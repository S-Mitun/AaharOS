"""Hash-chained audit log (MP03 gate: a tampered audit row is detected)."""

import threading
import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.cli import integrity
from app.core.db import org_scope
from app.modules.audit import service as audit
from tests.db.conftest import Tenant, as_org, login_client, make_staff, make_tenant, sqlstate


def _write(app_engine: Engine, t: Tenant, n: int) -> None:
    with Session(app_engine) as s:
        org_scope(s, t.org)
        for i in range(n):
            audit.record(
                s,
                organization_id=t.org,
                actor_id=None,
                action="test.event",
                entity_type="test",
                entity_id=uuid.uuid4(),
                before={"n": i},
                after={"n": i + 1, "amount": "7875.00"},
            )
        s.commit()


def _verify(owner_engine: Engine, t: Tenant) -> audit.ChainVerdict:
    with Session(owner_engine) as s:
        return audit.verify(s, t.org)


def _tamper(owner_engine: Engine, sql: str, t: Tenant) -> None:
    """What a DBA with superuser rights could do: switch the immutability trigger off, edit, switch it on."""
    with owner_engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_immutable"))
        c.execute(text(sql), {"o": t.org})
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER trg_audit_log_immutable"))


def test_records_build_a_verifiable_chain(owner_engine: Engine, app_engine: Engine) -> None:
    t = make_tenant(owner_engine, "CHAIN")
    _write(app_engine, t, 5)
    verdict = _verify(owner_engine, t)
    assert (verdict.ok, verdict.rows_checked) == (True, 5)
    with owner_engine.connect() as c:
        rows = c.execute(
            text("SELECT seq, prev_hash, hash FROM audit_log WHERE organization_id = :o ORDER BY seq"), {"o": t.org}
        ).all()
    assert [r.seq for r in rows] == [1, 2, 3, 4, 5]
    assert rows[0].prev_hash == bytes(32)
    assert all(rows[i].prev_hash == rows[i - 1].hash for i in range(1, 5))


def test_tampered_row_is_detected(owner_engine: Engine, app_engine: Engine) -> None:
    t = make_tenant(owner_engine, "TAMPER")
    _write(app_engine, t, 5)
    _tamper(
        owner_engine,
        "UPDATE audit_log SET summary = jsonb_set(summary, '{after,amount}', '\"1.00\"')"
        " WHERE organization_id = :o AND seq = 3",
        t,
    )
    verdict = _verify(owner_engine, t)
    assert (verdict.ok, verdict.first_bad_seq) == (False, 3)
    assert verdict.reason == "row content does not match its hash"

    with Session(owner_engine) as s:
        ok, lines = integrity.run(s)
    assert not ok
    assert any(line.startswith("FAIL") and str(t.org) in line and "seq 3" in line for line in lines)


def test_deleted_row_is_detected(owner_engine: Engine, app_engine: Engine) -> None:
    t = make_tenant(owner_engine, "GAP")
    _write(app_engine, t, 5)
    _tamper(owner_engine, "DELETE FROM audit_log WHERE organization_id = :o AND seq = 2", t)
    verdict = _verify(owner_engine, t)
    assert (verdict.ok, verdict.first_bad_seq) == (False, 2)


def test_deleted_newest_row_is_caught_by_the_chain_head(owner_engine: Engine, app_engine: Engine) -> None:
    t = make_tenant(owner_engine, "TAIL")
    _write(app_engine, t, 5)
    _tamper(owner_engine, "DELETE FROM audit_log WHERE organization_id = :o AND seq = 5", t)
    verdict = _verify(owner_engine, t)
    assert not verdict.ok
    assert verdict.reason == "chain head says 5 rows, found 4"


def test_audit_rows_cannot_be_edited(owner_engine: Engine, app_engine: Engine) -> None:
    t = make_tenant(owner_engine, "EDIT")
    _write(app_engine, t, 1)
    with pytest.raises(DBAPIError) as err, app_engine.begin() as c:
        as_org(c, t.org).execute(text("UPDATE audit_log SET action = 'x'"))
    assert sqlstate(err.value) == "42501"  # the app has no UPDATE right
    with pytest.raises(DBAPIError) as err, owner_engine.begin() as c:
        c.execute(text("DELETE FROM audit_log WHERE organization_id = :o"), {"o": t.org})
    assert sqlstate(err.value) == "AH002"  # and the trigger stops even the owner


def test_concurrent_writers_do_not_fork_the_chain(owner_engine: Engine, app_engine: Engine) -> None:
    t = make_tenant(owner_engine, "RACE")
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            _write(app_engine, t, 10)
        except BaseException as exc:  # surface thread failures in the test
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(3)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=60)
    assert errors == []
    verdict = _verify(owner_engine, t)
    assert (verdict.ok, verdict.rows_checked) == (True, 30)


def test_audit_api_lists_rows_without_secrets_and_verifies(owner_engine: Engine, api_app: Any) -> None:
    team = make_staff(owner_engine, "AUDITAPI")
    login_client(api_app, team.emails["OWNER"])  # writes an auth.login row
    auditor = login_client(api_app, team.emails["AUDITOR"])
    log = auditor.get("/api/audit/log")
    assert log.status_code == 200
    actions = [r["action"] for r in log.json()["rows"]]
    assert actions.count("auth.login") == 2
    assert "password" not in log.text.lower()
    assert auditor.get("/api/audit/verify").json() == {
        "ok": True,
        "rows_checked": 2,
        "first_bad_seq": None,
        "reason": None,
    }
