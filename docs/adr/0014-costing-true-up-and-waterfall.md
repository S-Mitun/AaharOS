# ADR-0014: Run costs as value-only true-ups, standard cost cards, the waterfall and sensitivity

- Status: Accepted (MP07, 2026-11-21; plan and decisions F1–F8 approved by the user the same day)
- Builds on: ADR-0003 (two-level BOM), ADR-0004 (WAC and the late true-up), ADR-0012 (valuation from the ledger),
  ADR-0013 (the production run)

## Context
MP07 turns the run of MP06 into rupees: run cost, cost per good packet, the variance waterfall against a standard
cost card, and the WAC / FIFO / LAST comparison. NIT records labour and gas **after** 100 packets of B-001 have been
sold, so conversion costs must reach a lot that is partly sold (ledger.md J8). Every figure is an `Explained` value
and the UI's "Explain this number" popover shows it.

## Decision

### F1. Run costs: recorded on COMPLETED runs by `production`, each posting a true-up at once
- `production.service.record_run_cost` (kind LABOUR / GAS_POWER / OTHER, rupees to paise, Idempotency-Key) runs in
  one savepoint: the `run_costs` row, a value-only `COST_TRUE_UP` journal (source `run_cost`) and an audit row.
- `run_costs` is insert-only and needs its `journal_id` at insert, so a cost cannot be parked during the run and
  attached at completion; costs are refused before completion ("record them once the output is posted").
- `costing` (L6) writes no stock: it reads `production.service.costing_facts`.

### F2. The true-up spreads cumulatively over wherever the lot is
- Each pack line's share of the cost is by bulk allocated; the last line takes the rounding remainder.
- Within a lot: new target = what its positions hold + its share. Each position that holds units (CUSTOMER,
  IN_TRANSIT, FG_STORE, …) gets round_half_up(qty / lot qty × target) − what it holds; FG_STORE (on hand) takes the
  remainder, or the last position when nothing is on hand. Two true-ups (labour, then gas) end exactly where one
  would. Quantities are never touched.
- A pack line with no good units sends its share to SCRAP on the bulk item (consistent with ADR-0013 E4).
- The lot's stores are locked (`ledger.lock_item_stores`) before its positions are read, so a concurrent dispatch
  cannot read a half-updated lot value.
- NIT order, proven in `tests/db/test_costing.py::test_run_costs_in_nit_order_after_a_sale` with a stand-in dispatch
  journal: CUSTOMER +957.45, FG_STORE +842.55 → sold 100 = 3,114.36, on hand 88 = 2,740.64, total 5,855.00. In the
  MP07 replay the dispatch does not exist yet (MP10), so all 188 are on hand and B-001 ends at 5,855.00.

### F3. Cost status FINAL by an explicit action
- `POST /api/runs/{id}/costs/finalise` (`run.cost`): PROVISIONAL → FINAL, audited; no run cost is accepted after it.
  The replay records labour and gas, then finalises.

### F4. Standard cost cards are append-only and found by run date
- A card belongs to a pack spec version and has a version number: MATERIAL lines (recipe qty per batch × standard
  rate per base unit), PACKAGING lines (qty per good unit × rate), CONVERSION lines (rupees per batch), and
  `per_unit` to 6 dp. It is built from the recipe's ACTIVE version when created.
- Rates arrive per stock unit (₹42 per kg) and are stored per base unit (₹0.042 per g); a rate that is not exact at
  6 dp per base unit is refused, not rounded.
- Migration 0008 makes `standard_cost_cards` and `standard_cost_lines` insert-only (the app role keeps SELECT and
  INSERT; `aahar_forbid_change()` refuses UPDATE and DELETE even for the owner). Standards change by a new version.
- A run uses the card in force on its run date (latest effective date ≤ run date, then the highest version). It is
  not frozen into the run snapshot because production (L5) cannot import costing (L6); immutability of cards gives the
  same guarantee (`test_a_newer_card_does_not_revalue_an_older_run`).
