# AaharOS — NIT Trichy Order-to-Audit System
## Product blueprint, architecture, data strategy, financial model and Claude Code master-prompt pack

**Based on:** `Problem Statement - Winter Internship Application - 2026 .md`  
**Issuing body:** Centre for Digital Infrastructure, NIT Tiruchirappalli  
**Project type:** Individual prototype for a small South Indian packaged-snack manufacturer  
**Working title:** AaharOS — The Digital Operations & Intelligence Platform for Small Food Manufacturers  
**Important:** The name is provisional. The benchmark data supplied in the problem statement is authoritative and must not be altered.

---

# PART A — PRODUCT STRATEGY

## 1. Product vision

Build a production-aware, traceable order-to-audit platform for a small food factory. A transaction is entered once at its source and flows through inventory, production, costing, sales, dispatch, collections and audit reports.

The product should answer five questions that a small factory owner normally struggles to answer:

1. **Where did the material go?** Trace every receipt, issue, production consumption, scrap, adjustment and dispatch to its source document.
2. **What did the factory actually make?** Compare the recipe plan with actual consumption, saleable output, damage and wastage.
3. **What did each saleable packet really cost?** Include raw materials, packaging, direct labour and run-level energy/power costs.
4. **Where is money or capacity being lost?** Translate over-consumption, yield loss, expiry, stock-outs, delayed collections and delivery expense into understandable business impact.
5. **What should the owner do next?** Present practical, explainable actions rather than unexplained AI scores.

The product must feel simple to the salesman and production worker, while remaining mathematically trustworthy for the owner, accountant and auditor.

### Positioning statement

> AaharOS gives a small food manufacturer one connected operational record from retailer order to production batch to customer invoice — with every stock movement traceable and every avoidable loss visible in rupees.

## 2. The innovation thesis

Do not try to impress the panel by adding dozens of unrelated modules or forcing AI into a deterministic accounting problem. Build a strong operational core and make the differentiators arise from the data already captured.

### 2.1 Essential differentiators

| Differentiator | What it does | Why it matters |
|---|---|---|
| **Batch-to-Cash Traceability** | Links purchased raw-material lots → production run → finished-goods batch → invoice → retailer/distributor | Makes a packet traceable in both directions |
| **Loss-to-Profit Intelligence** | Converts yield shortfall, extra ingredient use, damaged packaging and expiry into ₹ impact | Turns a variance report into a business decision |
| **Recipe Version Lock** | Every production run snapshots the approved BOM version used at the time | Old runs remain reproducible when a recipe changes |
| **Stock Confidence** | Separates ledger quantity, physical count, reserved quantity and available quantity | Stops owners treating a single overwritten stock number as truth |
| **Production Readiness Planner** | Reads pending orders, available finished goods, BOMs and raw stock to calculate batches required and shortages | Connects sales demand to production planning |
| **Margin Waterfall** | Shows selling price excluding tax, batch cost, estimated delivery cost and contribution margin | Exposes products or customers that are low-margin after delivery |
| **Expiry and Recall Trace** | Supports lot/expiry tracking and a forward/backward trace query | Helps isolate affected batches and customers without recalling everything |
| **Route Cost Intelligence** | Estimates delivery distance, vehicle capacity, trip cost and cost per delivered packet | Makes transport a measurable cost rather than an invisible expense |
| **Audit Evidence Pack** | Exports the underlying records, movement references, totals and calculation assumptions | Helps an accountant verify numbers instead of trusting a dashboard |

### 2.2 One standout feature: the Loss-to-Profit Ledger

Create a screen called **“Where Profit Leaks”**. It should show a small number of evidence-backed cards:

- Yield loss: expected 200, actual 188, shortfall 12 packets, variance −6%.
- Extra oil consumption: planned 10 L, actual 10.5 L, excess 0.5 L, additional material cost ₹70 at the supplied ₹140/L rate.
- Packaging damage: 6 damaged pouches, recorded separately from good packets, cost ₹15 at ₹2.50 per pouch.
- Cost per saleable packet: actual run cost divided by 188 good packets.
- Potential sales value of 12 missing packets: ₹600 at ₹50 per packet before tax. Label this **potential sales value**, not confirmed profit or cash loss.
- Recommended action: review frying temperature, batch timing, operator entry and packaging handling. Recommendations must be framed as hypotheses, not asserted causes, because the benchmark contains no root-cause evidence.

Every card must drill down to the exact production run, material issue or stock movement. Never display an AI-generated explanation without evidence.

### 2.3 A second standout feature: “Can I fulfil this order?”

Before approval, show:

- Current finished-goods on-hand.
- Already reserved quantity.
- Available-to-promise quantity.
- Quantity requested.
- Quantity that can be fulfilled now.
- Shortage.
- Earliest feasible fulfilment estimate, based on capacity and raw-material availability if production planning has been configured.

For the benchmark, Distributor B requests 120 packets when only 88 are available. The system must clearly show a shortage of 32 and must not silently create negative stock. Offer a backorder or partial-fulfilment path. Do not create a posted invoice for unavailable stock unless the user explicitly chooses a supported business rule and the stock/dispatch status is truthful.

### 2.4 A third standout feature: “Trace this packet”

From a finished-goods batch, the owner or auditor can navigate backward to:

- Production run and timestamp.
- BOM version.
- Raw-material and packaging lots consumed.
- Actual quantities and operator.
- QC result and wastage.
- Material valuation used for costing.

They can navigate forward to:

- Finished-goods stock movements.
- Dispatches.
- Invoices.
- Customers who received the batch.

For the prototype, use synthetic lot numbers and synthetic customers. A recall simulator may show the affected customers for a selected lot. Label this as a traceability demonstration, not a regulatory recall certification.

---

# PART B — SCOPE AND PRIORITY

## 3. Three delivery tiers

### Tier 1 — Mandatory benchmark system (must be excellent)

- Login and role-based permissions for salesman, admin, production and read-only accountant/auditor; owner role is also recommended.
- Masters for products, customers, suppliers, raw materials, packaging, units and BOMs.
- Mobile-friendly order entry.
- Admin order verification and approval.
- GST invoice PDF using the exercise's 5% tax assumption.
- Purchase receipt and stock update.
- Production run with BOM-based planned quantity and actual issues.
- Actual good output, damage and wastage capture.
- Automatic raw-material decrease and finished-goods increase.
- Stock ledger with source references.
- Planned-versus-actual consumption and yield variance.
- Cost per packet including labour and power/gas.
- Dispatch, customer payment and outstanding balance.
- Sales register and stock reports, with CSV/XLSX export.
- A deterministic seed script that reproduces the supplied benchmark exactly.

### Tier 2 — High-value differentiators

- Batch/lot/expiry tracking with FEFO suggestions.
- Raw-material reorder level and supplier lead-time alerts.
- Production planning from pending orders.
- Margin by product, customer and route.
- Loss-to-Profit screen.
- Stock reservation and backorder handling.
- Audit log and correction/reversal workflow.
- Dashboard for receivables ageing and inventory value.
- Read-only auditor workspace with evidence drill-down.
- Tamil/English interface support for floor staff.
- Offline order capture with reliable synchronisation.

### Tier 3 — Stretch features (only after Tier 1 is proven)

- Delivery route planning with vehicle capacity and time windows.
- Transport cost allocation to order/product.
- Market-price reference for selected commodities.
- Demand forecasting with explicit backtesting.
- Batch traceability/recall simulator.
- QR code on production batch or dispatch note.
- Tally-compatible export.
- Mock e-Invoice/e-Way Bill payload format, never represented as a live government connection.
- AI-assisted plain-language variance explanation, strictly read-only and grounded in recorded facts.

**Do not build Tier 3 while any benchmark number is wrong.**

## 4. Features to avoid or postpone

- Microservices: unnecessary for one factory prototype; use a modular monolith.
- Blockchain: adds complexity without improving the ledger's correctness or auditability.
- Facial recognition or continuous GPS tracking: unnecessary and privacy-invasive.
- A generic chatbot as the home screen: it does not solve the business workflow.
- Unverified “AI predicts everything” claims.
- Live government GST filing or e-invoice integration: the brief permits a mock format and does not provide credentials or legal configuration.
- Full double-entry accounting: outside the prototype's core. Provide operational sales, stock, purchase, collection and costing reports, plus accounting export.
- Real customer, supplier or company data: the brief expressly requires dummy/invented data only.

---

# PART C — TECHNICAL ARCHITECTURE

## 5. Recommended stack

Use a maintainable stack Claude Code can implement and test end to end.

| Layer | Recommended technology | Reason |
|---|---|---|
| Web application | React + TypeScript + Vite | Fast, mature, component-driven interface |
| UI system | Tailwind CSS + shadcn/ui or equivalent accessible components | Consistent, clean screens without custom styling everywhere |
| Client data/forms | TanStack Query, React Hook Form, Zod | Server-state, validation and controlled forms |
| Mobile/offline | PWA + IndexedDB through Dexie | Installable salesman workflow and offline order queue |
| API | Python FastAPI + Pydantic | Typed APIs, validation and generated OpenAPI |
| Database | PostgreSQL | Transactions, constraints, decimal types and reliable reporting |
| ORM/migrations | SQLAlchemy 2 + Alembic | Explicit schema and controlled migrations |
| Authentication | Argon2id password hashing + short-lived access tokens + refresh-token rotation, or a clearly justified managed auth adapter | Secure role-aware login without hard-coded demo shortcuts |
| Money/quantity maths | Python Decimal + PostgreSQL NUMERIC | Prevents float drift |
| PDF | HTML invoice/report templates rendered to PDF | Repeatable print output |
| XLSX | openpyxl | Spreadsheet exports |
| Testing | pytest, Hypothesis, Vitest, React Testing Library, Playwright | Unit, property, component and end-to-end testing |
| Local runtime | Docker Compose | One-command reproducible setup |
| Optional routing | OpenStreetMap data + OSRM distance/time matrix + Google OR-Tools | Route estimation and capacity-aware optimisation |
| Optional charts | Recharts or another accessible chart library | Readable operational summaries |

