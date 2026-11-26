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
from app.core.errors import NotFoundError
from app.core.oracle import load_oracle, to_jsonable
from app.modules.judge import signup

router = APIRouter(prefix="/api/guide", tags=["guide"])
signup_router = APIRouter(prefix="/api", tags=["signup"])


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
        return {"available": False, "reason": "make benchmark has not been run on this server yet"}
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {"available": True, **data}


EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200, pattern=EMAIL_PATTERN)]


class SignUpBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factory_name: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    display_name: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    email: Email
    password: Annotated[str, StringConstraints(min_length=10, max_length=200)]


@signup_router.post("/signup", status_code=status.HTTP_201_CREATED)
def sign_up(body: SignUpBody, request: Request, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    """Public: create your own sandbox factory (Section 5 data, opening stock) with you as its owner. Sign in next."""
    signup.check_rate(request.client.host if request.client else None)
    made = signup.sign_up(
        session,
        factory_name=body.factory_name,
        display_name=body.display_name,
        email=body.email,
        password=body.password,
    )
    session.commit()
    return {"organization_code": made.organization_code, "email": made.email, "role": "OWNER"}
