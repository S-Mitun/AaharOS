"""Shared fixtures for the benchmark suite. The oracle is loaded with Decimals only (never float)."""

from pathlib import Path
from typing import Any

import pytest

from app.core.oracle import load_oracle

ORACLE_PATH = Path(__file__).with_name("expected_results.yaml")


@pytest.fixture(scope="session")
def oracle() -> dict[str, Any]:
    return load_oracle(ORACLE_PATH)
