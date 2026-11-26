# ADR-0020: Trace and recall, the batch passport, the freshness radar, the oil log and fill weights

- Status: Accepted (MP13, 2026-11-26; plan T1–T8 approved by the user as recommended the same day, radar included;
  built in five commits, one per module)
- Builds on: ADR-0005 (FEFO, lots at actual cost), ADR-0012 (D4: supplier lots recorded, raw stock lot-less),
  ADR-0013 (the run and its frozen snapshots), ADR-0017 (invoices, FEFO dispatch), ADR-0019 (the Morning brief)

## Context
MP13 asks for "trace this packet" backward and forward, a recall simulator, a batch passport with a QR and a
scan-to-reorder link, a shelf freshness radar, the RUCO oil log and fill-weight sampling with a giveaway estimate.
No benchmark row belongs to MP13, so it must not turn any of the 26 red. Supplier lot numbers are on receipt lines and
in `lots` (source `purchase_receipt`), finished-goods lots carry best-before, dispatch lines carry `lot_id`, runs
carry snapshots and `operator_id`, and `oil_sessions` / `fill_weight_samples` are written at completion (MP06). Raw
and packing stock has no lot in the ledger (D4).

## Decision

### T1. Trace a lot (`GET /api/trace/lots/{lot}`, `report.read`)
From a finished-goods lot, backward: the batch, its frozen recipe and pack versions, the operator, every material it
took from a store (issues and returns from RAW_STORE, packing consumed at completion from PACK_STORE) with the date,
the document and what each may contain (T2); opening stock reads "opening stock, no supplier lot recorded", a receipt
without a lot "receipt GRN/…, no supplier lot recorded". Forward: every dispatch of the lot (number, date, invoice,
customer, packets) and what is still in FG_STORE. Every figure is read from posted rows and is an Explained value
with its source document. A supplier lot traces to its receipts, the batches that may contain it and their lots.

### T2. Supplier lot → batches: the "may contain" window
Raw stock stays lot-less. A supplier lot (accepted quantity > 0) may be in every outflow of its item from its home
store after the lot arrived, until that store's balance of the item first falls to zero; then it is certainly used
up. Movements are read in the order the balance trigger applied them (`posted_at`, `clock_timestamp()` per journal);
movements at the same instant are read inflows first and checked for zero only at the end (conservative). A return to
the store brings back whatever its issue may have held; a reversal of an outflow brings back what that outflow may have
held. Pure in `traceability.domain.may_contain`, with a Hypothesis property test that, whatever order the floor
actually takes sacks in (and with returns and same-instant moves), every lot really used is in the window: a recall
may name an extra batch, never miss one. The UI says "may contain".
Rejected: lot-tracked raw stock (changes the ledger posting rules late in the project) and FIFO guessing (misses
batches whenever the floor does not use the oldest sack first).

### T3. Recall simulator (`GET /api/trace/recall/{lot}?reason=`, `report.read`)
From a supplier lot or a finished-goods lot: the affected batches and lots (made, dispatched, on hand), every customer
holding packets with the invoices and lots, totals, and a printable draft notice that starts and ends with "DEMO
SIMULATION - NOTHING HAS BEEN SENT". Read-only: nothing is stored, nothing is sent, and every number in the notice
comes from the recall facts.