Use stable, compatible versions at implementation time. Pin versions in lockfiles. Do not blindly install “latest” packages without checking compatibility.

### Why a modular monolith

Keep one deployable API and one PostgreSQL database, but enforce module boundaries:

- identity and access
- master data
- procurement
- inventory
- production
- costing
- sales
- GST billing
- dispatch and transport
- collections
- reporting
- audit

This keeps local deployment simple while allowing future extraction of high-load modules if the product actually grows.

## 6. Architecture rules

1. **The inventory movement ledger is the source of truth.** A stock balance is a projection/cache that can be rebuilt and reconciled from ledger entries.
2. **No direct stock overwrite.** Corrections must create an adjustment movement with reason, user, timestamp and reference.
3. **Every movement has a source document.** Purchase receipt, production run, dispatch, return, transfer or adjustment.
4. **Posted records are immutable.** Correct an issued invoice using a credit note/reversal process; do not delete or edit a posted financial document silently.
5. **Money uses decimal/paisa precision.** Store money as integer paise or PostgreSQL NUMERIC with Python Decimal. Never use binary float for money.
6. **Quantities use decimal values in a canonical base unit.** Do not round intermediate conversions.
7. **Every production run snapshots its BOM version.** Future BOM edits cannot rewrite old production history.
8. **Use database transactions for business events.** A production run must not update raw stock without also recording its finished output and source references.
9. **Make critical writes idempotent.** Repeated offline sync or network retries must not duplicate orders, receipts, invoices or payments.
10. **Protect concurrent stock actions.** Lock or version the relevant stock rows while approving/reserving/dispatching orders.
11. **Separate on-hand, reserved and available stock.** Available = on-hand − reserved; do not treat them as the same figure.
12. **Store timestamps in UTC and render in Asia/Kolkata.** Financial reporting uses the configured factory timezone.
13. **All business tables carry organisation scope.** Even with one demo factory, add `organization_id` so the design does not assume one global factory forever.
14. **Every privileged mutation creates an audit event.**
15. **Do not claim legal/tax compliance from a PDF template alone.** The tax configuration and product HSN must be verified by a qualified accountant before production use.

## 7. Core data model

Claude Code should create and document a clear ER diagram. A practical first version includes:

### Identity and configuration
- `organizations`
- `users`
- `memberships`
- `roles`
- `permissions`
- `role_permissions`
- `user_customer_assignments` or salesman territories
- `organization_settings`
- `number_sequences`

### Parties and master data
- `customers`
- `suppliers`
- `addresses`
- `products`
- `product_variants` or SKU pack sizes
- `raw_materials`
- `packaging_items`
- `units`
- `unit_conversions`
- `tax_categories`
- `price_lists`
- `price_list_items`

### Recipes and production
- `bom_headers`
- `bom_versions`
- `bom_lines`
- `production_runs`
- `production_material_issues`
- `production_outputs`
- `production_scrap`
- `production_cost_entries`
- `quality_checks`
- `finished_goods_batches`

### Procurement and lot traceability
- `purchase_orders` (optional)
- `purchase_receipts`
- `purchase_receipt_lines`
- `suppliers`
- `inventory_lots`
- `lot_allocations`

### Inventory
- `inventory_movements`
- `inventory_balances` (rebuildable projection)
- `stock_reservations`
- `stock_counts`
- `stock_adjustments`
- `warehouses` or `locations` (even if initially one factory store)

### Sales and finance operations
- `sales_orders`
- `sales_order_lines`
- `order_status_history`
- `invoices`
- `invoice_lines`
- `invoice_tax_lines`
- `credit_notes`
- `dispatches`
- `dispatch_lines`
- `payments`
- `payment_allocations`
- `customer_balance_snapshots` (optional projection)

### Logistics and analytics
- `vehicles`
- `delivery_routes`
- `route_stops`
- `transport_expenses`
- `demand_forecasts` (optional)
- `alerts`
- `audit_logs`
- `outbox_events`
- `export_jobs`

Use foreign keys, unique constraints, check constraints and indexes. The model must allow a second pack size (for example 500 g) to share or derive from an appropriate recipe without duplicating hard-coded logic.

## 8. Inventory and unit model

Use controlled units and dimensional conversions:

- Mass: kg ↔ g
- Volume: L ↔ mL
- Count: piece, packet, carton
- Carton conversion: 1 carton = configured number of packets, e.g. 20

Do not convert kg to litres without a documented density conversion for that material. Store the unit dimension and conversion factor. Each SKU's stocking unit and each BOM line's usage unit must be explicit.

Suggested stock movement types:

- `OPENING_BALANCE`
- `PURCHASE_RECEIPT`
- `PRODUCTION_ISSUE`
- `PRODUCTION_OUTPUT`
- `PRODUCTION_SCRAP`
- `DISPATCH`
- `SALES_RETURN`
- `PURCHASE_RETURN`
- `STOCK_ADJUSTMENT`
- `TRANSFER_IN`
- `TRANSFER_OUT`
- `EXPIRY_WRITE_OFF`

Use signed quantity deltas in canonical units, but keep the movement type and source document explicit. For lot-tracked items, every movement must identify the lot where applicable.

## 9. Production variance model

For each BOM line:

- planned quantity = BOM quantity per batch × batch multiplier
- actual quantity = total issued quantity for the production run
- quantity variance = actual − planned
- variance percentage = `(actual − planned) / planned × 100`
- absolute variance above the configured tolerance triggers an alert
- favourable and unfavourable variance should be distinguished

For output:

- expected good output = BOM expected output × batch multiplier
- actual good output = accepted saleable packets
- yield variance % = `(actual good output − expected good output) / expected good output × 100`

Record separately:
- good output
- food-process scrap/rejects
- packaging damage
- rework
- unclassified loss

Do not add damaged pouches to good output. Do not treat damaged packaging as finished-goods packets. Require an operator to choose a reason when recording a loss, while allowing `UNKNOWN` where the cause is genuinely not known.

## 10. Costing method

Use **perpetual moving weighted-average cost** for raw-material inventory in this prototype. This is easy to explain and fits the opening-balance-plus-purchase benchmark.

For each stock receipt:
`new weighted average = (old stock value + receipt value) / (old stock quantity + receipt quantity)`

For each production run:
`material cost = sum(actual issued quantity × applicable weighted-average unit cost)`

`total run cost = material cost + direct labour + gas/power + other explicitly assigned run overhead`

`cost per good packet = total run cost / actual good packets`

Do not divide by expected packets when actual good output is lower. Preserve the cost snapshot on the posted production run so later price changes do not rewrite old costs.

Transport should be shown separately from factory manufacturing cost, then optionally included in delivered contribution margin. This avoids hiding the difference between production cost and delivery cost.

## 11. GST and invoice model

The benchmark explicitly fixes the exercise tax rate at 5%. Make tax rules configurable and effective-dated by product tax category/HSN and place of supply.

For the given exercise:
- Tamil Nadu supplier → Tamil Nadu customer: 2.5% CGST + 2.5% SGST.
- Tamil Nadu supplier → Karnataka customer: 5% IGST.
- Retailer A taxable value: ₹7,500.
- CGST: ₹187.50.
- SGST: ₹187.50.
- Invoice total: ₹7,875.
- Payment: ₹4,000.
- Outstanding: ₹3,875.

Include supplier GSTIN, invoice number and date, recipient details, HSN, description, quantity/UQC, taxable value, tax rate and tax amount, place-of-supply details where relevant, and the other fields required by the configured invoice template.

The problem statement does not supply an actual company GSTIN, customer GSTIN or confirmed HSN classification. Use visibly fictional demo data and an HSN field that is clearly marked for accountant verification. Do not invent a real company's identity or present an unverified HSN as legally correct. The prototype's GST summary should be described as an export shape that maps to GSTR-1/GSTR-3B concepts, not an actual filing.

---

# PART D — BENCHMARK CALCULATION CONTRACT

## 12. Exact seed data and required expected outcomes

This section is a contract. Implement the benchmark as a repeatable automated scenario and do not change its inputs.

### 12.1 Opening stock and flour purchase

| Item | Opening quantity | Opening rate | New receipt | Receipt rate |
|---|---:|---:|---:|---:|
| Flour | 100 kg | ₹42/kg | 60 kg | ₹45/kg |
| Cooking oil | 30 L | ₹140/L | — | — |
| Salt and spice mix | 5 kg | ₹200/kg | — | — |
| 200 g pouch | 500 pieces | ₹2.50/piece | — | — |
| Carton | 30 pieces | ₹15/piece | — | — |
| Murukku 200 g | 50 packets | — | — | — |

After the flour receipt, moving weighted-average flour cost is:

`(100 × ₹42 + 60 × ₹45) / 160 = ₹43.125/kg`

### 12.2 Production run

BOM standard for one batch:
- flour 40 kg
- cooking oil 10 L
- salt/spice mix 1.2 kg
- 200 g pouches 200 pieces
- cartons 10 pieces
- expected good output 200 packets

Actual:
- flour issued 40 kg
- oil issued 10.5 L
- spice mix issued 1.2 kg
- good output 188 packets
- damaged pouches 6 pieces
- total pouches consumed = 188 + 6 = 194 pieces
- cartons used = 9 pieces
- labour = ₹1,200
- gas/power = ₹600

### 12.3 Expected stock states

