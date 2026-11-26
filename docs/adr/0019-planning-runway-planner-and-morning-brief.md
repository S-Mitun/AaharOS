# ADR-0019: Material runway, shortage attribution, the CP-SAT batch planner, drafts and the Owner Morning Brief

- Status: Accepted (MP12, 2026-11-26; plan L1–L8 approved by the user as recommended the same day, built in four
  commits, one per module)
- Builds on: ADR-0013 (production run and variances), ADR-0014 (costing and the waterfall), ADR-0016 (reservations,
  backorders, the MP09 next-batch stub), ADR-0017 (collections)

## Context
Benchmark rows 23 (how much of Distributor B's shortage the batch's yield loss explains: 12 of 32) and 24 (the
material runway after the run: flour 3.00, oil 1.95, spice 3.17, pouches 1.53, cartons 2.10, one full batch) were the
last two red rows. MP12 also asks for a batch planner that recommends batches and purchases, and the owner's home
screen. The planner must never post anything: the ledger, invoices and runs stay human-approved.

## Decision

### L1. Material runway (row 24)
For each ACTIVE pack spec version and the active recipe it packs, one standard batch needs each recipe line's base
quantity plus each pack line's quantity × (bulk yield ÷ net weight). For every material, batches = available ÷
needed per batch, computed exactly and displayed to 2 dp (ROUND_HALF_UP). Available = on hand in RAW_STORE +
PACK_STORE (the projection). The binding materials are those with the smallest displayed figure; full batches =
floor(the smallest exact figure). Pure in `planning.domain.runway`, every figure Explained.

### L2. Shortage attribution (row 23)
For an order's backordered lines: the yield loss of completed runs of that finished good within
`planning.attribution_days` (effective-dated setting, DEMO 30) is Σ max(0, expected good − actual good). The part of
the shortage it explains = min(shortage, that loss), floored to whole packets; "would have been" = shortage − that.
NIT: min(32, 200 − 188) = 12; would have been 20. Shown as "Why short?" on a part-approved order card.

### L3. Planning settings (migration 0012)
`item_planning` per item: reorder level, safety stock, minimum order (base units) and lead time in days (0–365).
Master data under row-level security, changed only through `planning.set_item_params` with an audit row
(`PUT /api/planning/item-settings/{item}`, `settings.manage`). The daily batch capacity is the effective-dated
setting `planning.batches_per_day` (DEMO 2). DEMO values are fictional and seeded for the Section 5 materials.

### L4. The batch planner (OR-Tools CP-SAT, `ortools==9.11.4210`)
A small integer program, pure in `planning/planner.py` (no database):
- variables: batches per pack (0…capacity), packets of each finished good's shortfall met;
- constraints: Σ batches ≤ capacity; per material Σ need × batches ≤ available (base units scaled by 10⁶ to integers,
  rounded up so the solver never over-uses stock); met ≤ shortfall; met ≤ Σ good packets per batch × batches;
- objective: maximise Σ value (paise) × met, minus batches as a tie-break (weighted so one paisa of value always beats
  saving a batch);
- one worker and a 5 s limit: the same inputs give the same plan.
Demand = packets not yet decided (SUBMITTED) + backorders (PART_APPROVED), valued ex-tax at the captured prices
(`sales.open_demand`); shortfall = demand − available to promise. Good packets per batch = floor(bulk yield ÷ net).
It also works out a full plan (enough batches for every open packet), what that plan is short of, and a suggested
purchase per material: max(0, full-plan need + safety stock − available); if what is left after today's plan is below
the reorder level, at least enough to return to reorder level + safety stock; rounded up to the minimum order. Each
suggestion is Explained and carries a "needed by" date from the lead time.

### L5. Nothing is posted automatically
Approving a planned batch creates a **DRAFT** production run through `production.create_run` (starting it, issuing
materials and completing it stay manual floor steps, `run.start`). Approving purchases creates a **draft purchase
order** (`DPO/{fy}/{n}`, gapless numbering, `receipt.post`): `draft_purchase_orders` + insert-only lines. A draft is
intent only: no stock and no money move; the delivery is still a purchase receipt (MP05). A draft is cancelled with a
reason, never deleted (the app role holds no DELETE; the lines' trigger refuses UPDATE and DELETE).

### L6. Owner Morning Brief
`GET /api/planning/brief` (`report.read`): five cards and no more: today's orders (count, value, waiting for a
decision) · available vs pending (from the plan) · where profit leaks (top 3 unfavourable waterfall components of
completed runs in the last 30 days, ₹) · material runway (full batches, binding materials) · money to collect
(outstanding, overdue, unpaid beyond the MSME 45 days). Then "Today's 3 actions": candidates (decide waiting orders,
start the planned batches, buy what blocks the rest, call the largest overdue customer, check the largest leak), each
with its rupee impact as an Explained, ranked by `planning.domain.rank_actions` (largest ₹ first, ties in a fixed
order, nothing at zero, at most three).

### L7. Screens
Owner → Morning brief (the owner lands there), Production → Batch planner (runway with "runs out first", the plan, draft
batch and draft purchase order buttons by permission; the production role lands there), "Why short?" on the order
card, and one Owner step in the guided tour (12 steps). Count units read in the singular for one ("1 batch").

### L8. Layering
`planning` sits in the top layer with reports and judge; it reads production, sales, costing, collections, ledger,
recipe and catalog through their services and writes only its own tables (and a DRAFT run through production's
service). No lower module imports it.

## Consequences
- Rows 23 and 24 are green: 26/26.
- The planner recommends one production day; multi-day horizons, changeovers, shelf life and supplier choice are out
  of scope (MP16 forecasting may feed demand later).
- Draft purchase orders have no supplier yet unless one is given, and no "send to supplier" step; turning a draft into
  a receipt is manual.
- OR-Tools adds about 30 MB to the backend image.
