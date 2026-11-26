"""Batch passport, QR and scan-to-reorder against PostgreSQL (MP13, ADR-0020, module 3): the public route shows only
what is printed on the pack, refuses forged or altered tokens, is rate-limited per IP, and a reorder link only leads
a signed-in salesman who serves that customer to the pre-filled order."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.db import org_scope
from app.core.errors import RateLimitedError
from app.modules.identity import service as identity
from app.modules.sales import service as sales
from app.modules.traceability import passport
from app.modules.traceability.passport import PassportRef
from tests.db.conftest import login_client
from tests.db.test_traceability import Traced, traced  # noqa: F401 - the fixture is reused

PUBLIC_KEYS = {
    "demo",
    "factory",
    "fssai_no",
    "product",
    "lot_no",
    "made_on",
    "best_before",
    "past_best_before",
    "net_quantity",
    "can_ask_for_more",
}


def _customer(app_engine: Engine, t: Traced, code: str) -> uuid.UUID:
    with Session(app_engine) as s:
        org_scope(s, t.org)
        found = sales.customer_id_by_code(s, code)
    assert found is not None
    return found


def test_the_public_passport_shows_only_the_pack_label(api_app: Any, traced: Traced) -> None:  # noqa: F811
    owner = login_client(api_app, traced.emails["OWNER"])
    label = owner.get(f"/api/trace/passport/{traced.lots['B-001']}").json()
    assert label["path"] == f"/passport/{label['token']}" and label["url"].endswith(label["path"])
    assert label["qr_svg"].startswith("<svg")
    anonymous = TestClient(api_app)  # no login, no cookies
    r = anonymous.get(f"/api/public/passport/{label['token']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == PUBLIC_KEYS
    assert (body["lot_no"], body["net_quantity"], body["product"]) == ("B-001", "200 g", "DEMO murukku 200g")
    assert body["fssai_no"] == "10000000000000 (DEMO)" and body["demo"].startswith("DEMO")
    assert body["can_ask_for_more"] is False and body["best_before"] is not None
    for secret in ("RET-A", "Retailer", "DIST-B", "50.00", "AHR/", "invoice", "price"):
        assert secret not in r.text


def test_forged_altered_or_foreign_tokens_are_refused(api_app: Any, traced: Traced, app_engine: Engine) -> None:  # noqa: F811
    owner = login_client(api_app, traced.emails["OWNER"])
    token = owner.get(f"/api/trace/passport/{traced.lots['B-001']}").json()["token"]
    anonymous = TestClient(api_app)
    body, tag = token.split(".")
    flipped = tag[:-2] + ("A" if tag[-2] != "A" else "B") + tag[-1]
    other_lot = passport._b64(  # the payload re-pointed at another lot, keeping the old tag
        uuid.UUID(bytes=passport._unb64(body)[:16]).bytes + uuid.UUID(traced.lots["B-002"].hex).bytes
    )
    for bad in (f"{body}.{flipped}", f"{other_lot}.{tag}", "not-a-token", f"{body}", "a.b.c", "x" * 200):
        r = anonymous.get(f"/api/public/passport/{bad}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "passport_not_found", bad
    # a validly signed token for a supplier lot or a lot of another organization shows nothing either
    supplier = passport.sign(PassportRef(traced.org, traced.lots["FL-A"]))
    assert anonymous.get(f"/api/public/passport/{supplier}").status_code == 404
    foreign = passport.sign(PassportRef(uuid.uuid4(), traced.lots["B-001"]))
    assert anonymous.get(f"/api/public/passport/{foreign}").status_code == 404
    assert owner.get(f"/api/trace/passport/{traced.lots['FL-A']}").status_code == 422  # no passport for raw lots
    assert (
        owner.get(f"/api/trace/passport/{traced.lots['B-001']}", params={"customer_id": str(uuid.uuid4())}).status_code
        == 404
    )


def test_the_public_route_is_rate_limited_per_address() -> None:
    ip = f"198.51.100.{uuid.uuid4().int % 250}"
    for n in range(passport.PUBLIC_LIMIT):
        passport.check_rate(ip, now=1000.0 + n)
    with pytest.raises(RateLimitedError):
        passport.check_rate(ip, now=1000.0 + passport.PUBLIC_LIMIT)
    passport.check_rate(ip, now=1000.0 + 61 + passport.PUBLIC_LIMIT)  # a minute later it is allowed again
    passport.check_rate(f"{ip}0")  # another address is not affected


def test_ask_for_more_leads_only_the_customers_salesman_to_a_prefilled_order(
    api_app: Any,
    traced: Traced,  # noqa: F811
    app_engine: Engine,
    owner_engine: Engine,
) -> None:
    owner = login_client(api_app, traced.emails["OWNER"])
    ret_a = _customer(app_engine, traced, "RET-A")
    label = owner.get(f"/api/trace/passport/{traced.lots['B-001']}", params={"customer_id": str(ret_a)}).json()
    anonymous = TestClient(api_app)
    public = anonymous.get(f"/api/public/passport/{label['token']}").json()
    assert public["can_ask_for_more"] is True and set(public) == PUBLIC_KEYS  # still no customer name
    assert anonymous.get(f"/api/trace/reorder/{label['token']}").status_code == 401  # needs a login
    salesman = login_client(api_app, traced.emails["SALESMAN"])
    refused = salesman.get(f"/api/trace/reorder/{label['token']}")
    assert refused.status_code == 404  # not this salesman's customer
    with Session(app_engine) as s:
        org_scope(s, traced.org)
        salesman_id = next(
            uid
            for uid, name in identity.display_names(s, set(_members(owner_engine, traced))).items()
            if name == "DEMO SALESMAN"
        )
        identity.assign_customer(
            s, organization_id=traced.org, actor_id=None, salesman_id=salesman_id, customer_id=ret_a
        )
        s.commit()
    ok = salesman.get(f"/api/trace/reorder/{label['token']}").json()
    assert ok == {"customer_id": str(ret_a), "order_path": f"/sales/order/{ret_a}?repeat=1"}
    plain = owner.get(f"/api/trace/passport/{traced.lots['B-001']}").json()["token"]  # no customer in it
    assert salesman.get(f"/api/trace/reorder/{plain}").status_code == 404
    auditor = login_client(api_app, traced.emails["AUDITOR"])
    assert auditor.get(f"/api/trace/reorder/{label['token']}").status_code == 403  # no order.create


def _members(owner_engine: Engine, t: Traced) -> list[uuid.UUID]:
    from sqlalchemy import text

    with owner_engine.connect() as c:
        return list(
            c.execute(text("SELECT user_id FROM memberships WHERE organization_id = :o"), {"o": t.org}).scalars()
        )


def test_the_invoice_carries_a_customer_passport_per_lot(api_app: Any, traced: Traced, app_engine: Engine) -> None:  # noqa: F811
    owner = login_client(api_app, traced.emails["OWNER"])
    fwd = owner.get(f"/api/trace/lots/{traced.lots['B-002']}").json()["forward"][0]
    invoice_id = fwd["dispatches"][0]["invoice_id"]  # Distributor B's invoice: 40 of B-001 and 60 of B-002
    view = owner.get(f"/api/invoices/{invoice_id}").json()
    assert [p["lot_no"] for p in view["passports"]] == ["B-001", "B-002"]
    ref = passport.verify(view["passports"][0]["url"].rsplit("/", 1)[1])
    assert (ref.lot_id, ref.customer_id) == (traced.lots["B-001"], _customer(app_engine, traced, "DIST-B"))
    html = owner.get(f"/api/invoices/{invoice_id}/document").text
    assert "Batch passport" in html and html.count("<svg") >= 2