| Checkpoint | Expected |
|---|---:|
| Flour after purchase and issue | 120 kg |
| Oil after production issue | 19.5 L |
| Spice mix after production issue | 3.8 kg |
| Pouches after 194 used | 306 pieces |
| Cartons after 9 used | 21 pieces |
| Finished goods after production | 238 packets |
| Finished goods after 150 packet dispatch | 88 packets |

### 12.4 Expected variance states

- Yield: `(188 − 200) / 200 = −6%`, flagged.
- Oil: `(10.5 − 10) / 10 = +5%`, flagged.
- Pouches: 194 consumed against 200 planned, a −3% quantity variance; record the 6 damaged pouches as a separate packaging-loss event. Do not hide damage merely because total pouch consumption is below the BOM standard.
- Cartons: 9 used against 10 planned, with 188 good packets. The system should permit a partially filled carton/loose-packet explanation rather than silently assuming all cartons are full.

### 12.5 Cost per packet calculation

Using moving weighted-average flour valuation:

| Component | Calculation | Cost |
|---|---:|---:|
| Flour | 40 × ₹43.125 | ₹1,725 |
| Cooking oil | 10.5 × ₹140 | ₹1,470 |
| Spice mix | 1.2 × ₹200 | ₹240 |
| Pouches | 194 × ₹2.50 | ₹485 |
| Cartons | 9 × ₹15 | ₹135 |
| **Material total** | | **₹4,055** |
| Labour | Direct run expense | ₹1,200 |
| Gas/power | Direct run expense | ₹600 |
| **Total run cost** | | **₹5,855** |

`₹5,855 / 188 good packets = ₹31.143617...`

Display **₹31.14 per good packet**, while retaining full internal precision and documenting the rounding policy.

Useful comparisons:
- Potential sales value of 12 missing packets at ₹50 before tax = ₹600. This is not the same as lost profit.
- Extra oil cost = 0.5 L × ₹140 = ₹70.
- Damaged pouch cost = 6 × ₹2.50 = ₹15.
- Actual unit cost should be higher than a theoretical full-yield unit cost because the run produced fewer good packets and used extra oil.

### 12.6 Sales and collection

Retailer A:
- 150 packets × ₹50 = ₹7,500 taxable.
- CGST 2.5% = ₹187.50.
- SGST 2.5% = ₹187.50.
- Total = ₹7,875.
- Dispatch 150 packets.
- Remaining finished goods = 88 packets.
- Payment = ₹4,000.
- Outstanding = ₹3,875.

Distributor B:
- 120 packets requested.
- Only 88 available after Retailer A dispatch.
- Shortage = 32 packets.
- Flag insufficient stock and offer backorder/partial fulfilment.
- If an invoice is eventually issued to the Karnataka customer, the configured tax engine should choose IGST for the inter-state supply under the exercise assumptions.

### 12.7 Benchmark acceptance

The application must provide a `run_benchmark` or equivalent deterministic command/test that:
1. Resets only the benchmark demo tenant/database fixture.
2. Loads exact master data and opening stock.
3. Posts the 60 kg flour receipt.
4. Posts the production run.
5. Places and approves Retailer A's order, invoices and dispatches it.
6. Places Distributor B's order and records the shortage.
7. Records the payment and run expenses.
8. Generates report data.
9. Asserts every expected number above.
10. Produces a readable pass/fail summary.

The benchmark must be repeatable. Re-running it must not duplicate financial or stock events. It should reset a dedicated demo dataset or use a dedicated idempotent scenario key.

---

# PART E — DATASETS, PREPROCESSING AND ANALYTICS

## 13. Do not confuse ERP data with machine-learning training data

The core application does **not** need a trained AI model to calculate stock, GST, BOM consumption, cost per packet or outstanding dues. These are deterministic business rules. A model should never be allowed to decide a financial ledger entry.

Use three separate data layers:

### Layer A — Authoritative benchmark fixture

- Exactly the NIT-provided section 5 data.
- Stored in a versioned seed file and a deterministic seed script.
- Used for the demo video and automated acceptance tests.
- Never used as a training set.
- Never altered to improve a model score.

### Layer B — Synthetic longitudinal factory dataset

Generate synthetic—not real—business activity to test trends and analytics.

Recommended demo scale:
- 24 months of daily/weekly transactions.
- 1 fictional factory.
- 5–15 fictional salesmen.
- 80–150 fictional retailers/distributors.
- 12–25 fictional SKUs across 200 g, 500 g and other pack sizes.
- 15–30 raw/packaging material items.
- 5–10 fictional suppliers.
- Multiple BOM versions.
- Purchase receipts with variable lead times and prices.
- Production runs with controlled yield/consumption variation.
- Sales with weekday, seasonality and festival-like peaks.
- Partial dispatches, returns, delayed collections and stock-outs.
- Synthetic routes and vehicle capacities.
- Lots with made-up expiry dates for FEFO/recall testing.

Use a fixed random seed. Provide a generator configuration so another developer can reproduce the same dataset. Put synthetic-data labels on every demo screen/report where confusion with actual records is possible.

### Layer C — Optional contextual public data

The Government of India's Open Government Data platform has daily mandi commodity-price resources with state, district, market, commodity and variety fields. Use it only as a **market reference signal** for selected raw materials where a meaningful mapping exists. It is not a substitute for the factory's actual supplier invoice and must never update the stock valuation automatically.

For each imported data file:
- record publisher, source URL, download timestamp, licence/terms and source identifier;
- preserve an unmodified raw copy;
- map original column names to a versioned internal schema;
- normalise state/district/market/commodity names carefully;
- parse dates and numeric prices;
- reject or quarantine malformed rows;
- handle missing values explicitly;
- detect duplicate market/date/commodity observations;
- keep source currency and unit;
- never mix ₹/quintal with ₹/kg without an explicit conversion;
- log every transformation.

Do not use an unrelated retail dataset as if it represented South Indian snack-manufacturing demand. If an external retail dataset is used for a technical ingestion experiment, explain its geography, product mismatch and limitations.

## 14. Dataset preprocessing rules

For synthetic transaction data:
1. Validate primary keys and foreign keys.
2. Check chronology: order → approval → invoice → dispatch → payment.
3. Enforce non-negative quantities unless the movement type explicitly represents a return/reversal.
4. Normalise all units to canonical units for calculations.
5. Retain original entered units and converted quantities for auditability.
6. Separate training, validation and test periods by time, not random row split.
7. Preserve cancellation/return semantics; do not delete negative or reversed transactions as generic outliers.
8. Detect duplicate sync IDs and duplicate source documents.
9. Track missing customer/product/price fields and quarantine invalid records.
10. Store generator seed and dataset version.

For mandi-price data:
- validate the commodity and market-to-material mapping;
- use a date-based time split;
- do not fill long missing periods with fabricated values;
- document unit conversions;
- show source freshness and missingness;
- never present mandi prices as a guaranteed supplier quotation.

## 15. Optional forecasting and anomaly analytics

Build only after transaction capture, BOM, inventory and cost are correct.

### Demand forecasting

Target: weekly SKU demand, not an unexplained “AI demand score”.

Start with baselines:
- last-week/last-four-week moving average;
- seasonal-naive baseline;
- simple exponential smoothing where appropriate.

Only then evaluate a model such as LightGBM or another suitable tabular/time-series approach if there is enough historical signal.

Evaluation:
- rolling-origin time-series backtesting;
- compare against baselines;
- WAPE and MAE (and a clearly defined treatment for zero actual demand);
- segment by SKU and forecast horizon;
- prediction intervals or uncertainty bands;
- show forecast error and data coverage;
- record model version and feature window.

Data sufficiency gate:
- If there is insufficient history, show “not enough reliable history” and fall back to the transparent baseline.
- Synthetic-data performance must be labelled synthetic and must not be represented as real factory accuracy.
- Do not make production decisions automatically from a forecast. The planner recommends; the admin/owner approves.

### Production anomaly detection

Use deterministic rules first:
- consumption variance above configured tolerance;
- yield variance below configured threshold;
- repeat damage rate above threshold;
- repeated supplier lot/quality issues;
- unusually high cost per good packet.

An optional anomaly model can be explored after enough real, labelled production history exists. Explain false positives and never block production based solely on a model.

### AI explanation (optional)

An AI layer may turn recorded facts into a plain-language explanation in English or Tamil. It must:
- receive only the specific authorised records needed;
- cite run ID, BOM version, movement IDs and calculations;
- clearly distinguish facts from hypotheses;
- never write to stock, invoice, payment or production tables;
- never invent a root cause;
- work without an external LLM for core operation.

---

# PART F — TRANSPORT, EXPENSES, INVESTMENT AND SOCIAL VALUE

## 16. Transport module

The brief asks for salesman route/visit log as a stretch goal; transport can become a stronger differentiator if modelled as an operational cost feature rather than a decorative map.

### 16.1 Separate two journeys

- **Salesman visit route:** customer visits, check-in, order taking and visit outcome.
- **Delivery route:** approved dispatches, vehicle capacity, delivery windows and trip costs.

Do not mix these two route types in one dashboard.

### 16.2 Delivery route planning

Inputs:
- factory/depot;
- synthetic customer delivery coordinates or geocoded dummy addresses;
- orders ready for dispatch;
- packet/carton weight or volume;
- vehicle capacity;
- delivery time windows;
- expected loading/unloading time;
- vehicle fixed trip cost;
- variable cost per kilometre;
- driver allowance and toll/parking cost, where applicable.

Process:
1. Filter orders whose goods are actually available and ready.
2. Build a distance/time matrix.
3. Solve a capacitated vehicle-routing problem with time windows where practical.
4. Show route sequence, estimated distance/time and capacity utilisation.
5. Allow the dispatcher to edit/approve the route.
6. Record planned versus actual trip distance and expense.
7. Allocate transport cost by a documented rule (weight, volume, packet count, or stop-level cost).
8. Show delivery cost per order and contribution margin after estimated delivery expense.

