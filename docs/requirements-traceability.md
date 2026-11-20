# Requirements traceability

Every requirement in the NIT brief (sections 2–10) mapped to where it is built and how it is tested.
Tiers: **M** NIT must-have · **S** should-have · **X** stretch · **D** AaharOS differentiator · **E** excluded.
Test ids: `bench:aNN` = assertion NN in `benchmark/test_benchmark.py`; `<module>:` = `backend/app/modules/<module>/tests/`;
`e2e:` = Playwright (MP08+); `web:` = Vitest. Status today: only R-0x guide rows and the benchmark scaffold exist.

## Section 2: the challenge

| Id | Requirement | Tier | Module | API | Screen | Tables | Test | MP |
|---|---|---|---|---|---|---|---|---|
| R2.1 | Every transaction entered once, at its source, flows into stock, production, costing, accounts | M | all (via ledger) | all posting routes | all | stock_journals, stock_lines | bench:a26, ledger:state-machine | 04–11 |
| R2.2 | Sales loop: order → verify → GST invoice → dispatch → FG down → receivables | M | sales, billing, dispatch, collections | /orders, /invoices, /dispatches, /payments | salesman app, order inbox | sales_orders, invoices, dispatches, payments | bench:a05, a08–a12 | 08–10 |
| R2.3 | Production loop: purchase → issue per BOM → run → FG up → variance and cost | M | procurement, recipe, production, costing | /receipts, /runs | batch card | purchase_receipts, production_runs, variance_results | bench:a01–a04, a06, a07, a17 | 05–07 |
| R2.4 | Both loops meet at FG stock and feed monthly reports | M | ledger, reports | /reports/* | reports | inventory_balances | bench:a05, a13, a23 | 09–12 |
| R2.5 | Tally not required daily; export is a welcome extra | X | reports | /exports/tally | export centre | export_jobs | reports:tally-xml | 11 |

## Section 3: users and roles

| Id | Requirement | Tier | Module | API | Screen | Tables | Test | MP |
|---|---|---|---|---|---|---|---|---|
| R3.1 | Salesman (phone, weak network): pick customer, add products, submit; see own orders, status, customer-wise sales | M | sales, identity | /orders, /me/customers | salesman PWA | salesman_customer_assignments | e2e:salesman-order, identity:row-filter | 03, 08 |
| R3.2 | Factory admin (desktop): receive orders, verify price/qty/stock, invoice, dispatch, payments | M | sales, billing, dispatch, collections | /orders/{id}/approve … | order inbox, invoices, collections | — | e2e:admin-flow | 09–10 |
| R3.3 | Production supervisor: receipts, issues, daily runs, actual output and wastage | M | procurement, production | /receipts, /runs | batch card | — | e2e:batch-card | 05–06 |
| R3.4 | Accountant/auditor: read-only monthly reports and exports | M | reports, identity | GET /reports/* | auditor workspace | — | identity:auditor-403-all-mutations | 03, 11 |
| R3.5 | Owner: today's orders, stock, variance alerts, cost per packet, dues | S | planning | /owner/brief | morning brief | alerts | planning:brief | 12 |
| R3.6 | Each role sees only what it needs; RBAC is a requirement | M | identity | `require(perm)` on every route | role shells | roles, permissions, memberships | identity:route×role matrix | 03 |

## Section 4.1: field order taking

| Id | Requirement | Tier | Module | API | Screen | Tables | Test | MP |
|---|---|---|---|---|---|---|---|---|
| R4.1.1 | Salesman logs in, selects retailer/distributor, adds products with quantities | M | sales | POST /orders | New order | sales_orders, order_lines | e2e:salesman-order | 08 |
| R4.1.2 | Price from a price list; customer-specific prices/schemes optional | M / X | catalog, sales | GET /price-lists/active | product grid | price_lists (versioned) | sales:price-capture | 08 |
| R4.1.3 | Submitted straight to the factory, no phone/WhatsApp | M | sales | POST /orders | — | — | e2e:salesman-order | 08 |
| R4.1.4 | Offline orders saved and sent when network returns | X (strongly preferred) | sales | Idempotency-Key | outbox states | idempotency_keys | e2e:offline-sync-once | 08 |
| R4.1.5 | Order status (submitted/approved/invoiced/dispatched) and customer-wise sales | M | sales | GET /me/orders | My orders | order_status_history | e2e:status-timeline | 08 |

## Section 4.2: verification and GST billing

| Id | Requirement | Tier | Module | API | Screen | Tables | Test | MP |
|---|---|---|---|---|---|---|---|---|
| R4.2.1 | Admin sees incoming orders, edits qty/price, approves/rejects | M | sales | /orders/{id}/approve, /reject, /amend | order inbox | order_status_history, audit_log | sales:amend-audited | 09 |
| R4.2.2 | Before approval, show whether FG stock covers the order | M | sales, ledger | GET /orders/{id}/availability | "Available to promise" | reservations | bench:a13, sales:race-last-packets | 09 |
| R4.2.3 | GST invoice: GSTIN, HSN, taxable value, CGST/SGST or IGST by place of supply, FY numbering | M | tax, billing | POST /invoices | invoice | invoices, invoice_tax_lines, number_sequences, tax_rules | bench:a08–a11, a14, tax:property-sum | 10 |
| R4.2.4 | Invoice PDF, shared via WhatsApp link or email | M | billing | GET /invoices/{id}.pdf | invoice view | — | billing:pdf-fields | 10 |
| R4.2.5 | Dispatch reduces FG stock; partial dispatch and returns optional | M / X | dispatch, ledger | POST /dispatches | dispatch | dispatches, dispatch_lines | bench:a05, a21 | 10 |
| R4.2.6 | Payments recorded against invoices → customer outstanding | M | collections | POST /payments | collections | payments, payment_allocations | bench:a12, collections:no-over-allocation | 10 |

## Section 4.3: BOM and production (highest weight)

| Id | Requirement | Tier | Module | API | Screen | Tables | Test | MP |
|---|---|---|---|---|---|---|---|---|
| R4.3.1 | BOM per product: standard qty of each raw and packaging item per batch + expected yield | M | recipe | /recipes, /pack-specs | recipe master | recipe_versions, recipe_lines, pack_spec_lines (driver) | recipe:versions-immutable | 06 |
| R4.3.2 | Run records product, batch size/issues, expected output, actual output, wastage/scrap | M | production | POST /runs | batch card | production_runs, run_issues, run_outputs | bench:a04 | 06 |
| R4.3.3 | Saving a run lowers raw stock and raises FG stock automatically | M | production, ledger | POST /runs/{id}/post | stock-impact preview | stock_journals | bench:a01–a04, production:atomic-rollback | 06 |
| R4.3.4 | Planned vs actual consumption and yield; flag beyond tolerance (e.g. 3%) | M | production | GET /runs/{id}/variances | variance view | variance_results, settings | bench:a06, a07, a20 | 06 |
| R4.3.5 | Units convert correctly: kg, g, L, pieces, packets, cartons | M | uom | — | — | uoms, uom_conversions | uom:round-trip-property | 04 |

## Section 4.4: inventory

| Id | Requirement | Tier | Module | API | Screen | Tables | Test | MP |
|---|---|---|---|---|---|---|---|---|
| R4.4.1 | Separate balances: raw, packaging, WIP (optional), FG by product and pack size | M | ledger | GET /stock | stock summary | locations, inventory_balances | ledger:projection==rebuild | 04 |
| R4.4.2 | Opening + receipts − issues/sales ± adjustments = closing, per item | M | ledger | GET /stock/summary | stock summary | stock_lines | ledger:state-machine, bench:a26 | 04, 11 |
| R4.4.3 | Stock ledger: every movement with its source document | M | ledger, reports | GET /stock/ledger | stock ledger | stock_journals(source_type, source_id) | ledger:source-required | 04 |
| R4.4.4 | Batch numbers and expiry dates | X | ledger, traceability | GET /lots | trace this packet | lots | bench:a21, traceability:trace | 06, 13 |

## Section 4.5: costing

| Id | Requirement | Tier | Module | API | Screen | Tables | Test | MP |
|---|---|---|---|---|---|---|---|---|
| R4.5.1 | Material + packaging cost per run from purchase rates; pick and justify method | M | valuation, costing | GET /runs/{id}/cost | Explain this number | item_cost_state, valuation_layers | bench:a16, a17, a18 (WAC, FIFO/LAST sensitivity) | 05, 07 |
| R4.5.2 | Labour, power, gas, overheads per run or month, allocated by a stated rule | S | costing | POST /runs/{id}/costs | run costs | run_costs | bench:a17, costing:overhead-allocation | 07 |
| R4.5.3 | Approximate cost per packet per product and margin vs selling price | S | costing | GET /products/{id}/margin | where profit leaks | standard_cost_cards | bench:a18, a19 | 07 |

## Section 4.6: reports

| Id | Requirement | Tier | Module | API | Screen | Tables | Test | MP |
|---|---|---|---|---|---|---|---|---|
| R4.6.1 | Monthly, date-range filters, export Excel/CSV and PDF | M | reports | GET /reports/*?from&to&format | reports | export_jobs | reports:totals-vs-sql | 11 |
| R4.6.2 | Sales register, customer-wise and product-wise | M | reports | /reports/sales-register | reports | — | reports:sales-register | 11 |
| R4.6.3 | GST summary mapping to GSTR-1 / GSTR-3B | S | reports, tax | /reports/gst-summary | reports | invoice_tax_lines | bench:a26 (tax law) | 11 |
| R4.6.4 | Purchase register | S | reports | /reports/purchase-register | reports | purchase_receipts | reports:purchase-register | 11 |
| R4.6.5 | Stock summary and stock ledger (raw, packaging, FG) | M | reports | /reports/stock | reports | stock_lines | reports:stock-summary | 11 |
| R4.6.6 | Production report: planned vs actual, yield, wastage | M | reports | /reports/production | reports | variance_results | reports:production | 11 |
| R4.6.7 | Payments, collections, outstanding by customer with ageing | S | reports, collections | /reports/receivables-ageing | reports | payments | reports:ageing-buckets | 11 |
| R4.6.8 | Tally-compatible XML / Excel export | X | reports | /exports/tally | export centre | — | reports:tally-xml | 11 |

## Section 5: benchmark

| Id | Requirement | Tier | Where | Test | MP |
|---|---|---|---|---|---|
| R5.1 | Load section 5 master data from a seed script | M | `make seed-benchmark` (BENCHMARK tenant only) | bench:* | 05 |
| R5.2 | Steps 1–9 run end to end, in order, in the demo video | M | guided tour, Judge Mode, demo script | bench:a01–a26 | 04–12, 15, 18 |
| R5.3 | Results table matches, or differences explained in README | M | oracle `nit_expected`, README | bench:a01–a14 | 18 |
| R5.4 | Cost per packet stated with valuation method and overhead rule | M | costing, README | bench:a18 | 07, 18 |

## Section 6: scope tiers

| Id | Requirement | Tier | Covered by |
|---|---|---|---|
| R6.M1 | Login with ≥ 3 roles (salesman, admin, production) | M | R3.6 (5 roles) |
| R6.M2 | Product, customer, raw material and BOM masters | M | catalog, recipe (MP05–06) |
| R6.M3 | Mobile-friendly order entry and admin approval | M | R4.1.1, R4.2.1 |
| R6.M4 | GST invoice as PDF | M | R4.2.4 |
| R6.M5 | Production run updates raw and FG stock automatically | M | R4.3.3 |
| R6.M6 | Planned vs actual consumption and yield with variance | M | R4.3.4 |
| R6.M7 | Stock summary and stock ledger | M | R4.4.1–R4.4.3 |
| R6.M8 | Sales register and stock report exportable to Excel/CSV | M | R4.6.1, R4.6.2, R4.6.5 |
| R6.S1 | Purchases and supplier records | S | procurement (MP05) |
| R6.S2 | Payments, outstanding and ageing | S | R4.2.6, R4.6.7 |
| R6.S3 | Cost per packet with overheads | S | R4.5.2–R4.5.3 |
| R6.S4 | GST summary report | S | R4.6.3 |
| R6.S5 | Variance alerts beyond tolerance | S | R4.3.4 + alerts (MP12) |
| R6.S6 | Owner dashboard | S | R3.5 |
| R6.X1 | Offline order capture with sync | X | R4.1.4 |
| R6.X2 | Batch and expiry tracking, FEFO dispatch | X | R4.4.4, bench:a21 |
| R6.X3 | Reorder levels and low-stock alerts | X | planning (MP12) |
| R6.X4 | Production planning from pending orders | X | planning batch planner, bench:a24 (MP12) |
| R6.X5 | Salesman route/visit log with GPS check-in | X | transport, opt-in one-time check-in only (MP14) |
| R6.X6 | Tally-compatible export | X | R4.6.8 |
| R6.X7 | e-Invoice / e-Way Bill format (mock API) | X | dispatch/billing adapters, bench:a25 (MP10) |
| R6.X8 | Tamil interface for floor staff | X | i18n (MP15) |

## Section 7: technical expectations

| Id | Requirement | Tier | How | Test | MP |
|---|---|---|---|---|---|
| R7.1 | Stack choice justified in 2–3 sentences | M | README, ADR-0001 | review | 18 |
| R7.2 | Real database; balances derived from a ledger, never overwritten | M | Postgres, inventory_balances projection, zero-sum trigger | ledger:projection==rebuild, db:unbalanced-journal-rejected | 02, 04 |
| R7.3 | No float money; decimal or integer paise | M | `Decimal`/`NUMERIC`, `core.money` rejects float | test_core:float-rejected, grep gate | 00+ |
| R7.4 | Every stock movement links to its source | M | stock_journals(source_type, source_id) NOT NULL | ledger:source-required | 02, 04 |
| R7.5 | Edits to invoices and runs logged with user and time; posted invoices cancelled by credit note | M | audit hash chain, immutability trigger, credit notes | audit:tamper-detected, billing:credit-note | 03, 10 |
| R7.6 | Seed script for section 5 data | M | `make seed-benchmark` | bench:* | 05 |
| R7.7 | Hosted demo link or single run command | M | `make up`; hosted demo in MP17 | fresh-clone drill | 17 |
| R7.8 | Understand every part; explain and change code live | M | Part F drills, judge-readiness | MP19 drills | 19 |

## Section 8: deliverables

| Id | Deliverable | Where | MP |
|---|---|---|---|
| R8.1 | Public Git repo with clear commit history (no single final commit) | GitHub, one commit per logical change | all |
| R8.2 | README: setup, stack and why, features vs tiers, assumptions, known gaps, benchmark numbers | README.md | 18 |
| R8.3 | Design note ≤ 2 pages: ER diagram, stock and BOM computation, costing and valuation | docs/design-note.md | 18 |
| R8.4 | Demo video ≤ 8 min, section 5 in order, mobile + admin views | docs/demo-script.md | 18 |
| R8.5 | Live link or run command with test logins per role | README, Start-here page | 03, 17 |
| R8.6 | First-time visitors understand how to test it | Start-here page + guided tour + Guide button (D) | 00, 15 |

## Sections 9–10: evaluation and rules

| Id | Requirement | Tier | How | MP |
|---|---|---|---|---|
| R9.1 | Salesman places an order in under a minute | M | One-Thumb Order, Playwright timing (real number reported) | 08 |
| R9.2 | Live change: add a 500 g pack sharing the BOM | M | pack_spec data, zero code; rehearsed | 06, 19 |
| R10.1 | Document assumptions | M | docs/assumptions.md | 00+ |
| R10.2 | Only section 5 data and invented data; no real customer/company data | M | DEMO labels, CLAUDE.md rule | all |
| R10.3 | Individual, original work | M | own repo and history | all |

## AaharOS differentiators (tier D) and exclusions (tier E)

| Id | Item | Tier | MP |
|---|---|---|---|
| D1 | Start-here page, guided tour, Guide button on every page | D | 00 |
| D2 | Judge Mode: one-click replay + 26-row scoreboard | D | 15 |
| D3 | Where Profit Leaks: variance waterfall, flexible standards | D | 07 |
| D4 | Explain this number (`Explained` values with sources) | D | 07+ |
| D5 | Material runway and batch planner; shortage attribution | D | 12 |
| D6 | Trace this packet, recall simulator, freshness radar | D | 13 |
| D7 | Month-end close cockpit, evidence pack | D | 11 |
| D8 | Factory simulator with planted truths, ML only if it beats baselines | D | 16 |
| E1 | Microservices, blockchain, chatbot-first navigation, continuous GPS tracking | E | — |
| E2 | Live GST / IRP / e-way bill API calls (mock adapters only) | E | — |
| E3 | ML or LLM writing to ledger, invoice, payment or production tables | E | — |
