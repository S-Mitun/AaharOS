# ADR-0011: Ledger posting rules, idempotency, the reservation lock and the ₹0 stand-in replay

- Status: Accepted (MP04, 2026-11-21; plan approved by the user the same day)

## Context
MP04 builds the engine every later module posts through: units of measure, `ledger.domain.build_journal`,
`ledger.service.post / reverse / reserve / release`, the read-only stock API, the integrity checks and a
property-based state machine. ADR-0002 fixed the double-entry model and ADR-0009 the database guards. This ADR records
the rules the service adds on top, and four decisions taken while building it.

## Decision

### 1. Units (`uom.domain`)
- Converting to the base unit (g, mL, piece) only multiplies, so it is exact. A result with more than 6 decimal places
  (the ledger stores NUMERIC(18,6)) or a fractional piece is **refused, not rounded**.
- Converting back to kg / L / cartons is display only.
- A carton has no global size: `to_base(qty, "carton", units_per_carton=…)` takes the factor from the pack spec
  version. `split_into_cartons` is integer divmod (188 → 9 + 8).
- MASS ↔ VOLUME raises unless the item has a density row in `uom_conversions` (`item_id` set), stored as "item base
  units per base unit of the other dimension", so it is still a multiplication.

### 2. Journal rules (`ledger.domain.build_journal`, pure)
- Every line is converted to base units, then Σ qty per item = 0 and Σ value = 0 are checked before any SQL runs.
  PostgreSQL re-checks both (AH001); the domain check gives the user a readable message first.
- **The line role is derived, never typed:** qty > 0 → IN (SCRAP_IN when it lands on SCRAP at no value), qty < 0 →
  OUT, qty = 0 with a value → VALUE_ONLY (COST_TRUE_UP and REVERSAL only). A sign mismatch is refused.
- Each kind must reference its own source document type (RECEIPT → purchase_receipt, …, REVERSAL → stock_journal).
- ADJUSTMENT and REVERSAL need a reason; ADJUSTMENT needs an approver. Lot-tracked items need a lot on every line.
- Values must already be rounded to paise; the domain refuses 2700.005 rather than rounding it, because rounding one
  line silently would unbalance the journal. Rounding belongs to the valuation step (MP05) that computes the value.
- Floats are refused everywhere (`not_decimal`).
- Incoming lines are stored before outgoing ones: the store-not-negative CHECK runs per line (ADR-0009).

### 3. Posting (`ledger.service.post`)
- Runs in a **savepoint** inside the caller's transaction and never commits. A refusal rolls back the savepoint, so
  it leaves no trace and the caller's transaction stays usable; the caller commits its whole use case once (a
  production run posts its journal and its run rows atomically).
- After inserting the lines it runs `SET CONSTRAINTS trg_stock_lines_balanced, trg_stock_journals_have_lines
  IMMEDIATE` and then back to `DEFERRED`. The deferred balance triggers fire inside `post()`, so a refusal surfaces
  there with a clear error instead of at some later commit.
- `posted_at` is `clock_timestamp()`, not `now()`, so several journals posted in one transaction keep their order in
  the stock ledger.
- SQLSTATEs AH001–AH005, 23514 (by constraint name), 23505, 23503 and 42501 become `DomainError`s
  (`app/core/pg_errors.py`); anything else is re-raised.
- A deadlock (40P01) or serialization failure (40001) becomes `409 retry`: PostgreSQL rolled the transaction
  back, so nothing was written and the client may simply try again. (Added in the MP04 review: two journals that
  touch the same two balance rows in opposite order, such as a receipt and its reversal, can deadlock.)
- **Available ≥ 0:** for every store the journal takes stock out of, on hand after the movement minus ACTIVE
  reservations must be ≥ 0. A movement that would eat into stock held for an approved order is refused, even an
  adjustment: release or reduce the reservation first, so no approved order silently loses its stock.

### 4. Idempotency
- `post(..., idempotency_key=…)` claims the key in `idempotency_keys` with `INSERT … ON CONFLICT DO NOTHING`. A
  concurrent duplicate waits on that row, then sees it.