Use OSRM as a prototype routing adapter and Google OR-Tools for capacity/time-window optimisation. Do not depend on a public demo routing endpoint for a production service; use an appropriately hosted service/provider and respect map-data attribution/licensing. Do not track an employee continuously. A one-time visit check-in should be opt-in, visible and limited to work purposes.

### 16.3 Delivery cost formula

A transparent starter estimate:

`fuel cost = route km × vehicle fuel consumption (L/100 km) ÷ 100 × fuel price per L`

`trip cost = fuel cost + driver allowance + fixed vehicle cost + tolls + parking + other entered expense`

`delivery cost per packet = allocated trip cost / packets delivered`

All inputs must be editable and labelled as estimates until actual expenses are recorded. Do not assume a particular vehicle, fuel rate or fuel price without documenting the assumption.

## 17. Expense and capital plan

The prototype should be buildable without purchasing factory equipment. Use existing laptop/phone devices and dummy data.

### Prototype/student build

| Item | Expected approach |
|---|---|
| Development machine | Existing laptop |
| Local database/API/frontend | Docker Compose; no cloud requirement |
| Seed data | Generated locally |
| PDF/XLSX | Open-source libraries |
| Maps | Disabled or dummy map until the core is complete |
| Domain | Optional |
| Demo hosting | Free/low-cost tier if available, with its limitations documented |

### Illustrative small-factory pilot budget

These are planning estimates, not vendor quotations. Check current local prices before purchasing.

| Item | Indicative one-time range |
|---|---:|
| Android tablet for production desk (optional if existing device is available) | ₹10,000–₹18,000 |
| Thermal invoice printer (optional) | ₹5,000–₹10,000 |
| Barcode/QR scanner (optional) | ₹1,500–₹4,000 |
| UPS/router/backup connectivity allowance | ₹3,000–₹8,000 |
| QR labels and basic stationery | ₹500–₹2,000 |
| **Indicative optional hardware total** | **₹20,000–₹42,000** |

Monthly operating budget to model:
- hosting/database;
- domain (annual, if required);
- backup/storage;
- internet/backup connectivity;
- SMS/WhatsApp messaging if later enabled;
- support and maintenance;
- map/routing provider if using a paid provider.

For a student demo, a local run command can keep software hosting cost at ₹0. A free hosted database may have limits, inactivity pauses or no production-grade backup; never describe a free tier as a resilient factory deployment. The current provider pricing pages should be checked at deployment time.

### Working-capital intelligence

Add a compact owner report:
- raw-material stock value;
- packaging stock value;
- finished-goods stock value;
- receivables outstanding and ageing;
- slow-moving/near-expiry inventory;
- supplier price movement;
- cash tied up in stock;
- stock-out risk against pending orders.

Do not label all stock value as a loss. Explain that it is working capital tied up in inventory.

## 18. ROI and social-impact measurement

Do not promise savings without a baseline. Measure before/after during a small pilot.

| Impact measure | How to calculate |
|---|---|
| Order re-entry time saved | Old manual entry time − new order-entry/admin correction time |
| Month-end preparation time | Hours spent assembling reports before vs after |
| Material variance cost | Actual issue cost − BOM-standard issue cost, with favourable/unfavourable labels |
| Yield improvement | Saleable output per batch before vs after |
| Expiry/write-off reduction | Value of expiry losses over comparable periods |
| Stock-out reduction | Number of orders delayed for stock reasons |
| Collection visibility | Percentage of invoices with allocation and current ageing |
| Delivery efficiency | Actual distance/cost per successful delivery before vs after |
| Audit traceability | Time needed to trace a finished batch to raw-material lots and invoices |

Potential social value:
- gives small manufacturers better control without requiring a large ERP implementation;
- reduces avoidable raw-material and packaging waste;
- improves food-batch traceability and speed of investigating quality issues;
- makes production instructions and records more accessible to floor workers;
- helps owners understand real product margins and working-capital pressure;
- reduces avoidable delivery kilometres when route consolidation is feasible;
- improves the reliability and timeliness of records provided to accountants.

The product should measure these benefits rather than claim they have already occurred.

---

# PART G — UI/UX BLUEPRINT

## 19. Design principle

The UI should be operational, not decorative. A person using the factory tablet with limited time should complete a production run without navigating through accounting jargon. A salesman should be able to create a normal order in under one minute.

Use a quiet, light visual system:
- light neutral background;
- one restrained primary colour;
- high-contrast text;
- clear status labels;
- large touch targets;
- readable tables;
- consistent spacing;
- no excessive gradients, glass effects or animated cards;
- no dashboard full of meaningless charts;
- meaningful empty, loading, offline, error and success states.

### 19.1 Role-based navigation

**Salesman — mobile-first**
- New Order
- My Orders
- My Customers
- Sales Summary
- Sync Status

**Admin — desktop-first**
- Overview
- Order Inbox
- Customers
- Products & Prices
- Inventory
- Purchases
- Invoices
- Dispatch
- Collections
- Reports

**Production supervisor — tablet-first**
- Today's Production
- Start Production Run
- Material Issue
- Output & Wastage
- Batch History
- Raw Material Stock

**Owner — summary-first**
- Business Overview
- Production Losses
- Product Cost & Margin
- Inventory & Reorder
- Receivables
- Delivery Cost
- Traceability

**Accountant/auditor — read-only**
- Monthly Summary
- Sales Register
- GST Summary
- Purchase Register
- Stock Ledger
- Production Variance
- Collections/Ageing
- Audit Trail
- Export Centre

### 19.2 Critical UX flows

**Salesman quick order**
1. Select customer.
2. Search/select SKU.
3. Enter quantity; show price and line total.
4. Review and submit.
5. If offline, show “Saved on this device — waiting to sync”, not “Submitted to factory”.

**Admin approval**
1. Open order inbox.
2. Inspect customer, price, stock availability and shortage.
3. Adjust quantity/price with a recorded reason.
4. Approve, reject or backorder.
5. Generate invoice only according to valid stock/status policy.

**Production run**
1. Select product and BOM version.
2. See planned materials/output.
3. Enter actual issued quantities.
4. Enter good output, scrap, packaging damage and reason.
5. Enter labour/energy costs.
6. Preview variances and total stock impact.
7. Post the run once; show a source-linked movement summary.

**Auditor**
- Choose month/date range.
- Review summary totals.
- Drill into any number to the underlying invoice, purchase or movement.
- Export CSV/XLSX/PDF with timestamp, filters and valuation/tax assumptions.

### 19.3 Accessibility and language

- Keep English as the initial default.
- Add Tamil labels for production floor workflows as a high-value enhancement.
- Use translation dictionaries; do not duplicate entire screens.
- Use clear Tamil labels validated by a fluent speaker.
- Preserve numerals, units, product codes and invoice references consistently.
- Use icons with text labels, not icons alone.
- Provide keyboard navigation and accessible form errors.
- Do not use colour alone to communicate stock shortage or variance.

---

# PART H — CLAUDE CODE EXECUTION CONTRACT

## 20. How Claude Code must work

Paste prompts in sequence. Do not ask Claude to build everything in one pass.

### Rules for every prompt

1. Read the full NIT problem statement and this blueprint before changing code.
2. Inspect the current repository and report the actual state; never assume a new or empty repository.
3. Preserve working code unless there is a documented reason to change it.
4. Do not silently skip requirements.
5. Do not fabricate successful commands, tests, deployments, integrations or screenshots.
6. Never claim “PASS” unless the relevant command ran and its result was inspected.
7. For blocked tests, state the blocker, exact command and missing prerequisite.
8. Make small, coherent commits or stop at a manual checkpoint. The user controls Git commits/pushes.
9. Do not commit secrets, `.env` files, real customer data, generated private data or credentials.
10. Keep the benchmark data exact.
11. Do not start the next master prompt automatically.
12. At the end of each prompt, produce a concise completion report: files changed, migrations, commands run, test results, known gaps and the exact next step.
13. If a design decision affects money, stock, tax, units, audit or data retention, document the decision and add a test.
14. Do not add external services unless the feature genuinely needs them and a local/mock fallback exists.
15. Ask before destructive operations, database resets outside the dedicated demo tenant, force pushes, secret rotations or production migrations.

### Expected repository structure

Claude may adapt this structure to an existing repository, but must keep the boundaries clear:

```text
aaharos/
  apps/
    web/
      src/
        app/
        components/
        features/
          auth/
          orders/
          inventory/
          production/
          billing/
          reports/
          owner/
        lib/
        offline/
        locales/
  backend/
    app/
      api/
      core/
      domain/
      models/
      schemas/
      services/
        identity/
        procurement/
        inventory/
        production/
        costing/
        sales/
        billing/
        dispatch/
        reporting/
        audit/
      repositories/
      tests/
    alembic/
  data/
    benchmark/
    synthetic/
    external/
  docs/
    architecture/
    design-note.md
    benchmark.md
    data-dictionary.md
    security.md
    demo-script.md
  scripts/
    seed_benchmark.py
    generate_synthetic_data.py
    run_benchmark.py
  infra/
    docker/
  docker-compose.yml
  README.md
```

---

# PART I — MASTER PROMPTS (00–19)

Copy one prompt at a time into Claude Code.

## MP00 — Repository reconnaissance and requirements lock

**Objective:** Understand the repository, extract the NIT requirements and produce a verified implementation plan before coding.

