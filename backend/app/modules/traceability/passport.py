"""Batch passport, QR and scan-to-reorder (MP13, T4, ADR-0020).

A passport token is (organization, lot[, customer]) signed with HMAC-SHA256 under a key derived from
AAHAR_AUTH_SECRET; nothing is stored, so there is no table to leak or clean up. The public page shows only what is
printed on the pack anyway: product, lot, made on, best before, net quantity, the DEMO FSSAI number and the factory
name. No prices, no customers, no stock. A forged or altered token is refused. A token that carries a customer adds
an "Ask for more" link; it opens the salesman app, which needs a signed-in salesman assigned to that customer, so a
scan never writes an order by itself.
"""

import base64
import hashlib
import hmac
import io
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final

import segno
from sqlalchemy.orm import Session

from app.core.calendar import business_date
from app.core.config import get_settings
from app.core.db import org_scope, scoped_org
from app.core.errors import DomainError, NotFoundError, RateLimitedError
from app.modules.billing import service as billing
from app.modules.catalog import service as catalog
from app.modules.identity import service as identity
from app.modules.ledger import service as ledger
from app.modules.production import service as production
from app.modules.recipe import service as recipes
from app.modules.tax import service as tax
from app.modules.uom.domain import normalise

TOKEN_CONTEXT: Final = b"aahar-passport-v1"
SIG_BYTES: Final = 16  # 128-bit tag: forging one is out of reach, and the QR stays small
PUBLIC_LIMIT: Final = 30  # public passport reads per IP per minute (in-process; MP17 adds a shared limiter)
DEMO_BANNER: Final = "DEMO: fictional factory and product, not for sale."


def _key() -> bytes:
    return hmac.new(get_settings().auth_secret.encode(), TOKEN_CONTEXT, hashlib.sha256).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class PassportRef:
    organization_id: uuid.UUID
    lot_id: uuid.UUID
    customer_id: uuid.UUID | None = None


def sign(ref: PassportRef) -> str:
    payload = ref.organization_id.bytes + ref.lot_id.bytes + (b"" if ref.customer_id is None else ref.customer_id.bytes)
    tag = hmac.new(_key(), payload, hashlib.sha256).digest()[:SIG_BYTES]
    return f"{_b64(payload)}.{_b64(tag)}"


def verify(token: str) -> PassportRef:
    """The reference a token was signed for; anything forged, altered or malformed is "not found"."""
    bad = NotFoundError("passport_not_found", "this passport link is not valid")
    if len(token) > 120 or token.count(".") != 1:
        raise bad
    body, tag = token.split(".")
    try:
        payload, given = _unb64(body), _unb64(tag)
    except (ValueError, TypeError):
        raise bad from None
    if len(payload) not in (32, 48) or len(given) != SIG_BYTES:
        raise bad
    if not hmac.compare_digest(hmac.new(_key(), payload, hashlib.sha256).digest()[:SIG_BYTES], given):
        raise bad
    return PassportRef(
        uuid.UUID(bytes=payload[:16]),
        uuid.UUID(bytes=payload[16:32]),
        uuid.UUID(bytes=payload[32:]) if len(payload) == 48 else None,
    )


def passport_url(token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/passport/{token}"


def qr_svg(text: str) -> str:
    """A standalone SVG (with its namespace, so it also works as an <img> data URL)."""
    buff = io.BytesIO()
    segno.make(text, error="m").save(buff, kind="svg", xmldecl=False, svgns=True, nl=False, scale=4)
    return buff.getvalue().decode()


# ---------- the per-IP limit on the public route ----------

_hits: dict[str, deque[float]] = {}
_hits_lock = threading.Lock()


def check_rate(ip: str | None, now: float | None = None) -> None:
    at = time.monotonic() if now is None else now
    key = ip or "unknown"
    with _hits_lock:
        q = _hits.setdefault(key, deque())
        while q and at - q[0] > 60:
            q.popleft()
        if len(q) >= PUBLIC_LIMIT:
            raise RateLimitedError("too_many_requests", "too many passport reads from this address; wait a minute")
        q.append(at)


# ---------- what the passport shows ----------


def _net_g(session: Session, info: ledger.LotInfo) -> str | None:
    if info.source_type == "production_run" and info.source_id is not None:
        for lot in production.trace_runs(session, [info.source_id])[info.source_id]["lots"]:
            if lot["lot_id"] == str(info.id) and lot["net_g"] is not None:
                return str(normalise(Decimal(lot["net_g"])))
    try:  # opening stock: the finished good's ACTIVE pack spec
        return str(normalise(recipes.active_pack_net_g(session, info.item_id)))
    except DomainError:
        return None


def public_view(session: Session, token: str, on: date | None = None) -> dict[str, Any]:
    """The public passport. Scopes the session to the token's organization (there is no login)."""
    ref = verify(token)
    org_scope(session, ref.organization_id)
    try:
        info = ledger.lot_info(session, ref.lot_id)
    except NotFoundError:
        raise NotFoundError("passport_not_found", "this passport link is not valid") from None
    if info.source_type == "purchase_receipt":
        raise NotFoundError("passport_not_found", "this passport link is not valid")
    today = on or business_date()
    _, name = catalog.names_for(session, [info.item_id])[info.item_id]
    org = identity.organization(session, ref.organization_id)
    net = _net_g(session, info)
    return {
        "demo": DEMO_BANNER,
        "factory": org["name"],
        "fssai_no": tax.profile(session, today).get("fssai_no"),
        "product": name,
        "lot_no": info.lot_no,
        "made_on": None if info.mfg_date is None else info.mfg_date.isoformat(),
        "best_before": None if info.best_before is None else info.best_before.isoformat(),
        "past_best_before": info.best_before is not None and info.best_before < today,
        "net_quantity": None if net is None else f"{net} g",
        "can_ask_for_more": ref.customer_id is not None,
    }


def label(session: Session, lot_id: uuid.UUID, customer_id: uuid.UUID | None = None) -> dict[str, Any]:
    """For the trace screen: the token, the public URL and the QR (SVG) of one finished-goods lot."""
    org = scoped_org(session)
    info = ledger.lot_info(session, lot_id)
    if org is None or info.source_type == "purchase_receipt":
        raise DomainError("no_passport", "passports are printed for finished-goods lots only")
    token = sign(PassportRef(org, lot_id, customer_id))
    url = passport_url(token)
    return {"token": token, "path": f"/passport/{token}", "url": url, "qr_svg": qr_svg(url)}


def resolve_reorder(session: Session, token: str) -> uuid.UUID:
    """The customer a reorder link is for. The caller checks the salesman may see that customer."""
    ref = verify(token)
    if ref.customer_id is None or ref.organization_id != scoped_org(session):
        raise NotFoundError("passport_not_found", "this reorder link is not valid")
    return ref.customer_id


def invoice_passports(session: Session, customer_id: uuid.UUID, lots: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Billing's hook: one customer-carrying passport URL per lot dispatched on an invoice."""
    org = scoped_org(session)
    if org is None:
        return []
    out = []
    for lt in lots:
        lot_id = ledger.lot_id_by_no(session, uuid.UUID(lt["item_id"]), lt["lot_no"])
        if lot_id is not None:
            out.append({"lot_no": lt["lot_no"], "url": passport_url(sign(PassportRef(org, lot_id, customer_id)))})
    return out


billing.register_passport_provider(invoice_passports)
