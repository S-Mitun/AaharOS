# PROGRESS

## Status: MP11 done (branch feat/mp11-reports, one commit per module; module 5 + docs in the last) / MP12 next


## Benchmark scoreboard: 24/26
- **Green:**
  - 1 flour closing 120 kg, 2 oil 19.5 L, 3 pouches 306, 15 spice 3.8 kg / cartons 21 (MP04)
  - 16 flour WAC ₹43.125/kg after the purchase (MP05), an `Explained` value from `valuation.wac`
  - 4 FG after run 238, 6 yield −6.00% flagged, 7 oil +5.00% flagged, 20 pouch flexible +3.19% flagged (MP06)
  - **17 run cost ₹5,855.00 (materials ₹4,055.00 by item + labour ₹1,200 + gas ₹600), 18 cost per good packet ₹31.14
    with FIFO ₹30.90 / LAST ₹31.54 (only WAC posts), 19 waterfall ₹431.20 U with every component equal to the
    oracle's** (MP07)
  - **13 Distributor B: requested 120, available 88, shortage 32 flagged; a full approval refused with nothing
    written; FG never negative; not invoiced** (MP09)
  - **5 FG 88 after dispatch; 8–11 invoice A ₹7,500.00 + CGST ₹187.50 + SGST ₹187.50 = ₹7,875.00; 12 outstanding
    ₹3,875.00; 14 B's IGST ₹300 in full / ₹220 on 88; 21 FEFO 50 from OPEN-LOT + 100 from B-001; 22 sold 100 =
    ₹3,114.36 + on hand 88 = ₹2,740.64; 25 B's e-way bill not required (₹6,300 ≤ ₹50,000), reason shown** (MP10)
  - **26 integrity on the NIT tenant: audit chain, laws 1–4 (law 3 with B-001's 2.4 kg gap disclosed and flagged,
    law 4 = tax lines = GST summary = GSTR-1 export), balance rebuild, invoices add up, no over-promised stock** (MP11)
- They are replayed through the real services into a fresh BENCHMARK tenant (`app/modules/judge/replay.py`):
  - J0 opening, valued; J1 as a purchase receipt
  - run B-001 created and started; J2 a real material issue at WAC; J3 the real `complete_run`
  - J8 step 8: labour and gas as run costs (value-only true-ups), then the costs finalised (B-001 FINAL, ₹5,855.00)
  - (MP08) steps 4 and 6 as orders SO/26-27/000001 (Retailer A, 150) and 000002 (Distributor B, 120) at the DEMO
    general price list v1 (₹50.00 = `selling_price_ex_tax`)
  - (MP09) step 5's approval of Retailer A (150 of 238 reserved), then Distributor B's inbox card for row 13
  - (MP10) **NIT's order**: approve A → invoice AHR/26-27/000001 → dispatch J5 (FEFO, B-001 at provisional materials
    value) → order B → payment ₹4,000 (oldest due first) → J8 labour and gas (true-ups 957.45 to CUSTOMER, 842.55 to
    FG_STORE) → FINAL. Row 4 reads FG right after the run (238), since the replay now goes past it.
- Oracle integrity: 10/10 checks pass (the sha256 guard on `inputs` + `nit_expected` included). No green row turned
  red.

Red items and the MP that turns them green:
- MP12: 23 shortage attribution, 24 runway

## Done in MP11 (reports, GST export, month-end close, evidence pack)
- **Gate met:** **24/26** (row 26 green; no green row turned red), oracle 10/10; `make integrity` OK with every law built
  (no "not built yet" lines); Playwright 7/7 (repeat-order time printed 358 ms, automated).
- **Five commits, one per module** (the user asked to commit after each module): 2c14cbb report engine and core
  reports; ea761d7 GST summary, export, law 4; a8244e5 law 3; 828ac06 close cockpit and period lock / reopen; the last
  commit holds the evidence pack, Tally XML, bank statement, the Auditor screen, row 26 and the docs.
- **Decisions K1–K9 (approved; [ADR-0018](adr/0018-reports-gst-close-and-evidence.md)).**
- **Backend:** `reports` (domain: one report shape + CSV / XLSX / printable; service: sales and purchase registers,
  stock summary and ledger, production, receivables ageing; gst: GSTR-1 tables 4A/5/7/9B/12/13 + 3B 3.1, the
  GSTR-1-shaped JSON, law 4; close: cockpit, close / reopen; exports: evidence pack ZIP, Tally XML, bank statement);
  `ledger.movement_summary`, `stock_lines_export`, `lock_period` / `reopen_period` / `period_locks` / `is_locked`;
  `billing.register_rows`, `documents_issued`; `production.domain.mass_law`, `mass_law_results`;
  `audit.chain_head`; migration 0011 (lock history, reopen once with a reason, one active lock per month);
  `openpyxl==3.1.5`; DEMO settings `gst.b2cl_threshold` (₹1,00,000), `bank.stock_margin_pct` (25),
  `bank.debtors_margin_pct` (40), topped up on the DEMO factory.
- **API:** `GET /api/reports`, `/api/reports/{name}?format=json|csv|xlsx|html` (sales-register, purchase-register,
  stock-summary, stock-ledger, production, receivables-ageing, bank-statement, gst-summary), `/api/reports/gstr1-export`,
  `/api/reports/tally-xml`, `/api/reports/evidence-pack`, `/api/reports/close`; `POST /api/reports/close/lock`
  (`period.lock`), `/api/reports/close/reopen` (`period.reopen`).
- **Web:** Auditor → Reports (tabs Reports, GST, Close month, Evidence; any `report.read` role), drill-down links,
  downloads; tour step 9 is the real clicks.
- **Fixed in passing (real bug, found on the live check):** parallel requests with an expired access cookie each
  refreshed; the second reused the rotated token and the server revoked the session, so a reload after 15 minutes
  signed the user out. Single-flight refresh now (`refreshSession` in `lib/api.ts`), used by the start-up session check
  and the outbox; test `src/lib/api.test.ts`.
- **Checks run:** backend **747 passed** (was 665; full suite incl. 500 state-machine examples), ruff / format clean,
  mypy --strict clean, import-linter 2/2, `alembic check` clean (0011 applied to the dev DB); web **62 passed**,
  typecheck / lint / build clean; float grep clean; live on :5180 as the DEMO admin: the Close Cockpit shows the
  open order and 8 passing integrity checks (the DEMO month was left open).
- **New tests:** `tests/db/test_reports.py` (11: totals = direct SQL, stock closing = projection, production and
  ageing figures, formats, GST 4A / 3B and the export, a changed export detected, law 4 with a credit note and a
  cancelled invoice, bank drawing power, Tally voucher balances, evidence pack contents, the NIT tenant's integrity),
  `tests/db/test_close.py` (3), `production/tests/test_mass_law.py` (3), `src/reports/reports.test.tsx` (2),
  `src/lib/api.test.ts` (1).

## Review of MP09 (2026-11-21, before MP10)
- **Fixed, real bug:** choosing "today's list price" for a stale order applied the list in force at receipt, not the
  one the card shows as today's (v2 applied while v3 was shown). Test:
  `test_inbox.py::test_current_price_means_the_list_the_admin_sees_today` (failed before the fix). ADR-0016 H4 amended.
- **Hardening:** order history rows written in one transaction now sort received-first (they shared `now()`); could
  not be reproduced, pinned by `test_history_lists_received_before_decisions_in_one_transaction`.
- **UI:** the stale-price choice names a price only on single-product orders.

## Done in MP10 (tax engine, invoices, FEFO dispatch, collections)
- **Gate met:** **23/26** (rows 5, 8–12, 14, 21, 22, 25 green; 13 and 17–19 still green), oracle 10/10; `make
  integrity` OK with a new check (each invoice's lines and tax lines add up to its header); Playwright **7/7** (new:
  approve → invoice → FEFO dispatch → payment through the UI; repeat-order time printed 664 ms this run, automated).
- **Decisions J1–J10 (approved; [ADR-0017](adr/0017-tax-invoices-dispatch-and-collections.md)):** pure tax engine on
  effective-dated rules; invoices of approved packets only, gapless AHR numbers; cancel before dispatch, credit notes
  after (value-only); printable HTML invoice with a DEMO UPI QR, text-only share links; business identity and
  thresholds as settings; FEFO at lot value consuming exactly the packets leaving; mock e-way check; payments with
  oldest-due allocation, advances, MSME due dates; the replay in NIT's order; the admin screens.
- **Backend:** `tax` (domain, service, api), `billing` (domain, document, service, api, schemas), `dispatch` (domain,
  service, api), `collections` (service, api); migration 0010 (`dispatches.eway_payload`, dispatches insert-only);
  `ledger.fefo_lots`; `catalog.hsn_for` / `set_hsn`; `identity.organization`; sales: invoiced provider, billing status
  sync (INVOICED / DISPATCHED), guards (cancel or amend below what is invoiced refused), tax and e-way preview on the
  card, `set_payment_terms`; providers wired in `app/db_models.py`; `segno==1.6.1` (API image rebuilt).
- **API** (all in the generated route × role tests): `GET /api/invoices`, `/api/invoices/ready`,
  `/api/invoices/{id}`, `/api/invoices/{id}/document`, `/api/invoices/{id}/dispatches`, `/api/collections`,
  `/api/customers/{id}/statement`, `/api/tax/rules`; `POST /api/orders/{id}/invoice`, `/api/invoices/{id}/cancel`,
  `/api/invoices/{id}/credit-notes`, `/api/invoices/{id}/dispatch-preview`, `/api/invoices/{id}/dispatch`,
  `/api/payments`, `/api/tax/rules`.
- **Seeds:** HSN 21069099 (DEMO, verify with a CA), the GST rule at the oracle's 5% from 22-Sep-2025, the DEMO business
  profile, e-way thresholds ₹50,000, no round-off, 30-day MSME terms; `make seed-demo` topped up the DEMO factory.
- **Web:** Admin → Invoices and dispatch (`InvoicesPage`, `InvoicePage`: tax breakup, print / WhatsApp / email,
  preview then record dispatch, credit note, cancel) and Collections (`CollectionsPage`: owed, overdue, advance,
  record payment); the order card's "If invoiced" preview; tour steps 5 and 7 are the real clicks.
- **Live check on :5180 (DEMO factory, read-only):** the order card's preview (CGST + SGST ₹187.50 each, no e-way
  bill, with the reason); Invoices and Collections render. It caught a bug: "Overdue ₹0" on customers who owe nothing
  (amounts summed to `0`, not `0.00`); fixed in the backend (always paise) and the screen (zero by value).
- **Checks run:** backend **665 passed** (was 556; full suite incl. 500 state-machine examples, 6 min 4 s), ruff
  check / format clean, mypy --strict clean (137 files), import-linter 2/2 kept, `alembic check` clean (0010 applied
  to the dev DB); web **59 passed** (was 58), typecheck, lint and build clean; float grep clean; benchmark 23/26 and
  `make integrity` OK re-run after the last edits.
- **New tests:** `tax/tests/test_domain.py` (9, one property: header = Σ lines), `billing/tests/test_domain.py` (6),
  `dispatch/tests/test_domain.py` (6, one property), `tests/db/test_billing.py` (12: NIT invoice and document,
  approved-only, gapless numbers under 4 parallel requests, FEFO at lot value, partial dispatch, chosen lots need a
  reason, cancel only before dispatch, credit note limits, payments / advance / idempotency, outstanding feeds the
  credit check, part-approved order with an invoice cannot be cancelled), replay tests updated to the ledger.md end
  state, `src/admin/billing.test.tsx`, Playwright scenario 7.

