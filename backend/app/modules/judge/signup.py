"""Self sign-up on the public demo (deployment): a visitor gets their own sandbox factory.

The new organization is a SIM tenant (the database refuses LIVE tenants for the app role) named after the visitor's
factory, with the same Section 5 master data and opening stock the guided tour uses, the DEMO food-safety settings,
and the visitor as its OWNER. Everything in it is the visitor's own; the shared DEMO factory is untouched.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Final

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import DomainError, RateLimitedError
from app.core.oracle import load_oracle
from app.modules.identity import service as identity
from app.modules.judge.replay import (
    post_section5_opening,
    setup_section5,
    setup_section5_food_safety,
    setup_section5_transport,
)

PER_IP_PER_HOUR: Final = 5
_hits: dict[str, deque[float]] = {}
_lock = threading.Lock()


def check_rate(ip: str | None, now: float | None = None) -> None:
    at = time.monotonic() if now is None else now
    with _lock:
        q = _hits.setdefault(ip or "unknown", deque())
        while q and at - q[0] > 3600:
            q.popleft()
        if len(q) >= PER_IP_PER_HOUR:
            raise RateLimitedError("too_many_signups", "too many new factories from this address; try again later")
        q.append(at)


@dataclass(frozen=True)
class SignedUp:
    organization_code: str
    email: str


def sign_up(session: Session, *, factory_name: str, display_name: str, email: str, password: str | None) -> SignedUp:
    """Create the sandbox factory and its owner in one transaction (the caller commits)."""
    if not get_settings().signups_open:
        raise DomainError("signups_closed", "new accounts are not open on this server")
    name = factory_name.strip()
    if not name or not display_name.strip():
        raise DomainError("missing_name", "give your name and your factory's name")
    org = identity.create_scratch_tenant(
        session, kind="SIM", label="OWN", name=name if "DEMO" in name.upper() else f"{name} (DEMO)"
    )
    identity.create_first_owner(session, organization_id=org, email=email, display_name=display_name, password=password)
    oracle = load_oracle(get_settings().oracle_path)
    s5 = setup_section5(session, oracle, org)
    post_section5_opening(session, oracle, s5)
    setup_section5_food_safety(session, org)
    setup_section5_transport(session, org)  # MP14: vehicles, locations, rates
    code = session.execute(text("SELECT code FROM organizations WHERE id = :o"), {"o": org}).scalar_one()
    return SignedUp(str(code), email.strip())
