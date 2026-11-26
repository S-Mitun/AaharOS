"""`make sim`: write the synthetic 24-month dataset (fixed seed) to analytics/data/generated and the datasheet."""

import json
import sys
from pathlib import Path

from analytics.simulator import generate as sim

HERE = Path(__file__).resolve().parents[1]


def main() -> int:
    world = sim.simulate()
    counts = sim.write(world, HERE / "data" / "generated")
    sheet = f"""# DATASHEET: the AaharOS factory simulator (SYNTHETIC)

- **Generator:** `analytics/simulator/generate.py`, seed `{sim.SEED}`, deterministic (same seed, same rows).
- **Span:** {sim.WEEKS} weeks from {sim.START.isoformat()} (24 months), one DEMO factory.
- **Rows:** {json.dumps(counts)} (orders include the injected duplicate syncs).
- **Entities:** 120 fictional customers on 12 routes (R-1..R-7 Tamil Nadu, R-8..R-12 Karnataka / Kerala), 15 SKUs
  (the 500 g SKU from month 13, TN only), 4 operators (night shift from month 7), 8 flour suppliers.
- **Planted truths:** `{json.dumps(sim.PLANTED)}`
- **Festival dates:** `analytics/simulator/festivals.py` (state public-holiday lists, with sources).
- **Known biases:** demand is log-normal around a linear trend with no weather, price or stock-out effects; payment
  delays are Gaussian per route; yields and oil are Gaussian per run. Real data is noisier and messier: results on
  this data show the methods recover known effects, not real-world accuracy.
- **Use:** analytics only. Never training data for the benchmark, never written to the ledger.
"""
    (HERE / "DATASHEET.md").write_text(sheet, encoding="utf-8")
    print(f"wrote {counts} to analytics/data/generated and analytics/DATASHEET.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