## Done in MP09 (order inbox, available to promise, reservations, shortage options)
- **Gate met:**
  - row 13 green: **13/26**, oracle 10/10, no green row turned red
  - the race tests pass: two orders of 150 against 238 approved at the same instant → exactly one APPROVED, the
    other `insufficient_available`; two approvals of one order → one APPROVED, one `order_already_decided`
  - `make integrity` OK, with a new check: no store position promises more than it holds
  - `make e2e` (run as its two commands): **6/6** (new: the admin approves in the inbox and the salesman's phone shows
    Approved); repeat-order time printed 366 ms (automated)
- **Decisions H1–H10 (approved; [ADR-0016](adr/0016-order-approval-reservations-and-shortage-options.md)):** H1 full
  approval all-or-nothing under the order and item locks; H2 partial + backorder, filled later; H3 reject / cancel with
  a reason release stock; H4 stale orders need a price choice; H5 amendments never overwrite the salesman's values;
  H6 wait for the next batch (planner stub); H7 credit check warns, override needs a reason (outstanding provider for
  MP10); H8 the replay approves A at step 5; H9 race tests; H10 the inbox and card screens.
- **Backend:**
  - `sales.domain` (pure): allowed status changes, agreed quantities, the approval plan (full / partial), the
    backorder plan, status after, amending down, shortage, `Explained` available-to-promise and shortage, the credit
    check
  - `sales.service`: `approve_order`, `approve_backorder`, `reject_order`, `cancel_order`, `amend_line`,
    `wait_for_batch`, `inbox(view)`, `inbox_card`, `get_order_any`, `set_credit_limit`, `credit_limit_of`,
    `register_outstanding_provider`; `create_customer` takes a credit limit; order views carry approved /
    backordered / final price
  - helpers: `ledger.active_reservations`, `ledger.over_reserved` (integrity), `recipe.pack_spec_versions_for`,
    `production.next_batch_for`
  - seeds: DEMO credit limits (RET-A ₹25,000, DIST-B ₹1,00,000); `make seed-demo` set them on the DEMO factory
- **API** (all in the generated route × role tests): `GET /api/inbox?view=`, `GET /api/inbox/{id}`,
  `POST /api/orders/{id}/approve | approve-backorder | reject | cancel | wait` (`order.approve`),
  `POST /api/orders/{id}/amend` (`order.amend`); each decision returns the refreshed card.
- **Web:** `src/admin/` (InboxPage with filter chips, OrderCardPage with the stock line and shortage as ⓘ numbers,
  credit, the stale choice, one button per option, backorder, cancel / reject, history); the Order inbox is built in
  the registry; an admin lands on it after sign-in; tour steps 5 and 6 rewritten to the real clicks (invoicing marked
  "Coming in MP10").
- **Checks run:** backend **556 passed** (was 496; full suite incl. 500 state-machine examples, 2 min 58 s), ruff
  check / format clean, mypy --strict clean, import-linter 2/2 kept, `alembic check` clean (no migration in MP09);
  web **58 passed** (was 55), typecheck, lint (no warnings) and build clean (emits `sw.js`); float grep clean;
  benchmark 13/26 and `make integrity` OK re-run after the last edits.
- **New tests:** `sales/tests/test_approval.py` (11, one property: never reserves above available or beyond the
  request), `tests/db/test_inbox.py` (9, incl. both race tests), `test_replay.py` updated (A approved),
  `src/admin/admin.test.tsx` (3), Playwright scenario 6.
- **Checked live on :5180** as the DEMO Factory admin: landed on the inbox; Salesman A's 150-packet order shows
  "Short of stock" against the DEMO factory's 50 packets (available 50, shortage 100), the three options and the
  credit check within ₹25,000. Left undecided for the user to try.

## Done in MP08 (one app shell, the salesman PWA, the offline outbox, the orders API)
- **Gate met:**
  - one frontend (:5180) with every role's screens in its grouped sidebar and the tour first; one API (:8180)
  - `make e2e` (run as its two commands): **5/5 Playwright scenarios pass** on a fresh SIM tenant: online order; offline
    order → reconnect → exactly one server order; a duplicate send (reply dropped) replayed with the same key, one
    order; a stale price flagged (v2 published while offline); repeat-order time printed: **373 ms** (automated
    taps, dev stack; no target claimed, a human's time is not measured)
  - benchmark **12/26**, oracle 10/10, no green row turned red; `make integrity` OK
- **Checks run:** backend **496 passed** (was 431; full suite incl. 500 state-machine examples, 3 min 18 s), ruff
  check / format clean, mypy --strict clean (121 files), import-linter 2/2 kept, `alembic check` clean (0009 applied
  to the dev DB), float grep clean; web **55 passed** (was 26), typecheck / lint (no warnings) / build clean (the build
  emits `sw.js` and the manifest). Checked live on :5180 as Salesman A (DEMO factory): Today → New order → 150 →
  Save → SO/26-27/000001, "Received by factory", ₹7,500.00; phone width (375 px) bottom tabs and Menu button.
- **New tests:** `sales/tests/test_domain.py` (17, one property: totals = Σ qty × price exactly),
  `tests/db/test_sales.py` (12), `test_replay.py` (+1: steps 4 and 6 orders), generated RBAC cases for 7 new routes,
  `src/sales/sync.test.ts` (backoff, ACK, retryable vs refused, 401 pause, exactly-once, UUIDv7),
  `src/shell/registry.test.tsx` (every registry entry has a route and a sidebar link, role filtering, Coming page),
  `src/sales/sales.test.tsx` (save-first then Received only after ACK, repeat last order, Needs attention).
- **Decisions G1–G9 (approved; [ADR-0015](adr/0015-orders-prices-and-the-offline-outbox.md)):** G1 server prices,
  stale flagged not refused, price list items append-only; G2 whole packets, carton-aware stepper; G3 SO numbers on
  receipt; G4 UUIDv7 Idempotency-Key; G5 Dexie outbox + backoff sync + PWA shell; G6 minimal cache wiped at logout;
  G7 salesman lands on `/sales`; G8 Playwright in its own compose service on a fresh SIM tenant; G9 one web app with a
  grouped sidebar from one registry and the tour first.
- **Backend:**
  - migration 0009: `price_list_items` insert-only (trigger + grants, AH002)
  - `sales.domain` (pure): price list in force (customer list first, `known_at` for receipt-time answers), the order
    plan (whole positive packets, each item once, price = list price), exact totals (`Explained`), the stale rule,
    the request hash, `SO/26-27/000001`, new-price-list rules
  - `sales.service`: price lists (publish a version, list, in force), `catalog_for` (FG prices, packets per carton
    from the ACTIVE pack spec, available-today quantities for `stock.read`), `place_order` (assignment check) →
    `receive_order` (one savepoint: price check, key claim, number, order + lines, SUBMITTED history row with the
    stale note, audit, stored response), `get_order` (lines, timeline, stale detail with current prices),
    `list_orders` (row filter, `days`), `last_order`, `summary` ("ordered, not invoiced")
  - helpers: `catalog.names_for`, `recipe.units_per_carton`, `identity.route_order` / `is_assigned` / `display_names`
  - `python -m app.cli.seed_e2e`: a fresh SIM tenant with SALESMAN / ADMIN / OWNER logins and a random password
  - `make seed-demo` tops up an older DEMO factory (MP06 items, recipe, pack specs, card, tolerance; price list)
- **API** (all in the generated route × role tests): `POST /api/orders` (`order.create`, Idempotency-Key),
  `GET /api/orders?days=`, `GET /api/orders/{id}`, `GET /api/sales/catalog?customer_id=`,
  `GET /api/sales/customers/{id}/last-order`, `GET /api/sales/summary` (`order.read`), `GET /api/price-lists`
  (`customer.read`), `POST /api/price-lists` (`price.manage`); `GET /api/customers` now carries `route_order`.
- **Seeds and replay:** DEMO general price list v1 (`murukku_200g` ₹50.00) in `setup_section5`; the replay posts steps 4
  and 6 as SUBMITTED orders.
- **Web (one app, G9):** `src/guide/screens.ts` is the registry (group, icon, description, permission) for the sidebar,
  `src/routes.tsx` and the tour; `src/shell/` (AppShell with a Menu button at phone width, grouped Sidebar, Coming
  page, sign-in Gate, Sign-out with the unsent-orders dialog); `src/sales/` (Today, order screen with generated DEMO
  pouch art, carton-aware stepper, last quantity, available-today hint, sticky estimated total; My orders with Needs
  attention / On this phone / With the factory; order detail with the timeline and the confirmed `Explained` total;
  Summary; bottom tabs at phone width); the outbox (Dexie) and `sync.ts` (pure engine); the PWA manifest and service
  worker (production build); the sign-in page has one-tap DEMO login buttons and lands each role on its home; tour
  steps 4 and 6 rewritten to the real clicks; 48 px touch targets.
- **Dev stack:** the web container polls for file changes (`CHOKIDAR_USEPOLLING`): edits on the Windows host were not
  reaching Vite in Docker before.

## Done in MP07 (costing, the waterfall, Explain-this-number)
- **Gate met:**
  - 17, 18, 19 green (12/26); B-001's lot value = run cost exactly (₹5,855.00, FINAL).
  - Law 2 per run passes in `make integrity` (new check `production.run_value_mismatches`; run on the dev DB: OK).
  - The waterfall property test passes (`costing/tests/test_run_costing.py::test_waterfall_sums_exactly`): the parts
    always sum exactly to actual − standard, and any rounding is an explicit part. The NIT run needs none.
  - NIT's real order proven ahead of MP10 (`tests/db/test_costing.py::test_run_costs_in_nit_order_after_a_sale`, with a
    stand-in dispatch journal): sold 100 = ₹3,114.36, on hand 88 = ₹2,740.64.
  - No green row turned red; full suite with 500 state-machine examples.
- **Decisions F1–F8 (approved; [ADR-0014](adr/0014-costing-true-up-and-waterfall.md)):**
  - F1 run costs only on COMPLETED runs, each a COST_TRUE_UP at once (`production` owns `run_costs`)
  - F2 cumulative spread over wherever the lot is, on hand takes the remainder; zero-good share to SCRAP
  - F3 explicit "finalise run costs" → FINAL
  - F4 standard cost cards append-only (migration 0008), found by run date
  - F5 the waterfall rules (price, usage, yield, unallocated bulk, conversion spend, explicit rounding)
  - F6 sensitivity as of each issue; book value where a method has no answer (LAST before any purchase)
  - F7 overhead absorption deferred to MP11
  - F8 a plain sign-in page
- **Backend:**
  - `production`: `domain.plan_true_up` (pure), `service.record_run_cost`, `finalise_costs`, `costing_facts`,
    `run_value_mismatches`; the facts dataclasses live in `production.domain` so `costing.domain` stays pure
  - `costing`: `domain.py` (card lines, run cost, cost per good unit and per lot, waterfall, sensitivity; all
    `Explained`), `service.py` (cards create / list / `card_for`, `run_costing`), `api.py`
  - `valuation.sensitivity_at`; `ledger.lot_positions`, `lock_item_stores`, `journal_lines`, `journal_for`;
    `recipe.active_recipe_snapshot`
  - migration 0008: standard cost cards and lines insert-only
  - `python -m app.cli.record_fixture`: records the web test fixture from a fresh replay