```text
You are the principal software architect and implementation lead for AaharOS, an individual NIT Trichy internship submission.

Read these documents completely:
1. Problem Statement - Winter Internship Application - 2026 .md
2. AaharOS_NIT_Trichy_Claude_Code_Master_Prompt_Pack.md

Do not begin feature implementation yet.

First inspect the full repository: files, directories, package manifests, existing frontend/backend, database, migrations, tests, Docker files, Git state and current run instructions. Do not assume it is empty. Do not overwrite working code merely to match a proposed folder structure.

Create:
- docs/requirements-traceability.md: map every explicit requirement to a planned module, API, UI screen, data model and test.
- docs/architecture/initial-architecture.md: system boundaries and architecture decision record.
- docs/architecture/implementation-roadmap.md: dependency-aware phases and acceptance gates.
- docs/known-assumptions.md: only assumptions not specified in the NIT brief.
- docs/benchmark-contract.md: exact benchmark input and expected results.

Classify requirements as:
A. NIT mandatory,
B. NIT should-have,
C. NIT stretch,
D. AaharOS differentiator,
E. explicitly excluded.

Identify missing input data in the problem statement: factory GSTIN, recipient GSTIN, confirmed HSN, complete addresses, financial-year starting sequence, tax configuration effective dates and any supplier/customer metadata. Do not fabricate real identities or claim legal HSN correctness.

Architecture constraints:
- modular monolith;
- PostgreSQL;
- React/TypeScript responsive PWA;
- FastAPI/Python API unless the existing repository has a justified compatible stack;
- ledger-based stock;
- decimal/integer-paisa arithmetic;
- immutable posted documents with reversals;
- auditable user/time/source references;
- Docker Compose local run.

Do not add blockchain, microservices, AI chatbot-first navigation or unnecessary cloud dependencies.

Inspect and report:
- exact current Git branch and dirty/clean status;
- runtime versions;
- existing tests and their current results;
- any secrets/configuration files (report presence only; never print secret values);
- any existing schema that should be preserved;
- deployment constraints.

End with the first implementation phase and a list of unresolved risks. Do not implement MP01 or later until this report is reviewed.
```

**Acceptance gate:** Requirements traceability exists; the exact benchmark has been transcribed without changing values; repository state is known; no unrequested destructive change occurred.

## MP01 — Product experience, information architecture and UX prototype

**Objective:** Design the interface around each person's actual task.

```text
Implement the AaharOS user experience and navigation architecture.

Before coding, reread the UI/UX blueprint and NIT role table. Build separate experiences for:
1. Salesman — mobile-first, quick order in under one minute.
2. Factory admin — desktop-first order verification, billing, stock and dispatch.
3. Production supervisor — touch-friendly tablet workflow.
4. Owner — concise operational and financial intelligence.
5. Accountant/auditor — read-only reports and evidence drill-down.

Build a coherent design system:
- light neutral background;
- restrained primary colour;
- typography and spacing scale;
- accessible buttons, inputs, tables, dialogs and status chips;
- loading, empty, error, offline and success states;
- responsive layouts;
- keyboard-accessible controls;
- no meaningless dashboard charts or decorative complexity.

Build the navigation map and working page shells. Every page must have a clear purpose and role permission. Use realistic synthetic labels, but do not create random financial numbers that could be mistaken for persisted data.

Design these workflows first:
A. salesman creates an order;
B. admin verifies stock and approves/rejects/backorders;
C. production supervisor records a batch;
D. auditor filters and drills into a month-end report;
E. owner opens a production variance and sees its source records.

Use the existing component framework if one already exists. Avoid installing competing UI libraries. Add responsive tests for important layouts.

Deliver a page inventory and a short design note explaining why each role sees only the actions relevant to it. Do not begin complex business logic here.
```

**Acceptance gate:** Each role has a coherent shell; no user sees controls they cannot use; the salesman workflow is visibly short; layouts work on mobile and desktop.

## MP02 — Domain model, ER diagram and business invariants

**Objective:** Agree on the data model before implementing stock and finance code.

```text
Design the complete AaharOS domain model from the NIT brief.

Produce:
- docs/architecture/erd.mmd or another renderable ER diagram;
- docs/data-dictionary.md;
- docs/architecture/business-invariants.md;
- docs/architecture/decision-records.md.

Cover:
organizations, users, roles/permissions, customers, suppliers, addresses, products/SKUs/pack sizes, raw materials, packaging, units/conversions, price lists, tax categories, BOM versions/lines, purchases/receipts, lots, inventory movements, balance projections, stock reservations, production runs, issues, outputs, scrap, quality checks, cost entries, sales orders, status history, invoices, tax lines, credit notes, dispatches, payments/allocations, transport, audit logs and reporting/export jobs.

Define invariants explicitly:
- no negative available stock;
- all posted movements have source references;
- balances reconcile to movement ledger;
- posted invoices are not deleted;
- corrections use reversal/credit-note flows;
- every production run uses a frozen BOM version;
- one offline idempotency key cannot create duplicate orders;
- a payment cannot be allocated above its unallocated amount;
- a dispatch cannot exceed reserved/available finished goods;
- units must be dimension-compatible;
- financial values never use float;
- tenant/organization scoping applies to all operational records.

Define the relationship between stock on-hand, reserved and available. Define how partial dispatch/backorder works. Define how returns and reversals affect the ledger.

Pay special attention to the interview change request: adding a 500 g pack size that shares a recipe must not require hard-coded logic or destructive schema changes.

Do not generate migrations until the model and invariants are documented and internally consistent. Identify unresolved decisions rather than hiding them.
```

**Acceptance gate:** ERD and invariants are understandable, cover the benchmark and support an additional pack size without redesign.

## MP03 — Database foundation and migrations

**Objective:** Implement a strong PostgreSQL schema.

```text
Implement the approved AaharOS database model using PostgreSQL, SQLAlchemy 2 and Alembic (or the existing equivalent).

Requirements:
- use NUMERIC with explicit precision/scale for money and fractional stock quantities;
- use foreign keys, unique constraints, check constraints and indexes;
- use organization_id consistently;
- use UTC timestamps;
- preserve source-document references;
- define immutable/append-only behaviour for posted stock movements and financial documents at service/database policy level;
- create separate tables for inventory movements and rebuildable inventory balance projections;
- create stock reservations separately from on-hand;
- support BOM version snapshots and product variants/pack sizes;
- include audit fields and created/updated actor references where appropriate;
- store invoice sequence by financial year and organization;
- model payment allocations separately from payments;
- use database transactions for multi-table posting workflows.

Create migrations that can be applied to a clean database. If an existing database is present, inspect it and produce a safe migration plan; never drop or reset it without explicit approval.

Add migration tests and a database initialization path for Docker Compose. Seed only roles/system configuration at this point; benchmark seeding comes later.

Deliver a schema diagram, migration instructions, rollback notes and data dictionary updates. Run all migrations and tests, and report actual command outputs accurately.
```

**Acceptance gate:** Clean database can be created from migrations; constraints enforce core invariants; no destructive action was made to an existing database.

## MP04 — Authentication, role-based access and audit foundation

**Objective:** Implement real access control, not merely different navigation menus.

```text
Implement authentication and backend-enforced role-based access for AaharOS.

Roles:
- SALESMAN
- ADMIN
- PRODUCTION
- ACCOUNTANT_AUDITOR (read-only)
- OWNER

Requirements:
- secure password hashing using Argon2id or an established secure implementation;
- short-lived access token/session;
- refresh-token rotation and revocation if JWT is used;
- secure cookie/token handling; do not store long-lived secrets in localStorage;
- logout and session expiry;
- demo accounts generated through seed configuration, never hard-coded production passwords;
- organisation scoping;
- salesman can access only assigned customers and own orders;
- production can access production and stock tasks needed for its role, not finance administration;
- admin can manage orders, billing and operational masters;
- accountant/auditor is read-only for posted business data and exports;
- owner gets dashboard and approved management functions.

Every write endpoint must enforce permissions on the backend. Hiding a button is not security.

Create an audit logging service with actor, action, entity type/id, timestamp, request/correlation ID and before/after summary. Never log passwords, tokens or sensitive secrets.

Test direct API access for forbidden actions and cross-organization record access. Include positive and negative authorization tests for every role.

Document the demo test accounts and their intended permissions without exposing real credentials.
```

**Acceptance gate:** API-level RBAC tests pass; auditor cannot mutate records; salesman cannot read another salesman's customers/orders.

## MP05 — Units, inventory ledger and stock reconciliation engine

**Objective:** Build the most important source-of-truth subsystem.

```text
Implement the inventory domain before building production or dispatch.

Required features:
- item master for raw materials, packaging and finished goods;
- canonical base units and dimension-safe conversions;
- separate mass, volume and count dimensions;
- conversion definitions for kg/g, L/mL and configured packet/carton relationships;
- lot/batch reference support;
- immutable inventory movement records;
- rebuildable current-balance projection;
- available quantity = on_hand − reserved;
- stock ledger filterable by item, date, lot and source document;
- opening balance and authorised adjustment workflows;
- reconciliation command that recomputes balances from movements and compares them with projections;
- movement source links and actor/timestamp;
- idempotency for stock posting.

Never allow ordinary users to directly overwrite the stock balance. A physical count difference must become a reviewed adjustment with a reason and audit event.

Implement transaction-safe functions for:
- receive;
- issue;
- output;
- dispatch;
- return;
- adjustment;
- reserve/unreserve.

Add property-based tests for:
opening + receipts − issues + outputs − dispatches ± adjustments = closing balance.
Test mixed units, fractional quantities, multiple transactions and rounding boundaries.

Do not use floats. Do not silently clamp a negative balance to zero. Reject invalid transactions with a clear error. Add a ledger rebuild CLI and test it.
```

**Acceptance gate:** All movements reconcile; no negative available stock; mixed-unit calculations are correct; ledger source references are present.

