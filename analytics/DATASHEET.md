# DATASHEET: the AaharOS factory simulator (SYNTHETIC)

- **Generator:** `analytics/simulator/generate.py`, seed `20261126`, deterministic (same seed, same rows).
- **Span:** 104 weeks from 2023-11-06 (24 months), one DEMO factory.
- **Rows:** {"orders": 44588, "runs": 1276, "invoices": 10576} (orders include the injected duplicate syncs).
- **Entities:** 120 fictional customers on 12 routes (R-1..R-7 Tamil Nadu, R-8..R-12 Karnataka / Kerala), 15 SKUs
  (the 500 g SKU from month 13, TN only), 4 operators (night shift from month 7), 8 flour suppliers.
- **Planted truths:** `{"festival_uplift": {"Deepavali": 3.2, "Pongal": 1.8, "Onam": 2.5}, "supplier_lot_yield_effect": {"S-05": -0.05}, "operator_oil_effect": {"O-3": 0.04, "from_month": 7}, "route_payment_days": {"R-7": 60, "other": 22}, "cannibalisation_500g_on_200g": {"effect": -0.15, "state": "TN", "from_month": 13}, "faults": {"duplicate_sync_rate": 0.02, "unit_error_rate": 0.005, "unit_error_factor": 1000}}`
- **Festival dates:** `analytics/simulator/festivals.py` (state public-holiday lists, with sources).
- **Known biases:** demand is log-normal around a linear trend with no weather, price or stock-out effects; payment
  delays are Gaussian per route; yields and oil are Gaussian per run. Real data is noisier and messier: results on
  this data show the methods recover known effects, not real-world accuracy.
- **Use:** analytics only. Never training data for the benchmark, never written to the ledger.
