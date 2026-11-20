"""Public, read-only guide endpoints for first-time visitors and judges.

No login: they expose only the benchmark oracle (fictional NIT data) and the latest scoreboard file.
"""

import json
from typing import Any

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.oracle import load_oracle, to_jsonable

router = APIRouter(prefix="/api/guide", tags=["guide"])


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
