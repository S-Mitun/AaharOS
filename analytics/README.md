# analytics/

Separate from the ledger. **Reads** database views or exported files; **never writes** ledger, invoice, payment or
production tables. Built in MP16 (MASTER_PACK Part D).

| Folder | Purpose |
|---|---|
| `simulator/` | Seeded 24-month factory simulator with planted truths and injected data faults (synthetic, labelled) |
| `pipeline/` | raw → contract-validated → canonical units → de-duplicated → chronology-checked → feature tables |
| `models/` | Baselines first; LightGBM quantile demand, SPC charts, supplier-lot comparison, payment-delay risk; model cards |
| `eval/` | Rolling-origin backtests vs baselines, planted-truth recovery report (`make ml-eval`) |

Rules: time-based splits only; a model ships only if it beats its baseline; benchmark data is never training data.