- **API** (all in the generated route × role tests): `GET /api/runs/{id}/costing`, `GET/POST /api/standard-cost-cards`
  (`report.read` / `recipe.manage`), `POST /api/runs/{id}/costs` and `/costs/finalise` (`run.cost`).
- **Seeds:** the 200 g standard cost card (opening rates, conversion 1,200 + 600 per batch, ₹28.85) in `setup_section5`.
- **Web:** `<Num>` with the ⓘ "Explain this number" popover (formula, method, sourced inputs; Escape closes and
  returns focus); `/leaks` (completed batches) and `/leaks/{run}` (run cost, cost per good packet, standard, ranked
  waterfall with bars, checks worded as things to verify, method comparison); `/sign-in`; nav links. Exact decimal
  strings and BigInt only, no floats (`lib/decimal.ts`).
- **Tests:** backend 431 (was 386), web 26 (was 19), all passing. New: `production/tests/test_true_up.py` (6, one
  property), `costing/tests/test_run_costing.py` (9, one property), `tests/db/test_costing.py` (6), 25 generated
  RBAC cases, `src/leaks/leaks.test.tsx` (7, on a fixture recorded from a real replay).
- **Checks run:** ruff check / format clean, mypy --strict clean, import-linter 2/2 kept, `alembic check` clean
  (migration 0008 applied to the dev DB), float grep clean, web typecheck / lint (no warnings) / build clean,
  benchmark 12/26 (oracle 10/10), `make integrity` OK.
- **Not checked live in the browser:** the dev DB's DEMO logins belong to the DEMO factory, which has no runs (it was
  seeded before MP06), and the benchmark tenants that have runs have no logins. Adding the DEMO auditor to a
  benchmark tenant was blocked by the session's permission rules, so the page is verified by the vitest tests on a
  recorded real API response, not on :5180. The API container was not restarted on the new code.

## Done in MP06 (recipe, pack specs and the atomic production run)
- **Gate met:**
  - A failure injected at the third write of a completion persists nothing
    (`tests/db/test_production.py::test_failure_at_the_third_write_persists_nothing`), and so does a failure at
    **every** write in turn (`::test_failure_at_any_write_persists_nothing`): no journal, lot, pack-line change,
    sample, oil session, status change, audit row or balance change is left, and a clean retry then succeeds.
  - FG 238; yield −6.00%, oil +5.00% and pouch +3.19% flagged (benchmark 4, 6, 7, 20 green: 9/26).
  - The 500 g pack spec works from seed data with no code change (`::test_a_500g_run_from_seed_data`: 80 expected,
    78 good, yield −2.50% not flagged, 7 cartons + 8 loose); a 200 g + 500 g split works too.
  - `tests/db/test_replay.py` unchanged and green: B-001 ₹4,055.00, WIP 0, pouches ₹765.00. No green row turned red.
- **Decisions E1–E4 (approved; [ADR-0013](adr/0013-production-run-and-variance-engine.md)):**
  - E1: variances, packing and mass balance computed on read from the frozen snapshot (`variance_results` unused)
  - E2: flag = beyond tolerance and unfavourable, strict, on the unrounded %; display half up to 2 dp
  - E3: runs B-001…; lot no = run no (-A / -B with several pack lines, ordered by pack spec code); issues
    MI/26-27/000001
  - E4: a zero-good pack line writes its share off to SCRAP (as the bulk item, valued); a reason is required
- **`recipe`:** recipes and pack specs with versions DRAFT → ACTIVE → RETIRED (activating retires the old ACTIVE
  version, audited). Checks: RAW recipe lines, PACK pack lines, BULK output in grams, FG pack output. Snapshots via
  `recipe_snapshot` / `pack_snapshot`.
- **`production`:**
  - `domain.py` (pure): expected bulk and units; allocation (over-allocation refused, unallocated shown); batch and
    flexible standards; the batch view of packaging; yield; E2 flags; packing (divmod); mass balance with giveaway;
    the value split (last line takes the remainder); the completion journal plan; returns at the run's own average.
    Every figure is an `Explained` value. A test reads its source: no product, pack size or carton size in it.
  - `service.py`: `create_run`, `start_run` (freezes snapshots and the effective-dated tolerance), `issue_materials`
    (ISSUE RAW_STORE → WIP at WAC; RETURN at the run's own issued average), `complete_run` (one savepoint; the
    Idempotency-Key is checked before the status, so a retried submit replays), `run_analysis`, `get_run`,
    `list_runs`, `completed_run_wip_mismatches` (S6), `mass_balance_gaps`.
- **Kernel:** `app/core/effective_settings.py` (`value_on`, `decimal_on`, `put`; numbers stored as decimal strings).
  Also `ledger.service.lot_no`.
- **API** (all covered by the generated route × role tests):
  - `GET/POST /api/recipes`, `POST /api/recipes/{id}/versions`, `POST /api/recipes/versions/{id}/activate`, and the
    same four for `/api/pack-specs` (`recipe.manage` to change)
  - `GET/POST /api/runs`, `GET /api/runs/{id}`, `POST /api/runs/{id}/start` and `/issues` (`run.start`),
    `/complete` (`run.complete`); decimals as strings; Idempotency-Key on issues and completion
  - Deviation from the plan: the GET routes need `report.read`, not `recipe.manage`, so auditors can read the
    standards behind a variance.
- **Seeds:** `setup_section5` adds `murukku_bulk`, `murukku_500g`, `pouch_500g`; recipe MURUKKU v1 (40 kg / 10 L /
  1.2 kg, bulk yield 200 × 200 g); pack specs MURUKKU-200G v1 (pouch 1, carton 0.05, 20 per carton, 90 days) and
  MURUKKU-500G v1 (pouch_500g 1, carton_20 0.1, 10 per carton), all ACTIVE; `variance_tolerance_pct` = 3 from
  2026-04-01 (the oracle's `variance_tolerance_percent`). `make seed-benchmark` run on the dev DB: OK.
- **`make integrity`** adds S6 (the WIP of every completed run is zero per item, and the run has a completion
  journal) and reports each run's mass-balance gap without failing. Run on the dev DB: integrity OK; two B-001 runs
  show the 2.4 kg gap.
- **Tests:** 386 in total (was 279), all passing in Docker with the full 500-example state machine (4 min 29 s). New:
  - pure: `production/tests/test_domain.py` (16, with two Hypothesis properties: the value split is exact, and the
    completion conserves quantity and value), `recipe/tests/test_domain.py` (11)
  - PostgreSQL: `tests/db/test_production.py` (10: the NIT run, atomicity ×2, versions, 500 g, mixed split + E4,
    idempotency, returns, refusals, the API), plus the generated RBAC cases for the 13 new routes
  - Bugs the tests found, fixed: a completion replay with the same Idempotency-Key was refused because the status
    check ran before the key lookup; `dict()` over a SQLAlchemy result in `list_runs`; the multi-row sample insert
    passed `now()` as a parameter.
- **Checks run:** ruff check / format clean, mypy --strict clean, import-linter 2/2 kept, `alembic check` clean (no
  migration in MP06), float grep clean, benchmark 9/26 (oracle 10/10), `make integrity` OK.
- **Not checked live:** the API container on :8180 was not restarted against the new code; the routes run through
  the TestClient in `test_run_through_the_api`.

## Done in MP05 (valuation, procurement and lots)
- **Gate met:**
  - WAC = ₹43.125/kg after the NIT receipt (assertion 16 green, 5/26).
  - A duplicate submit gives one receipt (`test_duplicate_submit_gives_one_receipt`: 201 then 200, one journal).
  - FIFO layers are consumed oldest first (property `test_fifo_consumes_the_oldest_layers_first`).
  - Value is conserved: the property `test_wac_pool_drains_to_exactly_zero` checks issued + remaining = received
    after every issue and a drained pool at exactly (0, 0).
  - No green row turned red.
- **Decisions D1–D4 (approved; [ADR-0012](adr/0012-valuation-from-the-ledger.md)):**
  - D1: the WAC pool is read from `inventory_balances` at RAW_STORE + PACK_STORE under the per-(item, store) lock
  - D2: FIFO and last price are replayed from the ledger history and never post
  - D3: OPEN-LOT at the standard ₹28.85, derived from the inputs by `costing.domain.standard_cost`
  - D4: supplier lots go to `lots` and the receipt line; raw stock stays lot-less
  - `item_cost_state` and `valuation_layers` are left unused
- **`valuation`:**
  - `domain.py` (pure): `proportional_value`, `unit_cost`, `line_value`, and the `ValuationMethod` interface with
    WAC / FIFO / LAST and `gain_value` (WAC, else last price, else ₹0 as NO_COST_YET)
  - `service.py`: `pool`, `history`, `wac` (Explained), `issue_value` (locks first), `sensitivity`, `gain_value`,
    `post_opening`, `valuation_summary`
- **`procurement`:**
  - suppliers
  - purchase receipts posted in one savepoint: gapless `GRN/26-27/000001`, DRAFT → POSTED, a SUPPLIER → store
    journal at accepted qty × rate, audit row
  - rejected qty and freight recorded, not stocked (freight shown separately in the register)
  - supplier lot records
  - reversal by mirror journal → REVERSED
  - the purchase register (totals count POSTED receipts)
  - `receipt_value_mismatches` for integrity
- **Kernel:** `app/core/idempotency.py` (claim / complete / request_hash) is now shared by ledger and procurement, and
  `app/core/calendar.py` holds `business_date` and `financial_year`.
- **API** (all covered by the generated route × role tests):
  - `POST /api/purchases/receipts` (`receipt.post`, Idempotency-Key header, decimals as strings: a JSON number is a
    422)
  - `POST /api/purchases/receipts/{id}/reverse`
  - `GET /api/purchases/receipts/{id}`
  - `GET /api/purchases/register`
  - `GET /api/suppliers`
  - `GET /api/stock/valuation` (`report.read`: a salesman gets 403)
- **Seeds:**
  - `make seed-benchmark` creates a fresh BENCHMARK tenant with the section 5 master data and the valued opening
    stock, and prints its code.
  - `make seed-demo` now also adds, on the first run only, to the LIVE DEMO organization: the items, `SUP-DEMO`,
    `RET-A` (TN) and `DIST-B` (KA) with fictional DEMO GSTINs, salesman A → RET-A and salesman B → DIST-B, and the
    opening stock.
  - The master data is written as `aahar_app`, because the owner bypasses RLS.
  - Run on the dev DB, then checked live on :8180:
    - admin sees the valuation (flour ₹42.000000/kg before any purchase)
    - salesman A sees only RET-A, and finished-goods stock without values; 403 on the valuation
- **`make integrity`** adds the receipt-value check; run on the dev DB: all PASS.
- **The state machine** now values outgoing lines with `valuation.domain.proportional_value` instead of its own copy.
- **Replay values checked against ledger.md** (`tests/db/test_replay.py`):
  - flour ₹5,175.00, oil ₹2,730.00, spice ₹760.00, pouches ₹765.00, cartons ₹315.00
  - WIP 0, OPEN-LOT 50 / ₹1,442.50, B-001 188 / ₹4,055.00
  - flour 40 kg sensitivity: WAC ₹1,725.00, FIFO ₹1,680.00, LAST ₹1,800.00
- **Tests:** 279 in total (was 210), all passing in Docker. New in MP05:
  - pure: `valuation/tests/test_domain.py`, `procurement/tests/test_domain.py` (with the financial year and request
    hash), `costing/tests/test_domain.py` (standard cost)
  - Hypothesis found a rounding slip in a test's own expected value (half-even vs the books' half-up), fixed in
    the test; import-linter caught a test importing a higher layer, moved to `costing/tests`
  - PostgreSQL: `tests/db/test_procurement.py`, `tests/db/test_replay.py`
  - generated RBAC cases for the 6 new routes
