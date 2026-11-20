import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_expected_returns_exact_strings(client: TestClient) -> None:
    r = client.get("/api/guide/expected")
    assert r.status_code == 200
    body = r.json()
    nit = body["nit_expected"]
    assert nit["flour_closing_kg"] == "120"
    assert nit["oil_closing_L"] == "19.5"
    assert nit["yield_variance_percent"] == "-6.00"
    assert nit["invoice_A"] == {"taxable": "7500.00", "cgst": "187.50", "sgst": "187.50", "total": "7875.00"}
    assert nit["distributor_B"]["tax_regime"] == "IGST"
    assert body["aaharos_expected"]["flour_wac_after_purchase"] == "43.125"
    assert body["inputs"]["steps"]["1_purchase"]["qty"] == "60"
    assert body["config"]["gst_rate_percent"] == "5"
    assert body["config"]["factory_state"] == "Tamil Nadu"
    assert body["aaharos_expected"]["distributor_B_options"]["full_120"]["eway_bill_required"] is False


def test_no_float_anywhere_in_payload(client: TestClient) -> None:
    def walk(v: object) -> None:
        assert not isinstance(v, float), v
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        if isinstance(v, list):
            for x in v:
                walk(x)

    walk(client.get("/api/guide/expected").json())


def test_missing_oracle_gives_error_envelope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AAHAR_ORACLE_PATH", str(tmp_path / "nope.yaml"))
    get_settings.cache_clear()
    r = TestClient(create_app()).get("/api/guide/expected")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "oracle_missing"
    get_settings.cache_clear()


def test_scoreboard_unavailable_then_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    results = tmp_path / "latest.json"
    monkeypatch.setenv("AAHAR_BENCHMARK_RESULTS_PATH", str(results))
    get_settings.cache_clear()
    client = TestClient(create_app())
    assert client.get("/api/guide/scoreboard").json()["available"] is False
    results.write_text(json.dumps({"green": 0, "total": 26, "rows": []}), encoding="utf-8")
    body = client.get("/api/guide/scoreboard").json()
    assert body["available"] is True
    assert body["total"] == 26
    get_settings.cache_clear()
