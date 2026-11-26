"""Judge Mode (MP15): one replay at a time, only for benchmark.run, switched off by AAHAR_JUDGE_MODE."""

import time
from typing import Any

import pytest

from app.core.config import get_settings
from app.modules.judge import judge_mode
from tests.db.conftest import Staff, login_client


def test_who_may_start_a_replay_and_one_at_a_time(api_app: Any, staff: Staff, monkeypatch: pytest.MonkeyPatch) -> None:
    auditor = login_client(api_app, staff.emails["AUDITOR"])
    admin = login_client(api_app, staff.emails["ADMIN"])
    assert auditor.post("/api/judge/run").status_code == 403
    assert admin.get("/api/judge/status").json()["judge_mode"] is True

    started: list[list[str]] = []

    class FakeProc:
        returncode = 0

        def __init__(self, args: list[str], **_: Any) -> None:
            started.append(args)
            self.done = False

        def poll(self) -> int | None:
            return 0 if self.done else None

    monkeypatch.setattr(judge_mode.subprocess, "Popen", FakeProc)
    first = admin.post("/api/judge/run")
    assert first.status_code == 202 and started[0][-1].endswith("runner.py")
    again = admin.post("/api/judge/run")
    assert again.status_code == 409 and again.json()["error"]["code"] == "benchmark_running"
    assert admin.get("/api/judge/status").json()["running"] is True
    assert judge_mode._proc is not None
    judge_mode._proc.done = True  # type: ignore[attr-defined]
    time.sleep(0)
    assert admin.get("/api/judge/status").json()["running"] is False


def test_judge_mode_can_be_switched_off(api_app: Any, staff: Staff, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "judge_mode", False)
    owner = login_client(api_app, staff.emails["OWNER"])
    r = owner.post("/api/judge/run")
    assert r.status_code == 422 and r.json()["error"]["code"] == "judge_mode_off"
