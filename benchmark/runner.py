"""Benchmark scoreboard: `make benchmark`.

Runs the benchmark suite, prints the 26-row scoreboard against the oracle, writes results/latest.json
(read by the public guide page) and optionally a Markdown summary for GitHub Actions.

Status per assertion:
  GREEN  the assertion ran and passed
  RED    not built yet (strict xfail with NotImplementedError)
  FAIL   ran and failed, errored, or passed while still marked xfail
Exit code is 1 if anything is FAIL (including oracle-integrity checks), else 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.core.oracle import load_oracle, to_jsonable

HERE = Path(__file__).resolve().parent
ORACLE = HERE / "expected_results.yaml"
RESULTS = HERE / "results" / "latest.json"


def lookup(oracle: dict[str, Any], dotted: str) -> Any:
    node: Any = oracle
    for part in dotted.split("."):
        node = node[part]
    return node


class Collector:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.other: dict[str, str] = {}

    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        for item in items:
            marker = item.get_closest_marker("assertion")
            if marker is not None:
                number, title, owner_mp, *keys = marker.args
                self.rows[item.nodeid] = {
                    "n": number,
                    "title": title,
                    "owner_mp": owner_mp,
                    "keys": keys,
                    "status": "FAIL",
                    "detail": "did not run",
                }

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        row = self.rows.get(report.nodeid)
        if row is None:
            if report.when == "call" or report.failed:
                self.other[report.nodeid] = "pass" if report.passed and report.when == "call" else "fail"
            return
        if report.when == "setup" and report.failed:
            row.update(status="FAIL", detail="setup error")
        elif report.when == "call":
            if report.passed and not hasattr(report, "wasxfail"):
                row.update(status="GREEN", detail="")
            elif report.skipped and hasattr(report, "wasxfail"):
                row.update(status="RED", detail=f"not built yet ({row['owner_mp']})")
            elif report.failed and "XPASS(strict)" in str(report.longrepr):
                row.update(status="FAIL", detail="passes but still marked xfail: remove the marker")
            else:
                row.update(status="FAIL", detail="assertion failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summary", type=Path, help="append a Markdown scoreboard to this file")
    parser.add_argument("-q", "--quiet", action="store_true", help="hide pytest output")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    oracle = load_oracle(ORACLE)
    collector = Collector()
    pytest_args = [str(HERE), "-p", "no:cacheprovider", "-q" if args.quiet else "-v", "--no-header"]
    pytest.main(pytest_args, plugins=[collector])

    rows = sorted(collector.rows.values(), key=lambda r: r["n"])
    for row in rows:
        row["expected"] = {k: to_jsonable(lookup(oracle, k)) for k in row["keys"]}
    green = sum(r["status"] == "GREEN" for r in rows)
    failed = [r for r in rows if r["status"] == "FAIL"]
    integrity_failed = [k for k, v in collector.other.items() if v == "fail"]
    integrity_passed = sum(v == "pass" for v in collector.other.values())

    print()
    print(f"AaharOS benchmark scoreboard: {green}/{len(rows)} green")
    print("-" * 100)
    for r in rows:
        exp = ", ".join(f"{k.split('.')[-1]}={v}" for k, v in r["expected"].items()) or "see title"
        print(f"{r['n']:>2}  {r['status']:<5}  {r['title'][:44]:<44}  {exp[:40]:<40}  {r['detail']}")
    print("-" * 100)
    print(f"Oracle integrity checks: {integrity_passed} passed, {len(integrity_failed)} failed")
    for k in integrity_failed:
        print(f"  FAIL {k}")

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "green": green,
        "total": len(rows),
        "rows": [{k: r[k] for k in ("n", "title", "owner_mp", "status", "detail", "expected")} for r in rows],
        "oracle_integrity": {"passed": integrity_passed, "failed": len(integrity_failed)},
    }
    RESULTS.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.summary:
        lines = [
            f"## AaharOS benchmark: {green}/{len(rows)} green",
            "",
            "| # | Status | Assertion | Expected (oracle) | Note |",
            "|---:|---|---|---|---|",
        ]
        for r in rows:
            exp = ", ".join(f"`{k.split('.')[-1]}={v}`" for k, v in r["expected"].items())
            lines.append(f"| {r['n']} | {r['status']} | {r['title']} | {exp} | {r['detail']} |")
        lines += [
            "",
            f"Oracle integrity checks: {integrity_passed} passed, {len(integrity_failed)} failed",
            "",
        ]
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

    return 1 if failed or integrity_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
