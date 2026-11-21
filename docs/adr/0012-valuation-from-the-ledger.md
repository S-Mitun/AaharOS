# ADR-0012: Valuation read from the ledger, purchase receipts, and the opening lot at standard

- Status: Accepted (MP05, 2026-11-21; plan and decisions D1–D4 approved by the user the same day)
- Amends: ADR-0004 (where the WAC pool and the FIFO layers live). The book method itself is unchanged.

## Context
ADR-0004 chose a moving weighted average as the book method, with FIFO and last price as sensitivity only. MP01
placed the pool in `item_cost_state` and the FIFO layers in `valuation_layers`. Building MP05 showed that both tables
would be state the application writes directly, next to the ledger it is derived from.

## Decision

### D1. The WAC pool is read from the ledger projection
- Pool (qty, value) = the item's `inventory_balances` summed over the pool stores `RAW_STORE` and `PACK_STORE`.
  WIP holds what runs were issued (at issue value) and finished goods are valued per lot (ADR-0005), so neither is
  pooled.
- The arithmetic is ADR-0004's: issue value = round_half_up(qty / pool_qty × pool_value); the last unit out takes the
  rest; the ₹/kg figure is display only (6 dp, an `Explained` value).
- `valuation.issue_value` takes the MP04 per-(item, store) lock **before** reading the pool, and the lock is held to
  the end of the caller's transaction, so a value cannot go stale before its journal posts.
- Why: `item_cost_state` would be a second balance that the app writes directly, breaking the golden rule "no endpoint
  may write a balance", and it could drift from `inventory_balances`. The table stays unused until a later migration
  drops it.

### D2. FIFO and last price are replayed from the ledger history
- `valuation.service.history(item)` is each journal's net change to the item's pool, in posting order. Pure functions
  replay it: FIFO turns every inflow into a layer and takes outflows from the oldest. A reversal of a receipt removes
  that receipt's own layer first. LAST is the most recent receipt's unit cost × qty.
- Nothing is stored and nothing posts. Benchmark, flour 40 kg: WAC ₹1,725.00 (posts), FIFO ₹1,680.00, LAST ₹1,800.00.
- Why: layers kept in `valuation_layers` would have to be unwound on every receipt reversal, for figures that never
  post. The table stays unused.

### D3. The opening finished-goods lot is valued at standard, computed from the inputs
- `costing.domain.standard_cost` (pulled forward from MP07): (Σ BOM qty × opening rate + labour + gas) ÷ expected
  good output. Benchmark: (1,680 + 1,400 + 240 + 500 + 150 + 1,200 + 600) ÷ 200 = ₹28.85, so OPEN-LOT 50 × 28.85 =
  ₹1,442.50 (A1, A2). The figure is derived in the replay from `inputs`, never read from the oracle's answers.

### D4. Supplier lots are recorded, raw stock stays lot-less
- A receipt line's supplier lot no. is stored on the line, and as a `lots` row (source `purchase_receipt`) with its mfg
  and best-before dates. If the item already has a lot with that number, the existing row is reused.
- Raw stock lines carry no lot, as ledger.md and the MP02 lot-of-item FK assume. FEFO for raw materials can come with
  MP13 (traceability).

### Purchase receipts
- One savepoint, never committed by the service:
  - claim the Idempotency-Key (`app/core/idempotency.py`, now shared by ledger and procurement)
  - the gapless number `GRN/26-27/000001`
  - receipt and lines inserted as DRAFT
  - the supplier lots
  - a SUPPLIER → home-store journal
  - POSTED, then the audit row
  A refusal rolls back everything, the number included, so numbers stay gapless (tested with a locked period).
- **Stock value = accepted qty × rate**, rounded once to paise. Rejected qty is recorded and never enters stock.
  Freight is recorded per line and **excluded** from stock value (ADR-0004 v1); the register shows it separately.
  GST on purchases is input credit and never part of a receipt line.
- Only RAW and PACK items are purchased. A receipt with nothing accepted is refused.
- A duplicate submit with the same key returns the first receipt (HTTP 200, `replayed: true`). The hash covers the
  receipt's meaning in base units, so 60 kg @ ₹45 and 60000 g @ ₹0.045 are the same request. The same key with a
  different receipt is 409.
- Correction is by reversal only: the exact mirror journal plus status REVERSED, with a reason and an audit row. A
  reversal that would take a store negative (the flour is already issued) is refused, and the receipt stays POSTED.
- The API takes quantities, rates and money as **decimal strings**; a JSON number is a 422, so no float can enter.

### Who sees what
- `GET /api/stock/valuation` and the purchase routes need `report.read` (`receipt.post` to post or reverse), so a
  salesman never sees cost. ADMIN cannot post receipts (PRODUCTION and OWNER can), per the MP03 matrix.

### Integrity
- `make integrity` adds: for every posted or reversed receipt, Σ accepted line values = the value its journal
  brought into the stores.

## Consequences
- There is one source of truth for stock value, and the WAC pool can never disagree with the balances.
- The sensitivity cost grows with an item's history (one query per item). That is fine at this factory's scale; MP17
  can add a materialised view if the panel ever gets slow.
- MP06 replaces the replay's J3 stand-in with the real production run, and MP07 extends `costing.domain` with run
  cost, variances and the waterfall.