- Seed: the 200 g card from the inputs at opening rates (A2) with step 8's labour and gas as the conversion standard,
  ₹28.85 (the same figure `costing.domain.standard_cost` gives for OPEN-LOT, D3). No 500 g card: the inputs give no
  rate for `pouch_500g`.

### F5. The waterfall
For the good output, actual − standard is split into parts that sum exactly:
- price per item = actual value − standard rate × actual qty
- usage per item = (actual qty − standard qty) × standard rate; ingredients against the batch standard, packaging
  against the flexible standard (qty per good unit × good units) per pack line, with a "n damaged" note
- yield per pack line = per-batch standard (ingredients + conversion) × share of bulk × (expected − good) / expected
- bulk not allocated = per-batch standard × unallocated / expected bulk
- conversion spend = actual run costs − conversion standard × batch multiplier
- items issued but not in the recipe: their whole value, as "no standard"
Each part is rounded half up to paise. If the rounded parts do not add up to actual − round(standard), a
"rounding" part shows the difference: nothing is silent residue (a Hypothesis property checks the sum). A run whose
pack lines' cards disagree on ingredient rates or conversion has no single waterfall and says why.

Benchmark: standard of 188 good = 5,120 × 188 / 200 + 3.25 × 188 = 5,423.80; actual 5,855.00; 431.20 U = yield
307.20 + oil usage 70.00 + flour price 45.00 + pouch usage 15.00 (6 damaged) − carton usage 6.00; conversion 0.

### F6. Sensitivity as of each issue
- `valuation.sensitivity_at(item, qty, before_journal)` replays the item's pool history up to, not including, the
  journal that issued it (the material issue, or the completion for packaging), so later purchases never leak in.
- Returns scale a method's value by net / issued quantity. A method with no answer for a movement (LAST before any
  purchase) uses the book value for it and lists the item ("book value used").
- Benchmark: WAC 5,855.00 / ₹31.14, FIFO 5,810.00 / ₹30.90, LAST 5,930.00 / ₹31.54. Only WAC posts.

### F7. Overheads deferred
- Monthly overhead absorption (machine-hours, fallback kg) needs data that has no table yet; it is MP11 (reports).
  Costing shows direct (marginal) cost and says so on the page.

### F8. A plain sign-in page
- `/sign-in` posts to the existing `/api/auth/login` (cookies stay httpOnly); MP08 adds the role shells.
- `/leaks` lists completed batches; `/leaks/{run}` shows run cost, cost per good packet, standard, the ranked
  waterfall with bars, "checks to make" worded as things to verify (never causes), and the method comparison. Every
  figure comes from `GET /api/runs/{id}/costing` and has an ⓘ "Explain this number" popover (formula, method, inputs
  and the document each came from; Escape closes it). Display rounding and bar widths use exact decimal strings and
  BigInt, never JavaScript floats.

### API and permissions
- `GET /api/runs/{id}/costing`, `GET /api/standard-cost-cards`: `report.read`.
- `POST /api/runs/{id}/costs`, `POST /api/runs/{id}/costs/finalise`: `run.cost` (ADMIN, PRODUCTION, OWNER).
- `POST /api/standard-cost-cards`: `recipe.manage`.

### Integrity
- `make integrity` now checks law 2 per run: for every COMPLETED run, the value its completion and true-ups put into
  its lots and SCRAP = its net material issues + the packaging its completion took + its run costs, read from
  `material_issue_lines`, `run_costs` and the journal lines (a dispatch only moves lot value, so it never matters).

## Consequences
- Benchmark 17, 18 and 19 are green (12/26). Assertion 22 (the 3,114.36 / 2,740.64 split) stays with MP10, which
  replays the dispatch before step 8; the true-up that produces it is built and tested now.
- The recorded fixture for the web tests comes from a real replay (`python -m app.cli.record_fixture`).
