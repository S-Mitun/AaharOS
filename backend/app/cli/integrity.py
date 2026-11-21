"""`make integrity`: run every built integrity check and exit 1 if any fails.

Built: the audit hash chain of every organization (MP03); law 1 re-summed from every journal's lines and the
balance projection rebuilt from `stock_lines` and diffed (MP04; diff only, never repair); every posted receipt's
stock value equal to its lines (MP05); S6, the WIP of every completed production run is zero (MP06), with the mass
balance gap of each run reported (shown, never failed: law 3 is an explained gap, not a forced zero). The other laws
are added by MP11 and are listed here as NOT BUILT, never as passing. MP07 adds law 2 per run: the value each completed
run put into its lots and SCRAP equals its materials and its run costs.
"""

import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import db_models as _db_models  # noqa: F401 - registers every table for the ORM
from app.core.config import get_settings
from app.modules.audit import service as audit
from app.modules.billing import service as billing
from app.modules.ledger import service as ledger
from app.modules.procurement import service as procurement
from app.modules.production import service as production

NOT_BUILT = (
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

    imbalances = ledger.journal_imbalances(session)
    ok = ok and not imbalances
    if imbalances:
        lines.append(f"FAIL  law 1/2 journals balance: {len(imbalances)} unbalanced (journal, item) or journal sums")
        lines.extend(f"        {row}" for row in imbalances[:20])
    else:
        lines.append("PASS  law 1 quantity: every journal sums to zero per item (and to zero in value)")

    diff = ledger.projection_diff(session)
    ok = ok and not diff
    if diff:
        lines.append(f"FAIL  balance rebuild: {len(diff)} positions differ from inventory_balances (not repaired)")
        lines.extend(f"        {row}" for row in diff[:20])
    else:
        lines.append("PASS  balance rebuild: inventory_balances equals a rebuild from stock_lines")

    receipts = procurement.receipt_value_mismatches(session)
    ok = ok and not receipts
    if receipts:
        lines.append(f"FAIL  receipt value: {len(receipts)} receipts whose journal value differs from their lines")
        lines.extend(f"        {row}" for row in receipts[:20])
    else:
        lines.append("PASS  receipt value: every posted receipt's stock value = the sum of its accepted lines")

    wip = production.completed_run_wip_mismatches(session)
    ok = ok and not wip
    if wip:
        lines.append(f"FAIL  S6 run WIP: {len(wip)} (completed run, item) positions with WIP left on the floor")
        lines.extend(f"        {row}" for row in wip[:20])
    else:
        lines.append(
            "PASS  S6 run WIP: every completed run consumed exactly its net issues (WIP zero per run and item)"
        )

    value = production.run_value_mismatches(session)
    ok = ok and not value
    if value:
        lines.append(f"FAIL  law 2 value per run: {len(value)} completed runs whose lots + write-offs differ from cost")
        lines.extend(f"        {row}" for row in value[:20])
    else:
        lines.append("PASS  law 2 value per run: lots (wherever they are) + write-offs = materials + run costs")

    promised = ledger.over_reserved(session)
    ok = ok and not promised
    if promised:
        lines.append(f"FAIL  reservations: {len(promised)} positions promise more than they hold")
        lines.extend(f"        {row}" for row in promised[:20])
    else:
        lines.append("PASS  reservations: no store position promises more than it holds on hand")

    taxes = billing.tax_line_mismatches(session)
    ok = ok and not taxes
    if taxes:
        lines.append(f"FAIL  invoice tax: {len(taxes)} invoices whose lines do not add up to the header")
        lines.extend(f"        {row}" for row in taxes[:20])
    else:
        lines.append(
            "PASS  invoice tax: every invoice's lines and tax lines add up to its header (law 4, per document)"
        )

    gaps = production.mass_balance_gaps(session)
    lines.append(f"INFO  mass balance: {len(gaps)} completed runs show an unexplained gap (reported, not failed)")
    lines.extend(f"        {row}" for row in gaps[:20])
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
