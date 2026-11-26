# analytics/

Separate from the ledger. **Reads** database views or exported files; **never writes** ledger, invoice, payment or
production tables. Built in MP16 (MASTER_PACK Part D).

| Folder | Purpose |
|---|---|
| `simulator/` | Seeded 24-month factory simulator with planted truths and injected data faults (synthetic, labelled) |
| `pipeline/` | raw → contract-validated → canonical units → de-duplicated → chronology-checked → feature tables |
| `models/` | Baselines first; festival-aware demand, EWMA SPC, supplier-lot bootstrap, payment-delay logistic regression; model cards (`CARDS.md`) |
| `eval/` | Rolling-origin backtests vs baselines, planted-truth recovery report (`make ml-eval`) |

Rules: time-based splits only; a model ships only if it beats its baseline; benchmark data is never training data.

Run: `make sim` (writes the synthetic dataset and `DATASHEET.md`), `make ml-eval` (prints and writes `REPORT.md`, then the tests).