- **Checks run:** ruff check / format clean, mypy --strict clean, import-linter 2/2 kept, `alembic check` clean (no
  new migration in MP05), float grep clean, benchmark 5/26 (oracle 10/10), `make integrity` OK.

## Review of MP04 (2026-11-21, before MP05)
Three defects found and fixed, each with a test:
1. **Salesmen saw rupee values.** `stock.read` exists for the salesman's "available today" hint, but both stock
   routes returned stock values, which are cost (margin) data. Salesmen now get quantities only
   (`ledger/api.py::_for`; `test_stock_api_balances_and_ledger` asserts no `"value"` key reaches a salesman).
   docs/security.md and ADR-0011 §5b updated.
2. **Deadlocks were 500s.** Two journals that touch the same two balance rows in opposite order (a receipt and its
   reversal) can deadlock; PostgreSQL rolls one back with 40P01. 40P01 and 40001 now become `409 retry` (nothing was
   written, so a retry is safe). `tests/test_pg_errors.py`.
3. **A duplicate item code was a 500.** `catalog.create_item` now runs in a savepoint and reports `item_code_taken`;
   the caller's transaction stays usable. `test_duplicate_item_code_is_a_clear_error`.
- Re-run after the fixes: 210 tests pass (204 + 6), ruff / format / mypy --strict / import-linter clean, benchmark
  4/26 with oracle 10/10.
- Looked at and left as is: idempotency under concurrent duplicates (the second insert waits on the first and then
  replays), savepoint rollback of consumed reservations, running balances under `limit` (the response says
  `truncated`), cross-tenant ids (RLS returns 404 or empty).

## Done in MP04 (units and the double-entry stock ledger)
- **Gate met:**
  - The Hypothesis `RuleBasedStateMachine` (`tests/db/test_ledger_state_machine.py`) ran **500 examples clean**
    against PostgreSQL (217 s locally under Docker Desktop; 2,393 accepted steps and about 2,700 refusals of 6 kinds).
  - Benchmark stock assertions 1–3 and 15 are green: scoreboard **4/26**.
- **Units (`uom.domain`, pure):**
  - Converting to base units (g, mL, piece) only multiplies, so it is exact. More than 6 dp, or a fractional piece,
    is refused, never rounded.
  - Back to kg / L / cartons is display only. `split_into_cartons` is divmod (188 → 9 + 8).
  - A carton's size comes from the pack spec version's `units_per_carton`. Mass ↔ volume needs the item's density
    row in `uom_conversions`.
  - `uom.service` reads densities; a test keeps the seeded `uoms` equal to `domain.SYSTEM_UNITS`.
- **Journal rules (`ledger.domain.build_journal`, pure):**
  - converts every line to base units
  - Σ qty per item = 0 and Σ value = 0
  - the line role is derived from the signs
  - each kind must cite its own source document type
  - reason for ADJUSTMENT / REVERSAL, approver for ADJUSTMENT, a lot on lot-tracked items
  - values already rounded to paise; floats refused
  - incoming lines ordered first
  - the request hash for idempotency is unit-independent (60 kg and 60000 g are the same request)
