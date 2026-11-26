"""Public, read-only guide endpoints for first-time visitors and judges.

No login: they expose only the benchmark oracle (fictional NIT data) and the latest scoreboard file.
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import DomainError, NotFoundError
from app.core.oracle import load_oracle, to_jsonable
from app.modules.identity import supabase_auth
from app.modules.identity.service import Principal, require
from app.modules.judge import judge_mode, signup

router = APIRouter(prefix="/api/guide", tags=["guide"])
signup_router = APIRouter(prefix="/api", tags=["signup"])
judge_router = APIRouter(prefix="/api/judge", tags=["judge"])


@judge_router.post("/run", status_code=status.HTTP_202_ACCEPTED)
def judge_run(_principal: Annotated[Principal, Depends(require("benchmark.run"))]) -> dict[str, Any]:
    """Judge Mode: replay NIT's nine steps on a fresh BENCHMARK factory; the scoreboard refreshes when it ends."""
    return judge_mode.start()


@judge_router.get("/status")
def judge_status() -> dict[str, Any]:
    """Public: whether a replay is running (the scoreboard itself is /api/guide/scoreboard)."""
    return judge_mode.status()


@router.get("/expected")
def expected() -> dict[str, Any]:
    """The oracle's inputs and expected results, every number as an exact string."""
    path = get_settings().oracle_path
    if not path.exists():
        raise NotFoundError("oracle_missing", f"benchmark oracle not found at {path.name}")
    oracle = load_oracle(path)
    return {
        "source": "benchmark/expected_results.yaml",
        "version": to_jsonable(oracle.get("version")),
        "config": {
            k: to_jsonable(oracle.get(k))
            for k in ("timezone", "factory_state", "gst_rate_percent", "variance_tolerance_percent")
        },
        "inputs": to_jsonable(oracle["inputs"]),
        "nit_expected": to_jsonable(oracle["nit_expected"]),
        "aaharos_expected": to_jsonable(oracle.get("aaharos_expected", {})),
        "assumptions": to_jsonable(oracle.get("assumptions", {})),
    }


@router.get("/scoreboard")
def scoreboard() -> dict[str, Any]:
    """The last `make benchmark` result, or available=false if it has never run."""
    path = get_settings().benchmark_results_path
    if not path.exists():
        return {
            "available": False,
            "reason": "the benchmark has not run on this server yet: it starts a minute after the server wakes",
        }
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {"available": True, **data}


EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200, pattern=EMAIL_PATTERN)]


class SignUpBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factory_name: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    display_name: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    email: Email | None = None
    password: Annotated[str, StringConstraints(min_length=10, max_length=200)] | None = None
    access_token: Annotated[str, StringConstraints(min_length=20, max_length=4000)] | None = None  # Supabase mode


@signup_router.post("/signup", status_code=status.HTTP_201_CREATED)
def sign_up(body: SignUpBody, request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Public: create your own sandbox factory (Section 5 data, opening stock) with you as its owner. Sign in next."""
    signup.check_rate(request.client.host if request.client else None)
    if supabase_auth.enabled():  # Supabase Auth has the account and its password; the email comes from its token
        if not body.access_token:
            raise DomainError("access_token_required", "sign up at the sign-in server first")
        email, password = supabase_auth.verified_email(body.access_token), None
    else:
        if not body.email or not body.password:
            raise DomainError("email_and_password_required", "give an email and a password of at least 10 characters")
        email, password = body.email, body.password
    made = signup.sign_up(
        session, factory_name=body.factory_name, display_name=body.display_name, email=email, password=password
    )
    session.commit()
    return {"organization_code": made.organization_code, "email": made.email, "role": "OWNER"}
