"""Judge Mode (MP15): replay NIT's nine steps on a fresh BENCHMARK factory and refresh the 26-row scoreboard.

The replay is the benchmark runner itself (`benchmark/runner.py`), started as a separate process so the web request
returns at once; one run at a time. It never touches the DEMO factory or a visitor's factory: each run creates a new
BENCHMARK tenant (ADR-0006: nothing is deleted). Guarded by AAHAR_JUDGE_MODE (on by default for the demo).
"""

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.errors import ConflictError, DomainError

_lock = threading.Lock()
_proc: subprocess.Popen[bytes] | None = None
_started_at: float | None = None
_last_exit: int | None = None


class JudgeModeError(DomainError):
    pass


def _runner() -> Path:
    return get_settings().oracle_path.parent / "runner.py"


def running() -> bool:
    global _proc, _last_exit
    with _lock:
        if _proc is not None and _proc.poll() is not None:
            _last_exit, _proc = _proc.returncode, None
        return _proc is not None


def start() -> dict[str, Any]:
    """Start one replay; refuse a second while one is running."""
    global _proc, _started_at
    if not get_settings().judge_mode:
        raise JudgeModeError("judge_mode_off", "Judge Mode is switched off on this server (AAHAR_JUDGE_MODE)")
    if running():
        raise ConflictError("benchmark_running", "a replay is already running; the scoreboard updates when it ends")
    runner = _runner()
    if not runner.exists():
        raise JudgeModeError("runner_missing", f"the benchmark runner is not on this server ({runner.name})")
    with _lock:
        _proc = subprocess.Popen(  # noqa: S603 - a fixed script of this repository, no user input
            [sys.executable, str(runner)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        _started_at = time.time()
    return {"started": True, "note": "Replaying NIT's nine steps on a fresh benchmark factory (about a minute)."}


def status() -> dict[str, Any]:
    is_running = running()
    return {
        "judge_mode": get_settings().judge_mode,
        "running": is_running,
        "seconds": None if not is_running or _started_at is None else int(time.time() - _started_at),
        "last_exit": _last_exit,
    }
