"""Month-end close against PostgreSQL (MP11, ADR-0018, module 4): the cockpit, closing blocks postings dated in the
month, who may close and reopen, reopening keeps the history, and a lock is never deleted."""

import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from tests.db.conftest import login_client, sqlstate
from tests.db.test_billing import Factory, approved_order, factory  # noqa: F401 - the fixture is reused

NOV = "2026-11-01"


def test_cockpit_close_block_reopen(api_app: Any, factory: Factory, app_engine: Engine) -> None:  # noqa: F811
    order = approved_order(app_engine, factory, factory.ret_a, 10)
    owner = login_client(api_app, factory.emails["OWNER"])
    admin = login_client(api_app, factory.emails["ADMIN"])
    auditor = login_client(api_app, factory.emails["AUDITOR"])

    cockpit = auditor.get(f"/api/reports/close?month={NOV}").json()
    items = {i["key"]: i for i in cockpit["checklist"]}
    assert items["ready_to_invoice"]["count"] == 1 and items["ready_to_invoice"]["link"] == "/admin/invoices"
    assert cockpit["can_close"] is True and cockpit["locked"] is False
    assert all(c["ok"] for c in cockpit["integrity"]) and len(cockpit["integrity"]) == 8

    assert auditor.post("/api/reports/close/lock", json={"month": NOV, "reason": "DEMO close"}).status_code == 403
    assert admin.post("/api/reports/close/lock", json={"month": NOV, "reason": "  "}).status_code == 422
    closed = admin.post("/api/reports/close/lock", json={"month": NOV, "reason": "DEMO: November closed"})
    assert closed.status_code == 200 and closed.json()["locked"] is True
    again = admin.post("/api/reports/close/lock", json={"month": NOV, "reason": "DEMO: twice"})
    assert again.status_code == 409

    blocked = admin.post(f"/api/orders/{order}/invoice", json={"invoice_date": "2026-11-21"})
    assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "period_locked"

    assert (
        admin.post("/api/reports/close/reopen", json={"month": NOV, "reason": "DEMO: late invoice"}).status_code == 403
    )
    reopened = owner.post("/api/reports/close/reopen", json={"month": NOV, "reason": "DEMO: late invoice"})
    assert reopened.status_code == 200 and reopened.json()["locked"] is False
    assert admin.post(f"/api/orders/{order}/invoice", json={"invoice_date": "2026-11-21"}).status_code == 201

    relocked = admin.post("/api/reports/close/lock", json={"month": NOV, "reason": "DEMO: closed again"}).json()
    assert relocked["locked"] is True
    history = relocked["history"]
    assert [(h["active"], h["reopen_reason"]) for h in history] == [(False, "DEMO: late invoice"), (True, None)]


def test_a_lock_is_never_deleted_or_edited(api_app: Any, factory: Factory, owner_engine: Engine) -> None:  # noqa: F811
    admin = login_client(api_app, factory.emails["ADMIN"])
    assert admin.post("/api/reports/close/lock", json={"month": NOV, "reason": "DEMO close"}).status_code == 200
    for sql in (
        "DELETE FROM period_locks WHERE organization_id = :o",
        "UPDATE period_locks SET reason = 'changed' WHERE organization_id = :o",
        "UPDATE period_locks SET reopened_at = now() WHERE organization_id = :o",  # reopening needs a reason
    ):
        with pytest.raises(DBAPIError) as e, owner_engine.begin() as c:
            c.execute(text(sql), {"o": factory.org})
        assert sqlstate(e.value) in ("AH002", "23514"), sql
    assert uuid.UUID(str(factory.org))


def test_a_future_month_cannot_be_closed(api_app: Any, factory: Factory) -> None:  # noqa: F811
    admin = login_client(api_app, factory.emails["ADMIN"])
    r = admin.post("/api/reports/close/lock", json={"month": "2030-01-01", "reason": "DEMO: too early"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "future_period"
