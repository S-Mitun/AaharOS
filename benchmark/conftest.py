"""Shared fixtures for the benchmark suite. The oracle is loaded with Decimals only (never float).

`stock_replay` posts the NIT stock movements through ledger.service into a fresh BENCHMARK tenant (MP04), using the
database the API uses (AAHAR_DATABASE_URL, as aahar_app so row-level security applies). The database must be
migrated first (`make migrate`); without one, the assertions that need it report a setup error, never a pass.
"""

from pathlib import Path
from typing import Any

import pytest

from app.core.oracle import load_oracle

ORACLE_PATH = Path(__file__).with_name("expected_results.yaml")


@pytest.fixture(scope="session")
def oracle() -> dict[str, Any]:
    return load_oracle(ORACLE_PATH)


@pytest.fixture(scope="session")
def stock_replay(oracle: dict[str, Any]) -> Any:
    from sqlalchemy.orm import Session

    from app import db_models as _db_models  # noqa: F401 - registers every table for the ORM
    from app.core.db import get_engine
    from app.modules.judge.replay import replay_stock

    with Session(get_engine(), expire_on_commit=False) as session:
        return replay_stock(session, oracle)
