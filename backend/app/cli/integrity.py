"""`make integrity`: run every built integrity check and exit 1 if any fails.

Built now (MP03): the audit hash chain of every organization. The four conservation laws and the balance rebuild
are added by MP04 and MP11 and are listed here as NOT BUILT, never as passing.
"""

import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import db_models as _db_models  # noqa: F401 - registers every table for the ORM
from app.core.config import get_settings
from app.modules.audit import service as audit

NOT_BUILT = (
    ("Law 1 quantity: every journal sums to zero per item", "MP04"),
    ("Balance projection equals a rebuild from stock lines", "MP04"),
    ("Law 2 value: lot value = run cost", "MP11"),
    ("Law 3 mass balance per run", "MP11"),
    ("Law 4 tax: lines = GST summary = export", "MP11"),
)


def run(session: Session) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True
    orgs = audit.organizations_with_audit(session)
    for org in orgs:
        verdict = audit.verify(session, org)
        ok = ok and verdict.ok
        if verdict.ok:
            lines.append(f"PASS  audit chain {org}: {verdict.rows_checked} rows")
        else:
            lines.append(f"FAIL  audit chain {org}: broken at seq {verdict.first_bad_seq} ({verdict.reason})")
    if not orgs:
        lines.append("PASS  audit chain: no audit rows yet")
    lines.extend(f"----  {name}: not built yet ({mp})" for name, mp in NOT_BUILT)
    return ok, lines


def main() -> int:
    engine = create_engine(get_settings().migration_database_url)  # the owner sees every organization
    with Session(engine) as session:
        ok, lines = run(session)
    engine.dispose()
    print("\n".join(lines))
    print("integrity: OK" if ok else "integrity: FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
