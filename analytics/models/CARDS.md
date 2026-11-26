# Model cards (MP16; synthetic-only performance)

All four advise only: they read records and never write to the ledger, invoices, payments or production tables.
Figures: `analytics/REPORT.md` (written by `make ml-eval`).

| Model | Intended use | Data | Baseline it must beat | Result on synthetic data | Failure modes |
|---|---|---|---|---|---|
| Festival-aware weekly demand (level of the last 8 non-festival weeks x the festival factor learned from earlier festivals) | P50 weekly packets per SKU x state for the planner | cleaned orders, SKU x state x week | seasonal-naive, 4-week average; ship gate: WAPE 10% better than seasonal-naive | ships (see REPORT.md) | a festival never seen before gets factor 1; no price, weather or stock-out effects; no P10/P90 (LightGBM quantiles not built) |
| EWMA chart per operator, oil L per batch (lambda 0.2, 3 sigma, Phase I = first 20 runs) | flag an operator drifting on oil | runs in time order | the fixed 3% tolerance rule | catches O-3 within 30 runs, < 1 false alarm per 50 runs | limits set on a drifting first 20 runs would hide the drift; one chart per operator, not per fryer |
| Supplier-lot yield bootstrap (2,000 resamples, 95% CI) | show a supplier whose lots yield less | runs with their flour lot | none (an effect size with an interval) | S-05 flagged, CI excludes 0 | needs raw-lot traceability per run (in AaharOS: the MP13 "may contain" window, which can blur lots) |
| Logistic regression, late payment (> 45 days) | order of reminder calls | invoices with each customer's history | "pays like last time" | ships; optimistic because R-7 is cleanly separable here | real histories are noisier; shown only as a reminder priority, never a credit decision |

Not built: LightGBM quantile models, pandera contracts (plain-Python checks instead), mandi-price context, any UI for
these figures, the planner reading the forecast. The planner keeps using today's open orders.