- **Posting (`ledger.service`):**
  - `post()` runs in a savepoint and never commits (the caller's use case commits once):
    - claim the Idempotency-Key
    - per-(item, store) lock
    - insert the journal and lines
    - consume reservations
    - fire the deferred balance triggers now (`SET CONSTRAINTS … IMMEDIATE`)
    - check available ≥ 0
    - audit row
  - `reverse()` posts the exact mirror; a reversal is not reversible and a journal is reversed once.
  - `reserve()` checks available to promise (non-expired lots minus active reservations) under the lock;
    `release()` needs a reason.
  - DB refusals (AH001–AH005, 23514 by constraint, 23505, 23503, 42501) become clear errors via
    `app/core/pg_errors.py`. New `ConflictError` (409).
  - Also: `create_lot`, `ensure_locations` (the 12 standard locations), `catalog.service.create_item / units_for`,
    `identity.service.create_scratch_tenant` (BENCHMARK / SIM only).
- **Read-only stock API:**
  - `GET /api/stock/balances`: stores by default, `include_virtual`, filters
  - `GET /api/stock/ledger`: item / location / lot / date filters, opening balance, running balance per item, the
    source document per row
  - Both need `stock.read`; the generated route × role tests cover them. Checked live on :8180: auditor login →
    200 on both, no cookie → 401.
- **`make integrity`** adds law 1 (and law 2 per journal) re-summed from the lines, and `inventory_balances` rebuilt
  from `stock_lines` and diffed (diff only, never repair). Run on the dev DB: all PASS.
- **State machine:**
  - Steps: receipts, opening lots, issues and returns, run completions with scrap, dispatches (some consuming a
    reservation), adjustments, reversals, reserve / release, Idempotency-Key replays and 409s, float receipts.
  - Quantities arrive in mixed units (g / kg, mL / L, piece / packet / carton of 20).
  - A model predicts every outcome. After every step: the projection equals the model and a rebuild, law 1 holds,
    no store is negative, available ≥ 0, and no float is read back.
  - Refused steps must leave the database unchanged.
  - A vacuity guard asserts that accepted steps and refusals (negative stock, floats) both really happened.
- **Benchmark replay:** J0 opening, J1 purchase, J2 issue and J3 run output through `ledger.service`, reading only
  the oracle's `inputs`. The CI benchmark job now has a PostgreSQL 16 service and runs the migrations first.
- **Tests:** 204 in total at MP04 close (was 134; 210 after the review), all passing in Docker. New in MP04:
  - pure: `uom/tests/test_domain.py`, `ledger/tests/test_domain.py`
  - PostgreSQL: `tests/db/test_ledger_service.py`, `test_uom.py`, `test_ledger_state_machine.py` (1 test × 500
    examples), plus 10 new generated RBAC cases (2 routes × 5 roles)
- **Checks run:** ruff check / format clean, mypy --strict clean, import-linter 2/2 kept, `alembic check` clean
  (no new migration in MP04), float grep clean, benchmark 4/26 (oracle 10/10), `make integrity` OK.

## Done in MP03 (identity, RBAC, hash-chained audit)
- **Gate met:**
  - Generated authorisation tests over every guarded route × all 5 roles pass (35 cases today; new routes join
    automatically).
  - The auditor gets 403 on every mutation.
  - An edited, deleted or tail-deleted audit row is detected (`tests/db/test_audit.py`, `make integrity`).
- **Sessions ([ADR-0010](adr/0010-cookie-sessions-and-rbac.md), [docs/security.md](security.md)):**
  - Argon2id passwords.
  - Access token: 15-minute HS256 JWT in an httpOnly cookie (SameSite=Lax, path /api). The session row is checked on
    every request, so logout and deactivation act immediately.
  - Rotating refresh token: httpOnly, SameSite=Strict, path /api/auth, stored as SHA-256. Reusing a spent token
    revokes the session.
  - Login rate limit: 5 per email or 30 per IP in 15 minutes give 429 (`login_attempts`).
  - Unknown email and wrong password give the same 401.
  - Users with several organizations choose one at login.
- **Permission matrix in code:** `identity/domain.py`, 28 permissions split into read and mutating. Mirrored into
  `role_permissions` by migration 0007; a test keeps them equal.
- **`require(perm)` and `require_login()` dependencies:** a route without a guard (and not on the explicit public
  list) fails CI.
- **Salesman row filter:** assigned customers and own orders only (`GET /api/customers`, `GET /api/orders`).
- **RLS scope from the auth dependency:** the same DB session as the route. The scope is re-applied after every
  commit through SQLAlchemy `after_begin` (why not middleware: docs/security.md).
- **Correlation-id middleware:** `X-Correlation-Id` echoed on responses and stored on audit rows.
- **`audit.record()`:**
  - locks `audit_chain_heads` (no forked chains under concurrency; a test runs 3 writers × 10 rows)
  - redacts secret-looking keys and refuses floats
  - `audit.verify()` also uses the head, so deleting the newest rows is caught
  - `GET /api/audit/log` and `GET /api/audit/verify` serve the auditor and the owner
- **Migration 0007:**
  - tables `auth_sessions`, `refresh_tokens` (RLS) and `login_attempts`; column `memberships.is_active`
  - RLS on `users` (yourself plus members of your organization), so other tenants' password hashes are unreadable
  - `aahar_login_lookup(email)`, a SECURITY DEFINER function executable only by `aahar_app`
  - the `role_permissions` seed
- **CLIs:**
  - `make seed-demo`: LIVE `DEMO-FACTORY` organization with 6 DEMO logins (2 salesmen, admin, production, auditor,
    owner), passwords from `.env`, listed in the README
  - `make integrity`: audit chain for every organization; the laws are listed as "not built yet (MP04/MP11)", never
    as passing
- **Error envelope:** now also covers 401 / 403 / 429, framework 404/405 and request validation (422).
- **Tests:** 134 in total, all passing in Docker (107 PostgreSQL-backed, 27 pure). New in MP03: `test_auth.py` (13),
  `test_rbac.py` (6 + 35 generated), `test_row_filter.py` (2), `test_audit.py` (7), plus pure tests in
  `app/modules/audit/tests` and `app/modules/identity/tests`.
- **Checked live** against the running API on :8180: DEMO admin login, then `/me` as ADMIN; owner-only and
  auditor-only routes give 403; no cookie gives 401.
- **Checks run:** ruff check/format clean, mypy --strict clean (69 files), import-linter 2/2 kept, `alembic check`
  clean, float grep clean, benchmark runs (0/26, oracle 10/10), `make integrity` OK.

## Review of MP00, MP01 and MP02 (2026-11-21, before MP03)
- **MP00:** deliverables are present and match the prompt:
  - traceability covers sections 2–10
  - assumptions A1–A6 and G1–G16
  - 26 strict-xfail assertions plus the oracle-integrity checks
  - CI with lint, tests and benchmark, and the README badge
  - pre-commit, ADR-0000 and ADR-0001
- **MP00 findings fixed:**
  - Traceability still named tables that MP01 renamed (`run_issues`, `run_outputs`) and had placeholder test ids
    for RBAC, row filter and audit. Now updated to the real ones.
  - The error envelope covered only domain errors. Framework 404/405, validation errors and auth errors returned
    FastAPI's default `{"detail": ...}` shape. Fixed in `core/errors.py`.
  - The README status still said "scaffold (MP00)".
- **MP01:** reviewed in the MP02 session; its 9 schema findings and the lot-of-item finding were fixed in MP02.
  Nothing new found.
- **MP02 findings fixed in migration 0006 (`0006_mp02_review_hardening.py`):**
  1. **Cross-tenant leak:** PostgreSQL runs BEFORE triggers before the RLS WITH CHECK. The SECURITY DEFINER
     allocation guard could therefore read another tenant's invoice number or status and leak it in its error
     message, for a row stamped with that tenant's id. A same-org trigger now fires first (42501); see
     `test_rls.py::test_allocation_for_other_org_rejected_before_its_guard_runs`.
  2. **LIVE organizations:** the app role could create LIVE organizations. Now only BENCHMARK and SIM; the LIVE
     factory is seeded by the owner.
  3. **Migration tests:** they hard-coded revision 0005. Now generic: every revision is downgraded and re-applied
     one step at a time, comparing tables, triggers, policies and functions.
  4. **Test count:** this file and the MP02 commit message said "37 new DB tests"; the real number was 42 (53 total
     minus 11 pre-existing). Corrected below. The pushed commit message is left as is.

## Done in MP02 (schema, migrations, database-enforced guards)
- **Gate met:** an unbalanced journal is rejected by PostgreSQL itself at commit (SQLSTATE AH001,
  `tests/db/test_ledger_guards.py::test_unbalanced_journal_rejected`).
- Models for 67 tables, one `models.py` per owning module, plus kernel tables in `app/core/models.py`. Registry:
  `app/db_models.py`. Column types in `app/core/db.py`: `Money` NUMERIC(14,2), `Qty` / `UnitCost` NUMERIC(18,6),
  `Pct` NUMERIC(9,4) ([ADR-0008](adr/0008-money-as-numeric-rupees.md)).
- Alembic, 5 revisions (`backend/migrations/versions/`):
  - 0001: `btree_gist` and the non-owner login role `aahar_app`
  - 0002: schema (autogenerated, reviewed)
  - 0003: guards and triggers
  - 0004: RLS on 61 org-scoped tables plus least-privilege grants
  - 0005: seed of 5 roles, 28 permission codes, 6 system units
- Guards ([ADR-0009](adr/0009-database-enforced-ledger-guards.md)):
  - deferred balance triggers (Σ qty per item, Σ value per journal, ≥ 1 line)
  - line-role sign CHECKs
  - balances maintained by a trigger; the app can only read them
  - store-not-negative CHECK
  - insert-only ledger, invoice lines, payments and allocations, credit notes
  - invoice POSTED → CANCELLED only, with a reason, not if paid
  - run snapshots frozen; completed runs change only cost status or get reversed
  - receipt and BOM-version lines frozen after DRAFT
  - period locks on journals, invoices, credit notes, payments
  - allocations ≤ payment and ≤ invoice
  - gapless `aahar_next_doc_number()`
  - EXCLUDE no-overlap on effective-dated settings and tax rules
  - composite same-org FKs, and lot-of-item FKs
- MP01 review fixes applied to the schema, `erd.mmd` and `ledger.md`:
  - codes and numbers unique per organization
  - balance key allows "no lot" (NULLS NOT DISTINCT)
  - `audit_log` keyed (org, seq), plus `audit_chain_heads`
  - `location_kind` copied onto balances so S1 is a CHECK
  - `payments.unallocated` dropped (computed instead)
  - `credit_note_lines` and `credit_note_tax_lines` added
  - `posting_date` business date drives period locks
  - line roles defined: IN / OUT / SCRAP_IN / VALUE_ONLY
  - raw-material WIP lines carry no lot (a lot belongs to one item)
- Tests: 42 new DB tests, 53 backend tests in total, all passing in Docker. They include:
  - migrations up, down one step, up again; full down and up
  - `alembic check` (models match migrations)
  - J0–J8 of the NIT replay as raw journals: flour 120 kg / ₹5,175.00, oil 19.5 L, pouches 306,
    FG 88 / ₹2,740.64, CUSTOMER ₹4,556.86, B-001 ₹5,855.00
- Wiring:
  - `make migrate` = `alembic upgrade head`
  - compose runs the API as `aahar_app`, migrations as the owner, and DB tests with `AAHAR_REQUIRE_DB=1`
  - CI backend job now has a Postgres 16 service, runs `alembic upgrade head && alembic check`, and runs the DB tests
  - new setting `AAHAR_APP_DB_PASSWORD` (in `.env.example`)
- Checks run: ruff check/format clean, mypy --strict clean, import-linter 2/2 kept, float grep clean, benchmark runs (0/26).

## Done in MP01 (design only; no code, no migrations)
- `docs/architecture/erd.mmd`: 64 entities with keys and cardinalities (renders in Mermaid 11). Corrected in MP02 (see above).
- `docs/architecture/invariants.md`: the 4 conservation laws + 22 invariants, each with where it is enforced and its test id.
- `docs/architecture/ledger.md`: locations, journal kinds, the journal table for every NIT step with quantities and
  values, value and rounding rules. Replayed with `Decimal` before writing: every journal balances per item and in
  value, no store goes negative, B-001 = ₹3,114.36 sold + ₹2,740.64 on hand = ₹5,855.00, COGS A ₹4,556.86.
- `docs/architecture/bom.md`: recipe vs pack spec, drivers, formulas, 200 g / 500 g / mixed-split examples,
  the zero-code 500 g change.
- ADR-0002 to ADR-0007, Accepted on approval (2026-11-21). `docs/architecture/open-questions.md`: Q1–Q8 with recommendations.
- CI actions bumped (checkout v5, setup-python v6, setup-node v5) to clear the Node 20 deprecation warnings.

## Done in MP00
- Repo initialised and pushed to GitHub (S-Mitun/AaharOS); first CI run green. Source docs placed byte-identical (sha256 checked):
  `CLAUDE.md`, `docs/MASTER_PACK.md`, `docs/PROBLEM_STATEMENT.md`, `benchmark/expected_results.yaml`,
  `docs/reference/MASTER_PACK_v1.md`.
- Backend skeleton: `app/core` kernel (config, db, money, Explained, errors, oracle loader), 21 module packages with
  owner MP + allowed deps, FastAPI `/health`, public `GET /api/guide/expected` and `/api/guide/scoreboard`.
- import-linter contracts (layering + core-is-kernel), ruff, mypy --strict, pytest.
- Benchmark: 26 assertions, oracle-integrity tests, scoreboard runner (`make benchmark`) writing `benchmark/results/latest.json`.
- Web: Start-here page, 11-step guided tour, Guide side panel on every page; all numbers from the oracle API.
- Docker Compose (postgres:16, api, web), Makefile, CI workflow, pre-commit, .env.example (DEMO).
- Docs: architecture overview + 4 pipelines, requirements traceability, assumptions (A1–A6, G1–G16), ADR-0000, ADR-0001.

## Decisions (ADRs)
- [ADR-0000](adr/0000-source-precedence.md) source precedence; v1 vs v2 pack conflicts resolved for v2.
- [ADR-0001](adr/0001-modular-monolith-postgres-ledger.md) modular monolith, shared kernel `app/core`, layered modules,
  added `judge` module, everything in Docker.
- Commands: one Makefile, all targets run in Docker; Windows needs `winget install ezwinports.make` once.
- Web styling: plain CSS with tokens (no Tailwind yet). Revisit only if a later MP needs it.
- MP01 (accepted, see ADRs 0002–0007 and open-questions.md): real `WIP` location between issue and completion;
  scrap carries quantity, not value; WAC as a pooled (qty, value) with no rounded unit cost; late run costs via a
  value-only true-up; FG lots at actual cost, FEFO; a new BENCHMARK tenant per replay (no deletes).
- MP02: [ADR-0008](adr/0008-money-as-numeric-rupees.md) money NUMERIC(14,2) rupees, quantities and unit costs
  NUMERIC(18,6). [ADR-0009](adr/0009-database-enforced-ledger-guards.md):
  - balances are maintained by a DB trigger (pulled forward from MP04)
  - guard errors use SQLSTATE AH001–AH005
  - the API runs as the non-owner role `aahar_app` so RLS applies
  - composite same-org and lot-of-item FKs
- MP03: [ADR-0010](adr/0010-cookie-sessions-and-rbac.md):
  - cookie sessions with rotating refresh tokens and reuse detection
  - the permission matrix in code, mirrored in `role_permissions`
  - the org scope set by the auth dependency, not middleware
  - per-org deactivation
  - failed logins in `login_attempts`, not the audit chain (ADR-0007 amended)
- MP04: [ADR-0011](adr/0011-ledger-posting-rules.md):
  - `post()` runs in a savepoint and never commits; the deferred balance triggers fire inside it
  - the idempotency hash covers the journal's meaning in base units
  - **deviation from the approved plan:** the per-(item, store) lock is a transaction advisory lock, not
    `SELECT … FOR UPDATE` on `inventory_balances`. FOR UPDATE needs UPDATE privilege, and the app role may only read
    the projection (ADR-0009). Same serialisation; proven by the parallel-approval test.
  - a movement that would eat into active reservations is refused, adjustments included
  - the benchmark replay posts at ₹0.00 as a labelled stand-in (approved; replaced by valued postings in MP05)
- MP11: [ADR-0018](adr/0018-reports-gst-close-and-evidence.md): K1–K9 (report engine, reports, GST export and law 4,
  law 3 with flagged gaps, close and reopen with history, evidence pack, Tally XML, bank statement, Reports screen).
- MP10: [ADR-0017](adr/0017-tax-invoices-dispatch-and-collections.md): J1–J10 (tax engine, invoices, cancel and
  credit notes, document, settings, FEFO dispatch, mock e-way, collections, NIT-order replay, screens).
- MP09: [ADR-0016](adr/0016-order-approval-reservations-and-shortage-options.md): H1–H10 (approval under locks,
  partial + backorder, release on reject / cancel, stale choice, amendments, wait, credit, races, the inbox).
- MP08: [ADR-0015](adr/0015-orders-prices-and-the-offline-outbox.md): G1 server prices and stale flag, G2 whole
  packets, G3 SO numbers on receipt, G4 UUIDv7 keys, G5 outbox + sync + PWA, G6 device cache wiped at logout, G7
  role landing, G8 Playwright on a SIM tenant, G9 one app with one screen registry.
- MP07: [ADR-0014](adr/0014-costing-true-up-and-waterfall.md): F1 run costs after completion as true-ups, F2
  cumulative spread, F3 explicit FINAL, F4 append-only cards by run date, F5 waterfall rules, F6 as-of-issue
  sensitivity, F7 overheads deferred, F8 a plain sign-in.
- MP06: [ADR-0013](adr/0013-production-run-and-variance-engine.md): E1 variances on read from the frozen snapshot,
  E2 strict flag on unfavourable only, E3 numbering, E4 zero-good write-off to SCRAP; returns at the run's own
  average; reads of recipes and runs need `report.read`.
- MP05: [ADR-0012](adr/0012-valuation-from-the-ledger.md) (amends ADR-0004):
  - D1: the WAC pool is read from the projection
  - D2: FIFO / LAST are replayed from the history
  - D3: the opening FG lot is at the derived standard
  - D4: supplier lots are recorded, not stocked
  - receipts value accepted qty × rate; freight is excluded; decimals arrive as strings
- Commits use the GitHub no-reply email (repo-local git config) because the account blocks pushes exposing a private email.
- Host ports: web **5180**, API **8180**, Postgres **5442** (Vite `strictPort`). Other local projects use
  AgriVision 4280-81, 5000, 5280-81, 6379, 8080, 8100-01 and Nexora 5173, 8000. Container-internal ports are unchanged.

## 7-day schedule (deadline set by the user on 2026-11-21: everything incl. a hosted demo within 7 days)
| Day | MPs | Gate |
|---|---|---|
| 1 | MP00, MP01, MP02 | scaffold + CI; ERD approved; migrations + zero-sum trigger green |
| 2 | MP03, MP04, MP05 | RBAC + audit chain; ledger state machine; WAC → 1–3, 15 (stock), 16 |
| 3 | MP06, MP07 | production run + costing → 4, 6, 7, 17–20, 22 (run) |
| 4 | MP08, MP09, MP10 | salesman PWA, inbox, tax/invoice/dispatch/payments → 5, 8–14, 21, 25 |
| 5 | MP11, MP12 | reports, close, planner → 23, 24, 26 → **26/26** |
| 6 | MP15 (Judge Mode, Tamil), MP13 light, MP17 + deploy | hosted demo URL live |
| 7 | MP18, MP19 (+ MP14 / MP16 only if time) | README, design note, video script, red-team |

Cut line, in order: MP14 transport → MP16 ML models (keep simulator + SPC) → MP13 radar.
Never cut: MP00–MP12, Judge Mode, MP17, MP18.

## Known gaps / risks
- `make` is not installed on this Windows machine yet; until it is, run the `docker compose …` lines from the Makefile.
- CI runs on GitHub (S-Mitun/AaharOS) from the first push.
- Hosting provider for the demo URL not chosen (MP17; needs the user's account; free-tier limits to be documented).
- The 7-day plan is tight. Correctness first: no differentiator ships while a benchmark row is red.
- `sim`, `ml-eval` still exit 1 with "not built yet". `e2e` works since MP08 (needs `make up`). `migrate`, `seed-demo`, `seed-benchmark`,
  `benchmark` (needs a migrated DB since MP04) and `integrity` (audit chain, law 1, balance rebuild, receipt
  values) work.
- Web dev server prints React Router v7 future-flag warnings (harmless).
- **State-machine cost:** 500 examples take about 3.5 minutes under Docker Desktop on Windows, more than the
  1–2 minutes the plan estimated. CI on Linux should be faster (not measured yet). `AAHAR_SM_EXAMPLES=60` runs a
  quick version locally.
- **Reserved stock cannot be adjusted away** without releasing the reservation first (ADR-0011). If that is too strict
  for real count losses, MP09 can add an "adjust and release" use case.
- **Benchmark tenants accumulate:** every `make benchmark` and `make seed-benchmark` creates a fresh BENCHMARK
  organization in the dev DB (ADR-0006: no deletes). Judge Mode (MP15) will show only the newest.
- **Unused tables:** `item_cost_state` and `valuation_layers` are no longer written (ADR-0012). Drop them in a later
  migration together with `erd.mmd`.
- **No supplier or item management routes yet:** suppliers and items come from the seeds. Adding them through the UI
  needs routes (MP09 / MP17) and a permission decision (there is no `supplier.manage` yet).
- **Raw-material expiry is recorded, not enforced:** supplier lot dates are stored, but raw stock is lot-less (D4),
  so FEFO for raw materials waits for MP13.
- **No stock-posting route:** posting happens inside receipts (MP05), runs (MP06) and dispatches (MP10). No HTTP
  route moves stock without its source document.
- **Fill-weight samples are per run** (`fill_weight_samples` has no pack-line column), so they are accepted only for
  single-pack-line runs. A migration adding `run_pack_line_id` lifts this (MP13, or when the tablet UI needs it).
- **Quantity per good unit must be exact at 6 dp:** a carton of 24 (1/24) is refused. The seeds use 20 and 10 per
  carton. A per-carton driver would lift it (MP17 if needed).
- **Run reversal not built:** `run.reverse` is in the matrix, but no route or service reverses a completed run yet.
- **Runs are numbered at DRAFT:** deleting a DRAFT run leaves a gap in B-numbers (run numbers are not tax documents;
  material-issue numbers stay gapless).
- **Mass balance is reported, not yet a pass/fail law:** the rule for an acceptable gap is MP11.
- **Only the 200 g pack has a standard cost card:** the inputs give no rate for `pouch_500g`, so 500 g runs show
  their run cost but no waterfall (the page says why). Add a card through `POST /api/standard-cost-cards`.
- **Multi-pack waterfalls need matching cards:** a run whose pack lines' cards disagree on ingredient rates or
  conversion gets no single waterfall (a reason is shown).
- **Overheads are not absorbed** (F7): costing is direct cost; MP11 reports absorbed overheads.
- **The dispatch in `test_costing.py` is a test stand-in** (a raw DISPATCH journal); MP10 builds the real dispatch,
  replays step 5 before step 8, and turns assertion 22 green.
- **Salesman (MP08) and admin inbox (MP09) are built:** other roles land on `/leaks`; their screens come with MP10
  (invoices), MP11 (reports). Unbuilt screens show an honest "Coming in MPxx" page.
- **ADMIN cannot create orders** (`order.create` is SALESMAN and OWNER): phoned-in orders are entered by the owner or
  the salesman for now.
- **Credit notes are value-only:** returned goods (stock back, food safety) are MP13.
- **GSTR-1 export is for review only** (portal-shaped JSON, never filed); amendments (tables 9A/9C) and e-invoicing
  are out of scope.
- **Reports run synchronously;** very large ranges may be slow (the stock ledger caps at 2,000 movements per view).
- **Tally XML uses default ledger names** ("Sales GST (local)", "CGST Output" …); map them to the real ledgers on import.
- **The B2CL threshold, bank margins and e-way thresholds are DEMO settings;** set the real figures.
- **No payment reversal (bounced cheque) document yet;** payments and allocations are insert-only.
- **The invoice PDF is the browser's print-to-PDF** of a server-rendered page; a server-made PDF file is MP17.
- **WhatsApp / email share a text summary only** (no public PDF link, nothing sent by the server).
- **Intra-state e-way threshold is a DEMO ₹50,000**; it varies by state: set the real figure in settings.
- **HSN 21069099 and 5% are DEMO choices from the oracle's config;** verify with a chartered accountant.
- **"Wait for the next batch" holds no stock:** another order may take it first; the card shows live ATP.
- **The inbox lists at most 200 orders per view** (no paging yet).
- **Stale orders:** the flag is computed on read from versions known at receipt (no column); the admin chooses the
  price at approval (MP09).
- **The service worker is in the production build only;** the Vite dev server does not register it, so "opens with no
  network" holds for the hosted demo (MP17), not for :5180. Offline order capture works on :5180 once the app is
  loaded.
- **E2E tenants accumulate** (one SIM organization per `make e2e`, ADR-0006: no deletes).
- **BENCHMARK replay orders carry no salesman** (BENCHMARK tenants have no logins).
- **CSRF:** relies on SameSite cookies plus the CORS allow-list; there is no CSRF token (docs/security.md).
- **Multiple tabs:** two *tabs* refreshing at the same instant can still revoke the session (safe; the user signs in
  again). Within one tab, refresh is single-flight since MP11.
- **Audit chain head:** stored in the same database; since MP11 the evidence pack exports it, so keep a copy
  outside AaharOS to catch a superuser rewriting rows *and* the head.
- **DEMO passwords:** they default to `change-me-demo` when `.env` sets none. Set real ones before hosting (MP17).
  `AAHAR_AUTH_SECRET` must be set outside dev/test; the app refuses to start with the DEMO default.
- `erd.mmd` was edited for the MP02 fixes but not re-rendered (no Mermaid renderer available locally). The
  authoritative schema is `0002_schema.py`.
- The dev DB is migrated to head (0009) and seeded with the DEMO logins; `make seed-demo` (MP08) topped up the DEMO
  factory with the recipe, pack specs, card, tolerance and price list GENERAL v1.
- Host Python on this Windows machine defaults to cp1252 and CRLF. Scripted file edits must use UTF-8 and LF
  (`.gitattributes` enforces LF on commit).

## Exact next step
Run MP12 (owner morning brief, material runway, batch planner, reorder → rows 23 shortage attribution, 24 runway) in a
fresh session: read the MP12 section of docs/MASTER_PACK.md, show the plan and wait for approval. Keep committing one
module at a time (the user's standing request since MP11).

Before starting:
- Branch `feat/mp12-planning` from `feat/mp11-reports`.
- One frontend and one backend in Docker: web http://localhost:5180, API http://localhost:8180 (`/docs`). After a
  dependency change rebuild the API image (`docker compose build api && docker compose up -d api`).
- Everything runs in Docker; never two pytest runs at once; host Python is cp1252 / CRLF; long heredocs break the Bash
  tool, so write scripts with the editor tools.
- MP12 inherits: `production.next_batch_for` (the MP09 planner stub the batch planner replaces), stock balances and
  WAC, the recipe and pack snapshots, the oracle's `material_runway_after_run` and `shortage_attribution_B`, and the
  Owner group in the sidebar.
- Supabase: the user has a Supabase account connected; it fits the hosted demo (MP17) as managed PostgreSQL. Nothing
  was created there.

### Record: the MP11 plan as approved (implemented above)
Approved by the user on 2026-11-21 as recommended (K1–K9, one commit per module); see ADR-0018.

### Record: the MP10 plan as approved (implemented above)
Approved by the user on 2026-11-21 as recommended (J1–J10); see ADR-0017 for the decisions as built.

### Record: the MP09 plan as approved (implemented above)
Approved by the user on 2026-11-21 as recommended (H1–H10); see ADR-0016 for the decisions as built. Steps: domain
rules with a property test; the approval service, card and next-batch read; API; seeds and replay (row 13); DB tests
incl. the races; the inbox and card screens, admin landing and tour copy; one more Playwright scenario; docs.

### Record: the MP08 plan as approved (implemented above)
**Approved MP08 plan** (approved by the user on 2026-11-21, G1–G8 as recommended, G9 added; salesman PWA with an offline outbox; the orders API). MP08 turns no benchmark row green on its
own (13 is MP09), so the gate is the Playwright scenarios; the scoreboard must stay 12/26.

What exists: `customers`, `price_lists` (versioned, optional customer, effective-dated), `price_list_items`,
`sales_orders` (with `price_list_id`, `captured_at` and a unique `idempotency_key`), `order_lines` (whole packets,
`price_captured`), insert-only `order_status_history`, salesman → customer assignments with `route_order`, the salesman
row filter, `order.create` / `order.read` in the matrix, and `ledger.available_to_promise`. No price list is seeded, and
there is no order-taking code, no PWA and no Playwright yet (`make e2e` exits 1).

Decisions (approved):
- **G1. Prices come from the server's price list, never from the phone; a stale price is flagged, not refused.**
  - The price in force for a customer on a date: its customer-specific list if one is in force, else the general
    list's highest version in force.
  - The phone sends the price list version it showed and the price per line. The server takes `price_captured` from
    that version; a different price is refused (`price_mismatch`), so a tampered phone cannot set prices.
  - If that version is no longer the one in force when the order arrives (a new version came out while the phone was
    offline), the order is accepted and flagged **stale**, with the current price shown alongside; the admin decides
    in MP09.
  - Price list versions are append-only: migration 0009 makes `price_list_items` insert-only, so a captured price can
    always be traced to the list it came from. A new version is how prices change (`POST /api/price-lists`,
    `price.manage`).
- **G2. Orders are in whole packets.** The carton-aware stepper (tap = +1 packet, long-press = +1 carton) uses the
  units per carton of the item's ACTIVE pack spec, sent with the catalog; the order stores packets only.
- **G3. Numbers and dates.** `SO/26-27/000001`, gapless per financial year, given when the factory **receives** the
  order. `order_date` = the factory's business date on receipt; `captured_at` = when it was saved on the phone (shown
  as "saved on phone at").
- **G4. Idempotency.** The phone makes a UUIDv7 key when the order is saved and sends it as `Idempotency-Key`; it is
  also stored on the order (already unique). A replay returns the original order (200, `replayed`); the same key with a
  different order is 409 and lands in the conflict view.
- **G5. The outbox and sync.**
  - Dexie (IndexedDB), one new dependency (`dexie@4.0.10`), plus `vite-plugin-pwa@0.21.1` for the manifest and a
    service worker that caches the app shell, so the app opens with no network.
  - States: Saved on phone → Sending → Received by factory (only after the server's 201/200 with an order no.) →
    Approved / Rejected (read from the server; approval itself is MP09).
  - Sync runs on app start, on the browser's `online` event, and on a timer with exponential backoff (2 s doubling to
    5 min, with jitter). The Background Sync API is not used: Safari lacks it, and in-app sync covers the brief.
  - Network errors and 5xx keep the order as "Saved on phone" for a retry; a 4xx (other than 401 / 408 / 429) moves it
    to **Needs attention** with the server's reason, where it can be discarded, or edited and re-sent with a new key; a
    401 pauses sync until the salesman signs in again (the outbox is kept).
- **G6. Minimal device cache, wiped at logout.** Only the assigned customers, the priced catalog, the last order per
  customer and the salesman's own orders of the last 30 days are cached. Logout deletes the whole IndexedDB database.
  If unsent orders exist, logout first says how many and offers "Send now" or "Delete them and log out".
  *Alternative:* block logout until the outbox is empty.
- **G7. Role shells after sign-in.** A SALESMAN lands on a mobile-first `/sales` shell (Today · My orders · Summary).
  Other roles keep today's pages; their shells come with their MPs (inbox MP09, reports MP11). The "Available today"
  hint shows quantities only (✓ in stock / ⚠ partial), from `stock.read`, never values. Product pictures are generated
  DEMO illustrations (no photos).
- **G8. Playwright in its own compose service** from the official image `mcr.microsoft.com/playwright:v1.49.1-jammy`
  (a one-time image pull of about 2 GB), run against the dev stack by `make e2e`. Each run creates its own fresh
  scratch tenant with DEMO logins, so it never touches the DEMO factory. The time-to-submit for a repeat order is
  measured and printed as measured (no target is claimed until it is met). *Alternative:* run Playwright on the host
  (needs Node and the browsers installed on Windows).
- **G9 (added by the user). One web app and one backend, with the guided tour first, the way Nexora's workspace shell
  works** (`nexora-ai-learning-platform/frontend/src/app/shell`: `AppShell`, a grouped `Sidebar`, one `nav.ts`
  registry, and a `ModulePage` for hubs that are not built yet).
  - http://localhost:5180 is the only frontend server and http://localhost:8180 the only API. Every role's screens
    live in this one React app; there is no second frontend.
  - The first page anyone sees is the guided tour (Start here + the 11-step NIT tour, as today).
  - An app shell with a grouped sidebar: Guide · Salesman · Admin · Production · Owner · Auditor · Judge. Every screen
    in `apps/web/src/guide/screens.ts` is listed in its group. A built screen opens. A screen not built yet opens an
    honest "Coming in MPxx" page saying what it will do, never sample numbers or fake data.
  - `screens.ts` becomes the single registry for the sidebar, the routes and the tour's "Take me there" links, so the
    three can never disagree. Each entry gains its role group, an icon and a one-line description.
  - Signed out, a visitor can browse the tour and the "coming" pages; a screen that needs data asks to sign in. After
    sign-in the user's role group is expanded and they land on its home (a salesman on `/sales`). The sidebar hides
    what the role cannot use; the API still enforces every permission.
  - Phone width: the sidebar collapses into a menu button; the salesman area uses bottom tabs (Today · My orders ·
    Summary). Everything keeps 48 px touch targets, and status is icon + word + colour.
  - No new UI library: plain CSS with the existing tokens (PROGRESS decisions, MP00).

Steps:
1. **Migration 0009:** `price_list_items` insert-only (trigger + grants); `alembic check`.
2. **`sales.domain` (pure):** price resolution, the order plan (whole positive packets, each item once), totals ex-tax
   (an `Explained` value), the stale rule, the request hash (unit- and order-independent), `SO/26-27/000001`.
   Hypothesis: totals = Σ qty × captured price, exactly.
3. **`sales.service`:**
   - price lists: create a version (with its items), list, the price in force for a customer
   - `catalog(customer)`: FG items priced for that customer, units per carton from the active pack spec
     (`recipe.service`), the available-today hint (`ledger.available_to_promise`, quantities only)
   - `place_order`: one savepoint — idempotency claim, assignment check (a salesman orders only for assigned
     customers), price check (G1), number, order + lines, a SUBMITTED status-history row, audit row
   - `get_order` (lines, status timeline, stale flag with current price), `list_orders` (existing row filter),
     `last_order(customer)`, `summary` (per customer: orders, packets, value ex-tax — labelled "ordered, not invoiced")
4. **API** (all in the generated route × role tests): `POST /api/orders` (`order.create`, Idempotency-Key),
   `GET /api/orders/{id}`, `GET /api/sales/catalog?customer_id=`, `GET /api/sales/customers/{id}/last-order`,
   `GET /api/sales/summary` (`order.read`), `GET/POST /api/price-lists` (`customer.read` / `price.manage`). Decimals as
   strings; quantities as whole-number strings.
5. **Seeds and the replay:** a DEMO general price list v1 with `murukku_200g` at ₹50.00 (the inputs'
   `selling_price_ex_tax`) in `setup_section5`; `make seed-demo` adds the price list (and MP06's recipe, pack specs,
   card and tolerance) to an existing DEMO factory if missing. The replay posts step 4 (Retailer A, 150) and step 6
   (Distributor B, 120) as SUBMITTED orders, ready for MP09; no assertion changes. DB tests: the salesman row filter
   on orders, an order for an unassigned customer refused, a tampered price refused, a stale price flagged, a
   duplicate key replayed, a reused key with a different order 409, numbering gapless after a refusal.
6. **Web, one app (G9 first, then `/sales`, mobile-first, 48 px targets):**
   - the shell: grouped sidebar from `screens.ts`, the "Coming in MPxx" page, the menu button at phone width, sign-in
     state in the top bar; the guided tour stays the landing page; existing pages (`/guide`, `/leaks`, `/sign-in`)
     move inside the shell; vitest checks that every registry entry has a route and a sidebar link
   - Today: assigned customers in route order with **Repeat last order**
   - the order screen: product grid with pictures, carton-aware stepper, last quantity pre-filled, sticky total
     ex-tax, the available-today hint, Save (always to the phone first)
   - My orders with the status timeline; Needs attention (the conflict view); Summary per customer
   - the outbox (Dexie) and the sync engine, written as a pure state machine with an injected clock and network so
     vitest can drive backoff, ACKs, conflicts and 401s; the UI never says "Received" before the server's ACK
   - logout wipe (G6), PWA manifest and service worker (G5); the role redirect after sign-in (G7)
7. **E2E (`make e2e`):** online order; offline order → reconnect → exactly one server order; a duplicate replay
   ignored; a stale price flagged (a new price list version published while the phone is offline); time-to-submit for
   a repeat order measured and printed.
8. **Docs:** ADR-0015 (G1–G8), `docs/security.md` (what the phone stores and when it is wiped), the README's DEMO
   logins and `make e2e`, CLAUDE.md commands, this file.

**Gate:** one frontend (:5180) with every role's screens in its sidebar and the tour first, one API (:8180); the
five Playwright scenarios pass; an offline order reaches the server exactly once; a stale price is
flagged; the measured repeat-order time is printed; the benchmark stays 12/26 with no green row turned red; the full
suite passes with 500 state-machine examples.

### Record: the MP07 plan as approved (implemented above)

Figures checked by hand against the oracle before writing this plan:
- Run cost = materials 4,055.00 (flour 1,725 + oil 1,470 + spice 240 + pouches 485 + cartons 135) + labour 1,200 +
  gas 600 = **5,855.00**; per good packet 5,855 / 188 = 31.143617 → **₹31.14**.
- Sensitivity: only flour has two price layers. FIFO flour 1,680 (−45) → 5,810.00 / 188 = **30.90**; LAST flour
  1,800 (+75) → 5,930.00 / 188 = **31.54**. Oil, spice, pouches and cartons have one layer, so all methods agree.
- Waterfall: standard of 188 good = per-batch standard 5,120 (ingredients 3,320 + conversion 1,800) × 188 / 200 +
  packaging standard 3.25 × 188 = 4,812.80 + 611.00 = **5,423.80**; actual − standard = **431.20 U** =
  yield 12 × 25.60 = 307.20 + oil usage 0.5 L × 140 = 70.00 + flour price (43.125 − 42) × 40 = 45.00 + pouch usage
  (194 − 188) × 2.50 = 15.00 + carton usage (9 − 9.4) × 15 = −6.00 + conversion spend (1,800 − 1,800) = 0.

Decisions that need a yes or no:
- **F1. Run costs are recorded only on COMPLETED runs, by `production`, and each one posts a COST_TRUE_UP journal at
  once.** `run_costs` belongs to production and is insert-only with its `journal_id` (migration 0003), so a cost
  entered during the run could not be attached to the completion later without a migration. `costing` (L6) only
  reads. *Alternative:* allow costs on IN_PROGRESS runs and let `complete_run` absorb them with a CONVERSION_COST
  line (needs migration 0008 to relax `run_costs` and a change to the MP06 completion).
- **F2. The true-up spreads cumulatively, as ledger.md J8 does.** For each lot: new target = its share of the run's
  conversion costs (by bulk allocated, last lot takes the rounding remainder) + what it already holds. Each position
  that holds the lot's units (CUSTOMER, IN_TRANSIT, FG_STORE) gets round(qty / lot qty × target) − value already
  there; FG_STORE (on hand) takes the remainder. Two true-ups (labour, then gas) therefore end exactly where one would.
  A zero-good line's share goes to SCRAP on the bulk item (E4). The lot's positions are locked first, so a dispatch
  cannot read a half-updated lot value.
  - Benchmark: dispatch is MP10, so in MP07's replay all 188 are on hand and B-001 ends at 5,855.00. A pure test
    proves NIT's order now (100 sold first: CUSTOMER +957.45, FG_STORE +842.55), and MP10 replays the real order.
- **F3. Cost status becomes FINAL by an explicit "finalise run costs" action** (`run.cost`); no run cost is accepted
  after FINAL. The replay records labour and gas, then finalises. *Alternative:* FINAL automatically once both a
  LABOUR and a GAS_POWER cost exist.
- **F4. Standard cost cards are stored, append-only, and a run uses the card in force on its run date.**
  - One card per pack spec version and version number, effective-dated: ingredient lines per batch × standard rate,
    conversion per batch, packaging per good unit × standard rate, `per_unit` to 6 dp.
  - Migration 0008 makes `standard_cost_cards` and `standard_cost_lines` insert-only (trigger + grants), so a past
    run's waterfall can never be revalued by editing a card. A new card version is how standards change.
  - Production (L5) cannot import costing (L6), so the card is found by run date when the costing is read, not frozen
    into the run snapshot. Seed: the 200 g card from the inputs at opening rates (A2) and step 8's labour + gas as the
    conversion standard, 28.85 (the same arithmetic D3 already uses for OPEN-LOT). No 500 g card: there is no input
    rate for `pouch_500g`, so its waterfall says "no standard cost card".
- **F5. Waterfall rules.** Price = (actual rate − standard rate) × actual qty; usage = (actual qty − standard qty) ×
  standard rate, with ingredients against the batch standard and packaging against the flexible standard; yield =
  per-batch standard × (expected − good) / expected; conversion spend = actual − standard per batch × multiplier.
  Each component is rounded half up to paise; if the rounded parts do not sum to actual − standard, an explicit
  "rounding" line shows the difference (never silent). Multi-pack runs: computed when every pack line's card has the
  same per-batch rates; otherwise refused with a reason (known gap). A Hypothesis property checks the sum is exact.
- **F6. Sensitivity re-values each of the run's issue movements as of that movement.** `valuation.sensitivity_at`
  replays the item's history *before* the journal that issued it (the material issue, or the completion for
  packaging), so later purchases do not leak in. Returns are scaled by net / issued quantity. Only WAC ever posts.
- **F7. Monthly overhead absorption is deferred to MP11 (reports).** It needs machine-hours per run and monthly
  overhead amounts, and neither has a table yet; it does not affect the benchmark. MP07 shows direct (marginal) cost
  only, labelled. *Alternative:* add both now (migration 0008 columns, inputs on the completion, an allocation
  rule), about half a day more.
- **F8. The "Where profit leaks" page needs a way to sign in.** There is no login screen until MP08. Recommendation:
  add a plain sign-in page now (email + password → the existing `/api/auth/login`, no role shells; MP08 builds those),
  so the page and the `<Num>` ⓘ popover read the authenticated `GET /api/runs/{id}/costing` and can be checked live.
  *Alternative:* a public read-only endpoint for the newest BENCHMARK tenant's run only (no login, fictional data),
  which Judge Mode (MP15) could reuse; it needs an owner-side lookup across tenants.

Steps:
1. **Migration 0008:** standard cost cards and lines insert-only (immutability triggers, SELECT + INSERT grants);
   `alembic check`; the generic migration up/down test covers it.
2. **`valuation.sensitivity_at(item, qty, before_journal_id)`** with a pure test that a later purchase does not change
   it.
3. **`production`:**
   - `domain.plan_true_up` (pure): the F2 split, laws 1–2 by construction; tests for the J8 figures (957.45 /
     842.55), all-on-hand (+1,800.00 to FG_STORE), two true-ups equal to one, and a zero-good line (SCRAP).
   - `service.record_run_cost` (COMPLETED and PROVISIONAL only; kinds LABOUR / GAS_POWER / OTHER; amount as a
     decimal string; Idempotency-Key; one savepoint: run_costs row + COST_TRUE_UP journal + audit row) and
     `service.finalise_costs` (→ FINAL, audited).
   - `service.costing_facts(run_id)`: what costing needs, read from the ledger and the run (net issue values per item,
     packaging values from the completion journal, lot values, conversion costs, the snapshot).
4. **`costing`:**
   - `domain.py` (pure): run cost by item and kind, cost per good unit (6 dp, shown to paise), FG lot unit cost, the F5
     waterfall, the F6 sensitivity totals. Every figure an `Explained` value with source refs (run, issue, journal,
     card). Property test: the waterfall sums exactly to actual − standard.
   - `service.py`: create / list standard cost cards; `run_costing(run_id)`.
   - API: `GET /api/runs/{id}/costing` (`report.read`), `POST /api/runs/{id}/costs` and
     `POST /api/runs/{id}/costs/finalise` (`run.cost`), `GET /api/standard-cost-cards` (`report.read`),
     `POST /api/standard-cost-cards` (`recipe.manage`). Generated route × role tests cover them.
5. **Seeds and the replay:** the 200 g standard card in `setup_section5`; step 8 (labour 1,200 + gas 600) recorded
   on B-001, then finalised. **Turn green:** 17 (5,855.00 = 4,055.00 + 1,200 + 600), 18 (31.14; FIFO 30.90, LAST
   31.54), 19 (431.20 U and every component equal to the oracle's). Keep 1–4, 6, 7, 15, 16, 20 green;
   `tests/db/test_replay.py` gains B-001 on hand 188 / 5,855.00, FINAL. Assertion 22 stays with MP10 (it needs the
   dispatch).
6. **Integrity:** law 2 per run moves from "not built" to a real check: for every completed run, the value of its
   lots wherever they are (on hand, in transit, sold) + what it wrote off = its net materials + its conversion costs.
7. **Web:**
   - `<Num>`: value plus an ⓘ popover with the formula, inputs and their sources (keyboard and screen-reader usable).
   - "Where profit leaks" page for a run: the waterfall as ranked ₹ cards (unfavourable first), flags from MP06, and
     "check" prompts worded as questions to verify, never as causes ("Check the frying temperature log and oil
     top-ups for run B-001"). Every number from the API.
   - The F8 sign-in. Vitest tests with a recorded API response; checked live in the browser on :5180.
8. **Docs:** ADR-0014 (F1–F8), ledger.md (J8 as built), invariants L2 test ids, bom.md / assumptions (standard rates
   = opening rates, conversion standard = step 8), this file.

**Gate:** 17, 18, 19 green (12/26); lot value = run cost exactly (5,855.00) and law 2 per run passes in `make
integrity`; the waterfall property test passes; no green row turns red; full suite with 500 state-machine examples.

### Record: the MP06 plan as approved (implemented above)

Decisions that need a yes or no:
- **E1. Quantity variances are computed on read from the run's frozen snapshot, not stored.** Each run freezes its
  recipe, pack specs and the tolerance in force on its run date. Yield and usage variances are then pure functions of
  the snapshot and the run's posted actuals: deterministic, nothing to drift, the same idea as ADR-0012. Two reasons:
  - `variance_results` belongs to `costing` (a higher layer than `production`)
  - its rupee column is NOT NULL, and rupee impacts are MP07's waterfall
  MP07 then decides whether the costed rows are stored. *Alternative:* store rows at completion, which needs migration
  0008 (move the table to `production`, make `inr_impact` nullable).
- **E2. The flag rule.** Flagged = beyond tolerance **and** unfavourable. Favourable beyond tolerance is shown as
  information (carton −4.26%: "8 loose packets not cartoned"), matching bom.md. The comparison uses the unrounded
  percentage and is strict, so exactly 3.00% is not flagged; the display rounds half up to 2 dp. Tolerance = the
  line's override, else the org setting `variance_tolerance_pct` (effective-dated, seeded at 3).
- **E3. Run and lot numbers.**
  - Runs are numbered B-001, B-002, … per organization (a perpetual sequence, `number_sequences` fy `00-00`).
  - The lot no. is the run no., with -A / -B suffixes for a run with several pack lines.
  - Material issues are numbered `MI/26-27/000001`.
- **E4. A pack line with zero good units writes its materials off to SCRAP.** A burnt batch is real. Its share of the
  cost goes to SCRAP as an explicit valued line, with the scrap reason required. Law 2 holds and nothing is silent.
  *Alternative:* refuse to complete a run with no good output.
- **Note (no decision needed):** issues post RAW_STORE → WIP and completion consumes WIP → PRODUCTION, as the accepted
  ADR-0002 says. The MP06 spec text says RAW → PRODUCTION; NIT checks the flour balance between steps 2 and 3, which is
  why ADR-0002 added WIP.

Steps:
1. **`recipe` (versions and workflow):**
   - recipes and pack specs with versions DRAFT → ACTIVE → RETIRED; activating a version retires the previous
     ACTIVE one (audited)
   - lines are frozen outside DRAFT by the existing DB trigger, and only ACTIVE versions can start a run, so "used
     versions are immutable" holds by construction (tested)
   - `recipe.service.snapshot(version)` returns a JSON copy with item ids, codes, base units, quantities, drivers,
     tolerances, net g, units per carton and shelf life
2. **`production.domain` (pure, the variance engine):**
   - expected bulk = yield × multiplier; expected units = bulk allocated ÷ net g; unallocated bulk is shown, and
     over-allocation is refused
   - batch standard (PER_BATCH) and flexible standard (PER_GOOD_UNIT); the batch view of packaging shown alongside
   - yield and usage %, direction, flag (E2)
   - packing breakdown (divmod)
   - mass balance: expected = good × net + scrap + loss + **unexplained gap** (shown, never forced to 0); giveaway from
     fill-weight samples, (mean sample net − declared net) × good units, shown as part of the gap
   - every figure returned as an `Explained` value
   - nothing mentions 200, 20 or "murukku"
3. **`production.service`:**
   - `create_run` (DRAFT: recipe version, multiplier, pack lines with bulk allocated)
   - `start_run` (→ IN_PROGRESS; freezes the snapshots and the tolerance)
   - `issue_materials` / `return_materials`: a material-issue document, RAW_STORE ⇄ WIP at WAC through
     `valuation.issue_value`; a return comes back at the run's own issued average, not the shared WIP average
   - `complete_run`, atomic in one savepoint:
     - lot per pack line (mfg = run date, best-before = run date + shelf life)
     - one RUN_COMPLETION journal: the run's net issues WIP → PRODUCTION; packaging PACK_STORE → PRODUCTION at WAC,
       damaged → SCRAP at no value; FG PRODUCTION → FG_STORE per lot
     - ingredient value split between lots by bulk allocated, packaging to its own lot, the last lot takes the
       rounding remainder (ADR-0003)
     - pack lines, fill-weight samples and the oil session (top-up, discard, TPC) recorded
     - run → COMPLETED with scrap / loss / reason in a single update, then an audit row
   - Idempotency-Key on issue and completion (tablet on weak wi-fi)
   - **Atomicity test:** a failure injected at the third write of a completion leaves no journal, lot, pack-line
     change or status change behind.
4. **API** (all covered by the generated route × role tests):
   - recipes and pack specs: list, create a draft version, activate (`recipe.manage`)
   - runs:
     - `POST /api/runs` and `POST /api/runs/{id}/start` (`run.start`)
     - `POST /api/runs/{id}/issues` (`run.start`)
     - `POST /api/runs/{id}/complete` (`run.complete`)
     - `GET /api/runs`, and `GET /api/runs/{id}` with the variances, packing and mass balance (`report.read`)
   - decimals as strings
5. **Seeds and the benchmark replay:**
   - `setup_section5` adds:
     - a BULK item `murukku_bulk`
     - recipe v1 ACTIVE from the BOM: 40 kg / 10 L / 1.2 kg; bulk yield = 200 expected packets × 200 g net
     - pack spec "Murukku 200 g" v1 ACTIVE: pouch 1 and carton 0.05 per good unit (10 / 200 from the BOM),
       20 per carton, DEMO shelf life 90 days
     - the tolerance setting (3%, from the oracle's config)
     - the 500 g pack spec as seed data only: `murukku_500g`, `pouch_500g`, 10 per carton so 1/N is exact
   - The replay's J2 becomes a material issue for run B-001 and J3 a real `complete_run` (188 good; pouches 194 used,
     6 damaged; 9 cartons); the stand-in is gone.
   - **Turn green:** 4 (FG 238), 6 (yield −6.00% flagged), 7 (oil +5.00% flagged), 20 (pouch flexible +3.19% flagged;
     the test also checks the batch view −3.00% is not flagged)
   - Keep 1–3, 15 and 16 green, and the replay values equal to ledger.md (`tests/db/test_replay.py`: B-001 ₹4,055.00,
     WIP 0).
   - Assertion 26 stays red: it is all four laws (MP11). The run's quantity part is checked in a DB test and in
     `make integrity` instead.
6. **Integrity:** `make integrity` adds S6, "WIP of every completed run is zero" (net issues = what completion
   consumed, per run and item). The mass-balance gap is reported, not failed.
7. **Docs:** ADR-0013 (E1–E4, snapshot contents, value split and rounding), bom.md and invariants D2 / S6 / L3 test
   ids, assumptions (shelf life 90 days DEMO, bulk yield derived from net weight), this file.

**Gate:** the injected failure persists nothing; FG 238; yield −6.00%, oil +5.00% and pouch +3.19% are flagged; the
500 g pack spec works from seed data with no code change (a DB test runs one 500 g run); no green row turns red.