### T4. Batch passport, QR and scan to reorder
A token is (organization, lot[, customer]) signed with HMAC-SHA256 under a key derived from `AAHAR_AUTH_SECRET`
(`hmac(secret, "aahar-passport-v1")`), with a 128-bit tag, base64url; nothing is stored. `GET
/api/public/passport/{token}` needs no login and returns only what is printed on the pack: product, lot, made on, best
before, net quantity, the FSSAI number (the effective-dated `org.fssai_no`, DEMO) and the factory name, with a DEMO
banner. No prices, customers or stock. Forged, altered, malformed, supplier-lot and foreign-organization tokens are
"not found"; 30 reads per IP per minute (in-process; a shared limiter comes with hosting, MP17). The route is listed as
deliberately public in the RBAC route test. `GET /api/trace/passport/{lot}` returns the link and the QR as SVG
(`segno==1.6.1`, already a dependency since MP10) for a printable label; `public_base_url` (config) is the host the QR
points at. The printed invoice carries one customer-carrying passport QR per dispatched lot through a billing hook
(`register_passport_provider`, like MP10's dispatch facts). "Ask for more" on a customer passport shares a link to
`/sales/reorder/{token}`; `GET /api/trace/reorder/{token}` (`order.create`) resolves it only for a salesman assigned to
that customer (or a role that sees all customers), who then opens the pre-filled order (`?repeat=1`) and submits it.
No unauthenticated write into orders.

### T5. The shelf freshness radar (`GET /api/trace/freshness`, `customer.read`)
Per customer × finished-goods lot: packets delivered in the last 90 days minus packets estimated sold. The selling rate
comes from that customer's order rhythm for the item over the same 90 days (rejected and cancelled orders left out):
packets ordered before the latest order ÷ days from the first to the latest order. The oldest best-before is counted
as sold first (no date first: opening stock). Low and high estimates use the mean order over the shortest and the
longest gap; fewer than two order days means "not enough history" and the whole delivery may still be on the shelf. A
lot is flagged when its best-before is within `freshness.alert_days` (effective-dated, DEMO 15) and the high estimate
is above zero; rupees at risk = high × the customer's latest price. A salesman sees only the customers assigned to
them. Shown as a chip on the salesman's Today list, a Freshness tab in the salesman app, and one more Morning brief
action candidate, "Visit X: up to N packets expire in D days" (kind `visit`); the brief keeps five cards and three
actions, and a missing setting leaves it as it was.

### T6. Oil log (RUCO) and fill weights (`GET /api/trace/oil`, `GET /api/trace/fill-weights`, `report.read`)
They read what batch completion recorded; there are no new write routes. Oil: litres per day = fresh + top-ups of the
runs dated that day, against `fssai.ruco_threshold_l_per_day` (DEMO 50: above it, daily used-oil records are required);
a session with TPC above `fssai.tpc_limit_pct` (DEMO 25) is flagged "discard". Fill weights, per batch with samples:
mean net, grams over declared, giveaway ₹ = max(grams over, 0) × good packets × ingredient cost per kg / 1000 (cost per
kg = ingredients issued ÷ the frozen recipe's bulk yield), rounded half up to paise; a sample below declared −
tolerance is a short fill, the tolerance read from `legal_metrology.short_fill_tolerance_g` (DEMO 200 g → 9 g, 500 g →
15 g, "verify with a Legal Metrology officer"). A missing setting is named in the error, never assumed.

### T7. DEMO history
`make seed-demo` posts, once, through the real services: three receipts with supplier lots (DEMO-FL-01, DEMO-PCH-01,
DEMO-SP-01, DEMO-FL-02, DEMO-OIL-01), batches B-001..B-003 with oil sessions and fill samples, Retailers C and D (new,
assigned to salesmen A and B) and six orders from Retailers A, C and D at different rhythms, each approved, invoiced and
dispatched FEFO. **Deviation from the approved plan:** T7 said "over the past 3 weeks"; the DEMO factory's opening
stock is dated on its opening day (2026-11-21, the benchmark date), so earlier issues and dispatches would come before
the stock they use. The history runs from the opening day to today (later days are clamped to today). DEMO factory
only; BENCHMARK tenants and the oracle are untouched; `make integrity` covers the new movements. `seed-demo` now also
tops up later MPs' settings right after a first run.

### T8. Screens and layering
Production → Trace and recall (lot search, backward / forward, recall simulator with a printable notice, passport
label), Production → Oil and fill weights, the public `/passport/:token` page outside the app shell, the salesman's
reorder hop, Salesman → Freshness and its Today chip, and the owner tour step. `traceability` sits in the top layer
with planning; it reads ledger, procurement, production, dispatch, sales, billing, recipe and catalog through their
services (new read helpers: `ledger.lot_info / lots_where / store_timeline`, `procurement.received_lots`,
`production.issue_refs / trace_runs / oil_records / fill_records`, `dispatch.lot_dispatches / deliveries_since`,
`sales.order_points`, `recipe.active_pack_net_g`) and writes nothing. No migration.

## Consequences
- 26/26 unchanged; no benchmark row depends on MP13.
- A supplier-lot recall can over-name batches while a store is never emptied; counting stock to zero now and then
  tightens it. Lot-tracked raw stock would make it exact, at the cost of changing ledger posting rules.
- The freshness radar is an estimate from order rhythm, not a shelf count; customers who order once are flagged on
  the whole delivery near best-before.
- The DEMO pack shelf life is 90 days, so today's DEMO history has nothing within 15 days of its best-before; the
  flag and the "Visit" action are shown by the tests at a later date.
- The public passport rate limit is per process; hosting (MP17) needs a shared one. Passport tokens cannot be revoked
  one by one: rotating `AAHAR_AUTH_SECRET` invalidates all of them (and all sessions).
- The RUCO, TPC and Legal Metrology figures are DEMO settings to verify before real use.