## MP06 — Procurement, suppliers and lot receiving

**Objective:** Record incoming raw and packaging material with cost and traceability.

```text
Implement supplier master, purchase receipt and receipt-line workflows.

Requirements:
- supplier details and state/GST fields as fictional configurable demo data;
- purchase receipt number and date;
- item, quantity, unit, rate, taxable/other cost fields where applicable;
- receiving location;
- supplier invoice/reference;
- lot number, manufactured date and expiry date where provided;
- reject/quarantine/accepted quantity if quality inspection is used;
- stock movement creation for accepted quantities;
- purchase register;
- receipt correction through reversal/adjustment, not silent overwrite;
- purchase document audit history.

For the benchmark, seed opening flour 100 kg at ₹42/kg and receive 60 kg flour at ₹45/kg. The moving weighted-average rate after receipt must be ₹43.125/kg.

Keep supplier price, tax, freight and landed-cost components distinct. Explain which components enter inventory valuation and how the choice is documented. Do not let a market reference feed automatically into book stock valuation.

Add tests for duplicate receipt submissions, unit conversion, invalid negative quantities, lot traceability and weighted-average valuation.
```

**Acceptance gate:** Receipt creates exactly one source-linked movement; weighted average matches the benchmark; repeated requests cannot double-receive stock.

## MP07 — BOM, recipe versioning and production run engine

**Objective:** Implement the central differentiator of the assignment.

```text
Implement the BOM and production-run modules with production-grade transaction semantics.

BOM requirements:
- finished SKU/product;
- version number and effective dates;
- expected batch yield;
- raw-material and packaging lines;
- quantities and units;
- tolerance per line or configurable product-level tolerance;
- approval/active version status;
- immutable snapshot copied into each posted production run.

Production-run requirements:
- select product and BOM version;
- batch multiplier;
- calculated expected consumption;
- actual issued material/packaging;
- actual good output;
- process scrap/rejects;
- packaging damage;
- rework and reason codes;
- operator/supervisor;
- timestamps;
- lot allocation where available;
- production costs captured as separate entries;
- atomic posting of raw stock issues, finished-goods output and variance snapshot.

A run must not partially post. If any stock movement or output fails, the whole transaction must roll back.

For the benchmark, reproduce exactly:
- one batch expects 200 Murukku 200 g packets;
- actual flour 40 kg;
- actual oil 10.5 L;
- actual spice mix 1.2 kg;
- 188 good packets;
- 6 damaged pouches;
- 9 cartons used;
- 194 pouches consumed in total.

Expected inventory after production:
flour 120 kg, oil 19.5 L, spice 3.8 kg, pouches 306, cartons 21, finished goods 238 packets.

Flag yield variance −6% and oil consumption variance +5% at a 3% tolerance. Record pouch damage separately. Explain that pouches consumed are 194, not 188. Do not infer a cause for the yield loss.

Support future pack-size changes through SKU/recipe data, not hard-coded special cases. Add rollback, duplicate-submit and concurrency tests.
```

**Acceptance gate:** One run posts all expected movements atomically; stock balances match; BOM changes do not rewrite older runs.

## MP08 — Costing, variance intelligence and production-loss screen

**Objective:** Turn production data into owner decisions.

```text
Implement production costing and the AaharOS Loss-to-Profit experience.

Costing:
- use perpetual moving weighted-average valuation for this prototype;
- calculate material cost from actual issue quantities and applicable cost snapshot;
- include direct labour and run-level gas/power costs;
- calculate cost per actual good packet;
- preserve the posted cost snapshot;
- distinguish manufacturing cost from delivery cost;
- show selling price excluding tax and contribution margin without treating GST as revenue.

Benchmark:
flour 40 × ₹43.125 = ₹1,725
oil 10.5 × ₹140 = ₹1,470
spice 1.2 × ₹200 = ₹240
pouches 194 × ₹2.50 = ₹485
cartons 9 × ₹15 = ₹135
materials = ₹4,055
labour = ₹1,200
gas/power = ₹600
total run cost = ₹5,855
good output = 188
unit cost = approximately ₹31.14 per good packet.

Build a variance view showing:
- planned and actual quantities;
- variance quantity and percentage;
- favourable/unfavourable label;
- threshold and whether it was breached;
- rupee impact where a defensible rate exists;
- source run and movement links.

Show the benchmark:
- yield −6%;
- oil +5%, ₹70 extra oil cost;
- 6 damaged pouches, ₹15 packaging cost;
- 12-packet potential sales value ₹600, clearly labelled as potential value, not profit.

Recommendations must be deterministic and evidence-based at first. Example: “Oil issue exceeded the BOM by 0.5 L (5%, ₹70 at the current valuation rate). Review the next run's measurement and issue process.” Do not claim the oil excess caused the yield loss. Provide unknown/other reason options.

Add tests for valuation, overhead allocation, division by zero, rounding, reversals and cost snapshot stability.
```

**Acceptance gate:** Cost equals ₹5,855 total and about ₹31.14 per good packet; variance facts are linked to source entries.

## MP09 — Salesman PWA and resilient offline order capture

**Objective:** Make the field-sales workflow excellent under weak network conditions.

```text
Implement the mobile-first salesman experience as an installable PWA.

Workflow:
- authenticate;
- select only assigned customer;
- add product/SKU and quantity;
- show approved price list and any valid customer-specific pricing;
- show line total and order total;
- add optional notes;
- submit;
- view own order status and customer-wise sales summary.

Offline:
- cache only the minimum required product/price/customer data;
- store unsent order drafts in IndexedDB;
- assign a stable UUID/idempotency key to every order;
- show clear states: draft, queued offline, syncing, submitted, failed/conflict;
- sync automatically when connectivity returns;
- never display “submitted to factory” until server confirmation;
- do not silently duplicate orders after retries;
- detect stale price-list versions and send the original price snapshot to admin for review;
- make conflict resolution visible;
- allow a user to retry safely.

Security:
- avoid long-lived credentials in IndexedDB/localStorage;
- keep offline customer data minimal;
- provide logout/device data cleanup;
- document shared-device risks.

The salesman should place a simple order in under 60 seconds on a normal device. Test offline/online transitions, duplicate retries, stale prices, invalid customer assignment and sync failures using Playwright or equivalent.
```

**Acceptance gate:** A queued offline order syncs exactly once; UI never lies about server receipt; salesman cannot access unrelated customers.

## MP10 — Order inbox, verification, pricing and stock reservation

**Objective:** Connect field demand to available finished goods.

```text
Implement the admin order inbox.

Each order must show:
- salesman/customer;
- products and quantities;
- captured price and current price;
- customer-specific scheme/discount if configured;
- requested date;
- on-hand, reserved and available stock;
- quantity available now;
- shortage/backorder quantity;
- any stale-price or stock warning.

Admin actions:
- approve;
- reject with reason;
- amend quantity/price with an audit reason;
- partially approve/backorder according to the documented policy;
- reserve finished goods atomically when approved;
- release reservation on cancellation/rejection;
- preserve order status history.

Concurrency is critical: two admins must not approve orders against the same last packets. Use database locks or version checks and test parallel approvals.

Benchmark:
Retailer A order 150 must be approved against 238 packets, then invoiced/dispatched.
After dispatch, Distributor B order 120 must show only 88 available and shortage 32. Do not allow stock to go negative.

Show an understandable “Available to promise” number. Do not expose database terminology to users.
```

**Acceptance gate:** Reservation and concurrent approval cannot oversell; benchmark shortage equals exactly 32 packets.

## MP11 — GST invoice, credit note, dispatch and collection

**Objective:** Complete the sales loop from approved order to auditable outstanding balance.

```text
Implement invoice, tax calculation, PDF, dispatch and payment allocation.

Tax engine:
- supplier state and recipient place-of-supply state;
- intra-state versus inter-state calculation;
- configurable tax category/HSN and effective-dated rate;
- 5% benchmark assumption;
- CGST/SGST split for Tamil Nadu retailer;
- IGST for Karnataka distributor if/when invoiced;
- Decimal/paisa rounding policy documented;
- invoice number unique by organization and financial year;
- no invoice number race under concurrent requests.

PDF:
- professional, readable invoice;
- supplier/recipient demo data clearly fictional;
- invoice number/date;
- HSN field from configurable product master;
- description, quantity/UQC, rate, taxable value, tax rate/tax amount and totals;
- place-of-supply information;
- print-friendly layout.

The brief does not supply confirmed legal HSN or actual GSTINs. Use clearly marked fictional demo identities and an HSN placeholder requiring accountant verification. Do not assert legal compliance or live GST filing.

Posted invoice correction:
- never delete a posted invoice;
- use credit note/reversal with audit link.

Dispatch:
- dispatch only quantities permitted by approved/reserved stock policy;
- partial dispatch supported;
- create finished-goods inventory movement;
- preserve order→invoice→dispatch links.

Payment:
- record a payment;
- allocate to one or more invoices;
- show paid, partially paid and outstanding states;
- prevent over-allocation;
- support unallocated advance only if clearly modelled.

Benchmark:
Retailer A invoice ₹7,500 taxable + ₹187.50 CGST + ₹187.50 SGST = ₹7,875.
Dispatch 150 packets.
Record ₹4,000 payment.
Outstanding exactly ₹3,875.

Add end-to-end tests for tax direction, rounding, invoice numbering, credit note, partial dispatch, duplicate payment and allocation.
```

**Acceptance gate:** Invoice arithmetic and outstanding match; dispatch reduces finished stock exactly once; posted invoice is immutable.

## MP12 — Owner dashboard, reorder and production-readiness planner

**Objective:** Build actionable intelligence without dashboard noise.

