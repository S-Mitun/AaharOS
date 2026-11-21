# ADR-0016: Order approval, reservations and the shortage options

- Status: Accepted (MP09, 2026-11-21; plan and decisions H1–H10 approved by the user the same day)
- Builds on: ADR-0011 (posting rules: per-(item, store) lock, reservations count against available), ADR-0015 (orders,
  server-side prices, the stale flag)

## Context
NIT step 5 starts with the admin approving Retailer A's 150 packets; step 6 asks what happens when Distributor B wants
120 and only 88 are left. MP09 builds the admin's order inbox and the decisions on an order so that stock is promised
exactly once, never below zero, and every change keeps the salesman's original request. Invoicing and dispatch are
MP10.

## Decision

### H1. Approve a whole order in one savepoint
The order row is locked `FOR UPDATE` (a second approval of the same order gets 409 `order_already_decided`). The
items' stores are locked in a fixed order (`ledger.lock_item_stores`, sorted by item id, so two approvals cannot
deadlock), available to promise is read, and each line reserves through `ledger.reserve` (which re-checks under the
same lock). Full approval reserves every agreed packet or nothing: a short line refuses the whole approval with the
shortage per line (`insufficient_available`, 422) and writes nothing. Status APPROVED, history and audit rows.

### H2. Partial approval with a backorder
"Send what is available now" reserves min(agreed, available) per line and records the rest as `qty_backordered`;
status PART_APPROVED. It is refused only when nothing can be reserved (`nothing_available`). "Fill the backorder"
reserves more as stock appears and turns the order APPROVED when nothing is owed.

### H3. Reject and cancel need a reason and release stock
Reject from SUBMITTED or PART_APPROVED; cancel from APPROVED or PART_APPROVED (before invoicing). Both release every
ACTIVE reservation of the order's lines, set approved/backordered to 0 (the audit row keeps the before values) and
write history and audit rows.

### H4. A stale price is chosen before approving
The card shows the phone's price next to today's list price. Approving a stale order needs `stale_price` =
`captured` or `current`; `current` writes `price_final` from the list in force **today** (the one the card shows as
"list today"; amended after the MP09 review, which found it used the version in force at receipt) with an automatic
`amend_reason` naming that version.

### H5. Amendments never overwrite the salesman's values
`qty_requested` and `price_captured` are never changed. A price change goes to `price_final` with a reason (the
existing CHECK requires it). A lower quantity is agreed at approval (with a reason) or amended down afterwards:
the backorder shrinks first, then the reserved packets (released and re-reserved). Raising a quantity is a new order.

### H6. Wait for the next batch
The order stays SUBMITTED; a history row records "Waiting for the next batch" with the earliest DRAFT / IN_PROGRESS
run that packs the item (`production.next_batch_for`: run no, date, planned packets) or "no batch planned, ETA
unknown". The batch planner replaces this read in MP12.

### H7. Credit check warns, an override needs a reason
Exposure = outstanding + this order (ex-tax) against `customers.credit_limit`; 0 means no limit is set. Outstanding
comes from a provider that collections registers in MP10 (`sales.service.register_outstanding_provider`: sales is
L5 and may not import L6); until then it is ₹0.00, labelled "no invoices exist until MP10". Over the limit, approval
needs `credit_override_reason`, recorded in the history and audit rows. DEMO limits (fictional): Retailer A ₹25,000,
Distributor B ₹1,00,000.

### H8. Benchmark row 13
The replay approves Retailer A at step 5 (150 of 238 reserved), places Distributor B's order and reads its inbox card:
requested 120, available 88, shortage 32; a full approval is refused with nothing written; FG never negative; B not
invoiced. The oracle's 88 is "after dispatch A" (MP10): here it is on hand 238 − reserved 150, and dispatch will
consume that reservation, so the figure stays 88.

### H9. Concurrency
Proven in `tests/db/test_inbox.py`: two different orders of 150 against 238 approved at the same instant → exactly one
APPROVED, the other `insufficient_available`; two approvals of the same order → one APPROVED, one
`order_already_decided`. `make integrity` gains "no store position promises more than it holds".

### H10. The admin's screens
`/admin/orders` (filters To decide · Short · Stale price · All) and `/admin/orders/{id}` (products, captured / final /
today's price, available to promise and shortage as `Explained` values with ⓘ, the credit check, the stale choice,
and one button per option in plain words). An admin lands on the inbox after sign-in.

## Consequences
- Statuses used: SUBMITTED → APPROVED / PART_APPROVED / REJECTED; APPROVED / PART_APPROVED → CANCELLED. INVOICED and
  DISPATCHED arrive with MP10, which must invoice only reserved (approved) packets and consume the reservations.
- Permissions: the inbox and decisions need `order.approve` (ADMIN, OWNER); amendments need `order.amend`.
- A "wait" leaves no reservation, so another order may take the stock first; the card says so by showing live ATP.
