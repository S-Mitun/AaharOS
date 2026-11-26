"""MP19 live-change drills (MASTER_PACK Part F) on the NIT replay: a 2% tolerance, a new GST rate and a customer's
own price take effect from their date, while the run, the invoice and the books already posted stay exactly as they
were. The settings route lets a manager make those changes; others cannot."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.calendar import business_date
from app.core.db import org_scope
from app.core.oracle import load_oracle
from app.modules.billing import service as billing
from app.modules.judge.replay import POSTING_DATE, replay_stock
from app.modules.production import service as production
from app.modules.production.domain import TOLERANCE_SETTING
from app.modules.reports import close
from app.modules.sales import service as sales
from app.modules.tax import service as tax
from tests.db.conftest import BACKEND, Staff, login_client

D = Decimal


@pytest.fixture(scope="module")
def replay(app_engine: Engine) -> Any:
    with Session(app_engine, expire_on_commit=False) as s:
        return replay_stock(s, load_oracle(BACKEND.parent / "benchmark" / "expected_results.yaml"))


def test_changes_apply_from_their_date_and_never_rewrite_the_past(replay: Any, app_engine: Engine) -> None:
    org = replay.organization_id
    later = POSTING_DATE + timedelta(days=1)
    with Session(app_engine, expire_on_commit=False) as s:
        org_scope(s, org)
        tax.put_setting(s, organization_id=org, actor_id=None, key=TOLERANCE_SETTING, value=D(2), effective_from=later)
        tax.create_rule(s, organization_id=org, actor_id=None, hsn="21069099", rate_pct=D(12), effective_from=later)
        sales.create_price_list(
            s,
            organization_id=org,
            actor_id=None,
            code="RETA-SPECIAL",
            effective_from=later,
            items={replay.item_ids["murukku_200g"]: D("48.00")},
            customer_id=sales.customer_id_by_code(s, "RET-A"),
        )
        s.commit()

        assert effective_settings.decimal_on(s, TOLERANCE_SETTING, POSTING_DATE) == D(3)
        assert effective_settings.decimal_on(s, TOLERANCE_SETTING, later) == D(2)
        rates = {r.effective_from: r.rate_pct for r in tax.rules(s)}
        assert rates[later] == D(12) and len(rates) == 2  # the 5% rule now ends the day before
        ret_a = sales.customer_id_by_code(s, "RET-A")
        assert ret_a is not None
        in_force = sales.price_list_in_force(s, ret_a, later)
        assert in_force is not None and in_force.code == "RETA-SPECIAL"

        # the past is untouched: B-001 keeps its frozen 3%, invoice A its 5% and Rs 7,875.00, the books are whole
        run = production.run_analysis(s, replay.run_id)
        assert run.tolerance_pct == D(3) and any("-6.00%" in f for f in run.flags)
        invoice = billing.invoice_view(s, replay.invoice_a_id)
        assert invoice["total"] == "7875.00" and invoice["by_tax"] == {"CGST": "187.50", "SGST": "187.50"}
        assert [c for c in close.integrity_checks(s, org) if not c["ok"]] == []


def test_only_a_manager_changes_settings_through_the_api(api_app: Any, staff: Staff) -> None:
    owner = login_client(api_app, staff.emails["OWNER"])
    auditor = login_client(api_app, staff.emails["AUDITOR"])
    tomorrow = (business_date() + timedelta(days=1)).isoformat()
    body = {"value": "15", "effective_from": tomorrow}
    assert auditor.put("/api/settings/freshness.alert_days", json=body).status_code == 403
    assert owner.put("/api/settings/org.gstin", json=body).status_code == 404  # identity, not a tunable number
    assert owner.put("/api/settings/freshness.alert_days", json={**body, "value": "1.5x"}).status_code == 422
    assert owner.put("/api/settings/freshness.alert_days", json=body).status_code == 200
    read = owner.get("/api/settings/freshness.alert_days", params={"on": tomorrow}).json()
    assert read["value"] == "15"
    assert TestClient(api_app).get("/api/settings/freshness.alert_days").status_code == 401