- The request hash is SHA-256 of the journal's **meaning** after conversion (kind, source, date, reason, approver,
  lines in base units, consumed reservations). 60 kg and 60000 g are the same request.
- Same key + same hash returns the original journal (`replayed=True`, nothing posted). Same key + different hash is
  `409 idempotency_key_reused`.

### 5. The per-(item, store) lock: an advisory lock, not `SELECT … FOR UPDATE`
- The approved plan said "lock the affected balance rows `FOR UPDATE`". PostgreSQL requires UPDATE privilege for
  `FOR UPDATE`, and ADR-0009 deliberately gives the app role SELECT only on `inventory_balances`. Granting UPDATE just
  to lock would weaken that guarantee.
- So `post()` and `reserve()` take `pg_advisory_xact_lock(hashtextextended('stock:<org>:<item>:<location>', 0))`
  for every store position they change availability of, in sorted order (no deadlock between two posts). The
  trigger's own UPDATE still row-locks each balance it changes. Same effect, no new privilege; a hash collision only
  serialises two unrelated positions.
- Proven by `tests/db/test_ledger_service.py::test_parallel_approvals_cannot_over_reserve`: two approvals of 150
  against 238 packets at the same instant, exactly one wins.

### 5b. What a salesman sees
- A salesman holds `stock.read` for the "available today" hint. Stock values are cost, and cost is margin data, so
  both stock routes drop every rupee value for roles that see only their own rows (MP04 review).

### 6. Reversals
- `reverse(journal_id, reason)` posts the exact mirror, line for line at the same values (history is never revalued).
- A reversal cannot be reversed (post the original movement again instead). A journal is reversed at most once
  (also a unique constraint). A reversal that would take a store negative is refused like any other posting.
- Reversing a dispatch does not reactivate its consumed reservation: re-approval is an order decision (MP09).

### 7. Reservations
- `reserve` checks available to promise = on hand in non-expired lots minus ACTIVE reservations, under the lock, and
  inserts the reservation in the caller's transaction. `release` moves ACTIVE → RELEASED with a reason.
  `post(..., consume_reservation_ids=…)` moves them to CONSUMED; it refuses a reservation that is not ACTIVE or is
  larger than what the journal takes out of that store.

### 8. Integrity (`make integrity`)
- Law 1 (and law 2 per journal) re-summed from every journal's lines, and `inventory_balances` rebuilt from
  `stock_lines` and diffed. **Diff only, never repair**: nothing may write a balance directly.

### 9. Benchmark: the ₹0 stand-in replay (approved in the plan)
- `app/modules/judge/replay.py` posts J0 opening, J1 purchase, J2 issue and J3 run output through `ledger.service`
  into a fresh BENCHMARK tenant (`identity.create_scratch_tenant`, ADR-0006). It reads only the oracle's `inputs`.
- Every line is posted at **₹0.00, labelled a stand-in**. MP05 (WAC) and MP06 (the production run with its frozen
  snapshot) replace it. Copying the oracle's rupee figures into the replay would use the answers as inputs, so it is
  rejected. Assertions 1–3 and 15 therefore check quantities only.
- Assertion 15's owner moved MP06 → MP04 (the MP04 spec names it). `inputs` and `nit_expected` are untouched (the
  sha256 guard still passes).
- The CI benchmark job now has a PostgreSQL 16 service and runs the migrations first.

## Consequences
- Every later module posts stock only through `ledger.service.post` with a source document; there is still no HTTP
  route that posts stock, so no endpoint can move stock without its document.
- The state machine (500 examples × up to 12 steps, each step checked against a model) is the regression net for any
  change to posting. It costs a few minutes in CI; `AAHAR_SM_EXAMPLES` lowers it locally.
- Reserved stock cannot be adjusted away without releasing the reservation first. If the factory finds this too strict
  for real count losses, MP09 can add an "adjust and release" use case that does both in one audited transaction.
