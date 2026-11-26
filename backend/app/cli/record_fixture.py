"""Record the web app's test fixture: the JSON the API returns for run B-001 after a fresh benchmark replay.

`docker compose run --rm backend python -m app.cli.record_fixture > apps/web/src/test-fixtures/b001.json`
The replay creates a new BENCHMARK tenant (ADR-0006); every number is fictional DEMO data from the oracle's inputs.
"""

import json
import sys

from sqlalchemy.orm import Session

from app import db_models as _db_models  # noqa: F401 - registers every table for the ORM
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.oracle import load_oracle
from app.modules.costing import service as costing
from app.modules.judge.replay import replay_stock
from app.modules.production import service as production


def main() -> int:
    with Session(get_engine(), expire_on_commit=False) as session:
        replay = replay_stock(session, load_oracle(get_settings().oracle_path))
        assert replay.run_id is not None
        payload = {
            "costing": costing.run_costing(session, replay.run_id).to_json(),
            "run": production.get_run(session, replay.run_id),
            "runs": {"runs": production.list_runs(session)},
        }
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
