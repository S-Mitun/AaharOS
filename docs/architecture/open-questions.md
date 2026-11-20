# MP01 open questions

**Approved 2026-11-21: all eight recommendations accepted as written.**

| # | Question | Recommendation | Why it matters |
|---|---|---|---|
| Q1 | Money columns: `NUMERIC(14,2)` rupees or `BIGINT` paise? (ADR-0008, MP02) | **NUMERIC(14,2)** for money; NUMERIC(18,6) for quantities and displayed unit costs | Maps 1:1 to Python `Decimal`, readable in SQL and exports, no ×100 conversions to explain live. Exactness is the same. |
| Q2 | Split the issue (step 2) and completion (step 3) with a real `WIP` location instead of one atomic post? | **Yes, split** (ADR-0002) | NIT checks flour 120 kg right after the issue step. Completion is still one atomic transaction. |
| Q3 | Damaged pouches and process scrap: absorbed into good output (normal loss) or written off? | **Absorbed by default**; a reason code can mark a loss *abnormal* (written off) in a later MP | The oracle's ₹5,855 and ₹31.14 include the 6 damaged pouches. |
| Q4 | Labour and gas entered after dispatch: a true-up journal split by quantity? | **Yes** (ADR-0004) | It is the only way to reach ₹3,114.36 + ₹2,740.64 = ₹5,855.00 in NIT's step order. |
| Q5 | Benchmark reset: a new BENCHMARK tenant per replay instead of deleting data? | **Yes** (ADR-0006) | Keeps "never delete a posted record" true everywhere. |
| Q6 | Dispatch posts straight to CUSTOMER, or to IN_TRANSIT until delivery is confirmed? | **Straight to CUSTOMER** in v1; IN_TRANSIT kept for MP14 trips | Simpler for the benchmark; delivery confirmation is a stretch goal. |
| Q7 | Distributor B in the scripted benchmark: leave SUBMITTED with the shortage shown, or approve 88 and backorder 32? | **Leave SUBMITTED**; the partial option is shown on the order card and demoed separately | Assertion 13 says "not invoiced"; a partial approval would also change the stock figures that follow. |
| Q8 | Freight on purchases: in inventory value or not? | **Excluded in v1**, recorded separately (ADR-0004) | The benchmark has none; WAC stays equal to NIT's rates. |