```text
Implement the owner overview with a small number of decision-focused cards:
- today's orders and order value;
- orders awaiting approval;
- available finished goods and pending demand;
- low raw-material/packaging items;
- production runs and yield alerts;
- actual cost per packet and margin;
- receivables and overdue amounts;
- near-expiry lots where expiry data exists;
- latest stock adjustments and high-impact exceptions.

Build a reorder suggestion:
- current available stock;
- pending production demand from BOM;
- average consumption/lead-time where sufficient history exists;
- safety stock configured by item;
- suggested purchase quantity;
- supplier lead time and last recorded price.

Build a production-readiness planner:
- pending sales demand;
- available finished goods;
- net production requirement;
- batches needed based on BOM expected yield;
- raw material required for those batches;
- raw material available and projected shortage;
- packaging requirement;
- estimated run cost using last known/weighted-average rates.

All suggestions must expose their arithmetic and input records. Clearly label an estimate. The owner can approve/reject a suggestion; the system must not create a purchase order or production run without explicit confirmation.

Avoid false precision when there is not enough history. For the benchmark, show why 32 packets are unavailable and what raw materials would be needed to make another batch.
```

**Acceptance gate:** Dashboard figures reconcile to source records; suggested production/purchase quantities are explainable and do not automatically mutate stock.

## MP13 — Transport, visit and delivered-margin intelligence

**Objective:** Add transport as an economically useful stretch goal.

```text
Implement delivery trip planning and cost accounting as a separate module from salesman visit planning.

Start with synthetic coordinates and route data. Do not ask for or store real customer addresses in the demo.

Delivery route inputs:
- depot;
- dispatch-ready orders;
- customer stop coordinates;
- vehicle capacity;
- delivery windows;
- loading/unloading time;
- fixed trip charge;
- cost per kilometre or fuel assumptions;
- driver allowance, toll and parking.

Use a routing adapter:
- OSRM for route/distance/time matrix in prototype;
- OR-Tools for capacity/time-window vehicle routing if the input supports it;
- provide a deterministic mock adapter for tests/offline operation.

Show:
- planned stop sequence;
- planned kilometres/time;
- vehicle capacity use;
- cost estimate;
- actual trip cost entry;
- delivery completion/failed stop;
- cost per delivered packet/order;
- product contribution after allocated delivery cost.

Use a documented allocation rule (weight, volume, packet count or stop-level charge). Do not mix GST invoice value with operating delivery cost.

Salesman visits are distinct:
- optional one-time check-in;
- user-visible purpose;
- no continuous background tracking;
- opt-in location permission.

Add tests for no-coordinate fallback, capacity overflow, unserved stop and expense allocation. Include OpenStreetMap attribution wherever its data is displayed.
```

**Acceptance gate:** Route plan is clearly estimated; capacity limits respected; transport cost is transparent; no continuous employee tracking exists.

## MP14 — Audit reports, exports and evidence drill-down

**Objective:** Give the accountant an evidence-backed month-end package.

```text
Implement the reports required by NIT section 4.6:
1. sales register customer-wise and product-wise;
2. outward GST summary shaped for GSTR-1/GSTR-3B mapping;
3. purchase register;
4. stock summary;
5. stock ledger by raw, packaging and finished goods;
6. production report with planned/actual consumption, yield and wastage;
7. payment and collection report;
8. receivables ageing.

Requirements:
- filter by date range and customer/product/item;
- define date/timezone behaviour;
- totals reconcile to the underlying posted records;
- show opening, receipts, issues, returns/adjustments and closing where relevant;
- include the valuation method and assumptions;
- export CSV and XLSX;
- export selected reports to readable PDF;
- include generated timestamp, selected filters, organization and page numbers;
- preserve decimal precision and consistent rounding;
- auditor is read-only;
- every summary row drills into source invoices, receipts, runs or movement IDs.

Add report tests comparing totals with SQL/source-of-truth transactions. Never calculate report totals from decorative frontend mock data.
```

**Acceptance gate:** Report totals reconcile; every number can be traced to source documents; CSV/XLSX exports are usable and correctly typed.

## MP15 — Tamil/English localisation and accessibility polish

**Objective:** Make the production floor and field workflows easy to use.

```text
Implement localisation through structured translation dictionaries, not duplicate screens.

Requirements:
- English default;
- Tamil translation for core production and salesman flows;
- language switch persisted per user;
- preserve units, amounts, product codes and invoice numbers;
- do not translate legal/product master identifiers;
- use labels reviewed for clarity;
- avoid broken text rendering and layout overflow;
- keyboard, screen-reader and touch accessibility;
- large touch targets for production tablet;
- clear errors in the user's selected language where translations exist.

Do not machine-translate critical tax/legal text and present it as verified. Mark incomplete translations and fall back gracefully to English.

Test both languages at mobile/tablet/desktop sizes. The user must be able to complete a production run without needing to understand accounting jargon.
```

**Acceptance gate:** Core flows remain usable in both languages; no clipped labels or inaccessible controls.

## MP16 — Synthetic data generator, benchmark runner and complete testing

**Objective:** Prove correctness systematically, not through a single happy-path demo.

```text
Create a robust test and data-generation system.

A. Benchmark fixture:
- exact NIT section 5 input data;
- deterministic seed;
- no real company/customer data;
- versioned fixture;
- dedicated reset path;
- idempotent run command;
- assertions for every benchmark result.

B. Synthetic longitudinal generator:
- fixed random seed;
- 24 months;
- multiple fictional SKUs, customers, salesmen, suppliers and BOM versions;
- realistic but explicitly synthetic seasonality, price movement, lead times and production variation;
- orders, invoices, returns, dispatches, payments and stock movements;
- optional expiry lots and vehicle trips.

C. Test pyramid:
- unit tests for money, units, tax, BOM, weighted average and variance;
- property-based tests for stock conservation and ledger reconciliation;
- integration tests with real PostgreSQL;
- authorization tests for every role;
- concurrency tests for reservation, invoice numbering and stock posting;
- API tests for idempotency and retries;
- frontend component tests;
- Playwright end-to-end flows for salesman, admin, production and auditor;
- export file content tests;
- migration tests from clean database.

Critical properties:
- total stock movement effects reconcile;
- no duplicate transaction after retry;
- available stock never negative;
- payment allocation never exceeds payment amount;
- invoice line/tax totals reconcile;
- production run is atomic;
- cost snapshots do not drift after later purchases;
- an auditor cannot mutate;
- a salesman cannot see another salesman's assigned customers/orders.

Run the complete benchmark and print a clear expected/actual summary. A “PASS” label is allowed only when the relevant test truly ran and passed. List blocked tests separately with their actual reason.
```

**Acceptance gate:** Benchmark run passes from a clean seeded database; unit/integration/E2E results are recorded; no false pass claims.

## MP17 — Security, performance, reliability and deployment

**Objective:** Make the prototype safe and reproducible for panel evaluation.

```text
Perform application hardening and produce a deployment-ready local environment.

Security:
- validate all inputs server-side;
- enforce RBAC on APIs;
- prevent cross-organization data access;
- secure password/session handling;
- rate-limit login and sensitive endpoints;
- secure CORS and cookie settings;
- protect against SQL injection, XSS and CSRF where applicable;
- keep secrets in environment variables;
- include .env.example with dummy placeholders only;
- never log tokens/passwords;
- audit privileged mutations;
- use safe file upload rules if uploads exist.

Reliability:
- database transactions for posting;
- idempotency keys;
- structured logs with correlation IDs;
- meaningful API error envelopes;
- health/readiness checks;
- backup/restore documentation;
- reconciliation CLI;
- background jobs cannot duplicate exports or financial writes.

Performance:
- indexes for ledger/date/customer/product queries;
- pagination on large lists;
- avoid N+1 query patterns;
- test with synthetic scale;
- keep reports bounded and explain any long-running operation.

Deployment:
- Docker Compose for frontend/API/PostgreSQL;
- one documented local command;
- seeded role logins;
- migration command;
- benchmark command;
- health checks;
- no external integration required for the core demo.

Run dependency/security checks available in the repository. Document actual limitations of free hosting/database tiers. Do not claim production-grade disaster recovery if it has not been configured and tested.
```

**Acceptance gate:** Clean machine setup is documented and verified; secrets are absent; core flows run locally without external credentials.

## MP18 — Documentation, two-page design note and demo-video story

**Objective:** Package the work in the exact form expected by NIT.

```text
Prepare the NIT submission deliverables.

README must cover:
- project purpose and problem solved;
- stack and two/three-sentence justification;
- setup and one-command run;
- seed/demo accounts by role;
- features mapped to NIT must-have/should-have/stretch tiers;
- database/ledger explanation;
- benchmark numbers;
- costing method and overhead rule;
- tax assumptions;
- known gaps and unverified HSN/GST identity placeholders;
- test commands and actual results;
- limitations and future work.

Design note (maximum two pages):
- ER diagram or concise data model;
- stock movement and balance computation;
- BOM/production variance calculation;
- weighted-average costing;
- audit/reversal design.

Demo video script (maximum eight minutes):
0:00–0:30 problem and product framing;
0:30–1:20 salesman mobile order;
1:20–2:10 admin review and stock availability;
2:10–3:10 purchase and production run;
3:10–4:00 variance and cost per packet;
4:00–5:00 GST invoice and dispatch;
5:00–5:40 Distributor B shortage;
5:40–6:20 payment and outstanding;
6:20–7:20 reports and audit drill-down;
7:20–8:00 one differentiator: traceability or Loss-to-Profit.

The demo must run the exact NIT benchmark in order. Do not fake a successful transaction with prefilled screenshots. Show both mobile salesman and admin views. Keep the video focused on evidence and decision value.
```

