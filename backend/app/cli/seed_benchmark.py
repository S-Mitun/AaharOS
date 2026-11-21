"""`make seed-benchmark`: a fresh BENCHMARK tenant with the NIT section 5 master data and opening stock.

ADR-0006: every reset is a **new** BENCHMARK organization, never a delete, so earlier replays stay auditable. The new
tenant's code is printed; the steps themselves (purchase, issue, run, ...) are posted by `make benchmark` and, from
MP15, by Judge Mode. Runs as `aahar_app`, so row-level security applies exactly as for the API.
"""

import sys

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import db_models as _db_models  # noqa: F401 - registers every table for the ORM
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.oracle import load_oracle
from app.modules.identity import service as identity
from app.modules.judge.replay import post_section5_opening, setup_section5


def main() -> int:
    oracle = load_oracle(get_settings().oracle_path)
    with Session(get_engine(), expire_on_commit=False) as session:
        org = identity.create_scratch_tenant(session, kind="BENCHMARK", label="SEED")
        s5 = setup_section5(session, oracle, org)
        post_section5_opening(session, oracle, s5)
        session.commit()
        code = session.execute(text("SELECT code FROM organizations WHERE id = :o"), {"o": org}).scalar_one()
    print(f"BENCHMARK tenant {code}: {len(s5.item_ids)} items, 1 supplier, {len(s5.customer_ids)} customers,")
    print("  opening stock posted (J0, valued; OPEN-LOT at standard cost). Earlier BENCHMARK tenants are kept.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