**Acceptance gate:** README, design note and demo script match the actual implementation; known gaps are disclosed.

## MP19 — Independent judge-readiness and live-change rehearsal

**Objective:** Find the flaws before a judge does.

```text
Act as a strict NIT Trichy technical evaluator. Do not praise the project by default.

Independently inspect the implementation against the original problem statement and the acceptance criteria. Re-run the benchmark from a clean demo state.

Evaluate:
1. Can a salesman submit an order quickly on mobile?
2. Can the admin verify stock without overselling?
3. Are BOM quantities and units correct?
4. Does every production run update raw and finished stock atomically?
5. Can the panel trace every stock quantity to a source document?
6. Are actual and planned consumption/yield compared correctly?
7. Is cost per good packet mathematically justified?
8. Are GST state/tax calculations and invoice totals correct under the exercise assumptions?
9. Can a posted invoice be altered/deleted?
10. Are collections and ageing correct?
11. Can the auditor export reports and trace summary totals?
12. Does the system run with one documented command?
13. Are any screens showing fake data that is not connected to the database?
14. Is any feature claimed as implemented when it is only a placeholder?

Then rehearse the stated live interview change:
“Add a second pack size of 500 g sharing the same BOM.”

Implement this in a branch or isolated test fixture:
- configure a second SKU/pack size;
- reuse or derive recipe quantities through data/configuration;
- calculate expected materials and packaging;
- demonstrate tests;
- ensure old production runs and invoices remain unchanged.

Also simulate:
- duplicate offline order sync;
- two simultaneous approvals for the last available packets;
- a production posting failure halfway through;
- a stock-count adjustment;
- a credit note;
- an expired raw-material lot;
- a payment allocation error.

Produce docs/judge-readiness-report.md with:
- pass/fail/blocked per requirement;
- exact evidence/commands;
- defects ranked by severity;
- no unverifiable claims;
- the five most likely panel questions and technically honest answers.

Do not hide failed checks. Do not start adding new features until critical defects are fixed.
```

**Acceptance gate:** The exact scenario works, the 500 g change is data-driven, and all remaining limitations are transparent.

---

# PART J — DEVELOPMENT ORDER AND GIT CHECKPOINTS

## 21. Recommended implementation sequence

| Checkpoint | Prompts | What should be demonstrably working |
|---|---|---|
| CP0 — Understand | MP00 | Requirements, repository state and risks |
| CP1 — Experience | MP01–MP02 | Role workflows and approved data model |
| CP2 — Foundation | MP03–MP04 | Database, authentication, RBAC and audit |
| CP3 — Production core | MP05–MP08 | Ledger, purchase, BOM, production and cost |
| CP4 — Sales core | MP09–MP11 | Offline order, approval, invoice, dispatch, payment |
| CP5 — Decision value | MP12–MP15 | Owner intelligence, transport, reports and Tamil |
| CP6 — Proof | MP16 | Seeded benchmark and test suite |
| CP7 — Release | MP17–MP19 | Deployment, documentation and judge rehearsal |

After each checkpoint:
- inspect `git status`;
- review the diff;
- run the appropriate test commands;
- commit only coherent, verified work;
- keep a clean working tree where possible;
- do not use one enormous final commit.

Suggested commit prefixes:
- `docs:`
- `feat(auth):`
- `feat(inventory):`
- `feat(production):`
- `feat(sales):`
- `feat(billing):`
- `feat(reports):`
- `test:`
- `fix:`
- `chore:`

The developer must understand the implementation. Claude Code can implement quickly, but the student must be able to explain:
- why the ledger is the source of truth;
- why weighted-average costing was selected;
- why actual good output is the cost denominator;
- how unit conversions work;
- why invoices are reversed rather than deleted;
- how role access is enforced;
- how the benchmark can be rerun;
- how the application behaves when offline;
- what the forecast/route estimate does and does not claim.

---

# PART K — JUDGE PRESENTATION

## 22. How to make the panel stop and pay attention

Do not open with a long list of technologies. Open with a real business question:

> “A factory uses 40 kg of flour to produce a batch expected to yield 200 packets. It actually produces 188 good packets and uses 0.5 litres more oil than planned. Most small billing systems record the sale, but cannot explain this production loss. AaharOS connects the recipe, material issue, actual output, stock, cost and customer invoice in one traceable flow.”

Then prove it with the NIT scenario.

The most memorable demonstration is:
1. show the 200-packet expected yield;
2. record 188 actual good packets and 6 damaged pouches;
3. show the −6% yield and +5% oil variance;
4. show why the cost is ₹31.14 per good packet;
5. show the retailer order reducing finished stock from 238 to 88;
6. show the second customer order being blocked by a 32-packet shortage;
7. show the owner the loss evidence and the auditor the source movements.

Then show one differentiator:
- trace a finished batch back to its raw-material receipts and forward to its customer invoices; or
- show production readiness and the raw-material shortage required to meet pending demand.

This is more convincing than presenting a dozen disconnected AI features.

## 23. Likely judge questions

**Why did you choose weighted average?**  
It is a transparent perpetual valuation method suitable for the supplied opening stock and purchase scenario. The rate after the flour receipt is ₹43.125/kg. The method is documented and can be changed only through a controlled valuation policy, not by rewriting historical costs.

**Why is the unit cost divided by 188 rather than 200?**  
Because 188 is the actual saleable output. The run incurred ₹5,855 of material and direct run costs; dividing by 188 gives approximately ₹31.14 per good packet. Using expected yield would understate the actual cost of saleable units.

**Why is the stock balance not directly editable?**  
Because a balance without a source movement is not auditable. The system records the receipt, issue, output, dispatch, return or adjustment, then derives/reconciles the balance from those movements.

**What happens if two admins approve orders at the same time?**  
The approval/reservation operation is transactional and uses database locking/version checks. Only the available quantity can be reserved.

**What happens when the salesman has no network?**  
The PWA stores a local order draft with an idempotency key. It shows a queued state until the server confirms receipt. A retry cannot create a duplicate.

**Is the forecasting model trained on the benchmark?**  
No. The benchmark is a fixed acceptance fixture, not a training set. Optional forecasts use separately labelled synthetic history for demonstration and require real, adequate historical data before operational reliance.

**Does the app file GST returns?**  
No. It calculates the supplied exercise scenario and produces a report structure that maps to GST reporting concepts. Actual classification, HSN and filing require accountant verification and authorised government integrations.

**Is this a full ERP/accounting replacement?**  
The prototype is an integrated operational system for order, stock, production, costing and audit evidence. It is not presented as a complete statutory accounting package.

---

# PART L — REFERENCES AND IMPLEMENTATION NOTES

## 24. Useful authoritative references

1. **NIT Trichy source brief:** `Problem Statement - Winter Internship Application - 2026 .md` (user-supplied; authoritative for project scope and benchmark).
2. **CBIC GST invoice rules:** https://cbic-gst.gov.in/gst-invoice-rules.html  
   Use this to check invoice-field requirements. The implementation must still verify the current rules and the factory's actual tax classification before any real deployment.
3. **CBIC Rule 46:** https://taxinformation.cbic.gov.in/content-page/explore-rules/1000136/1000001  
   Reference for tax invoice particulars, including supplier details, financial-year-unique serial number, recipient details, HSN, description, quantity/UQC and value.
4. **India Open Government Data — daily mandi commodity prices:** https://data.gov.in/resource/variety-wise-daily-market-prices-data-commodity  
   Optional raw-material market context only; it is not a substitute for supplier invoices or the factory's actual stock valuation.
5. **Google OR-Tools vehicle routing:** https://developers.google.com/optimization/routing  
   Reference for route sequencing and vehicle-routing problems.
6. **OR-Tools capacity constraints:** https://developers.google.com/optimization/routing/cvrp  
   Reference for capacity-constrained delivery planning.
7. **OSRM documentation:** https://project-osrm.org/docs/  
   Reference for route, trip and distance/time matrix services.
8. **OpenStreetMap copyright/licence:** https://www.openstreetmap.org/copyright  
   If OSM data is displayed or distributed, provide the required contributor attribution and comply with ODbL terms.
9. **Supabase pricing (if selected for managed database/auth):** https://supabase.com/pricing  
   Check current plan limits, project pausing, backups and usage before deployment.
10. **Render pricing (if selected for hosting):** https://render.com/pricing  
    Check current compute, database, storage and bandwidth costs before deployment.

## 25. Final non-negotiable checklist

- [ ] Exact NIT benchmark data is unchanged.
- [ ] Seed command works from a clean demo database.
- [ ] Flour closes at 120 kg.
- [ ] Oil closes at 19.5 L.
- [ ] Spice mix closes at 3.8 kg.
- [ ] Pouches close at 306.
- [ ] Cartons close at 21.
- [ ] Finished stock after production is 238.
- [ ] Finished stock after Retailer A dispatch is 88.
- [ ] Yield variance is −6% and flagged.
- [ ] Oil variance is +5% and flagged.
- [ ] Retailer A invoice is ₹7,875.
- [ ] Retailer A outstanding is ₹3,875.
- [ ] Distributor B shortage is 32 packets.
- [ ] Cost per good packet is approximately ₹31.14 using the documented assumptions.
- [ ] Inventory balances reconcile to source movements.
- [ ] Posted invoices cannot be silently edited/deleted.
- [ ] All roles are enforced by the backend.
- [ ] Offline order retries cannot duplicate an order.
- [ ] Reports export real database data.
- [ ] All claims in README/demo are proven by a command or visible workflow.
- [ ] Local one-command run and test logins are documented.
- [ ] The student can explain the calculations and make the 500 g pack-size change live.

**The winning strategy is not “the most features.” It is “the most trustworthy factory decision system that still feels effortless to use.”**
