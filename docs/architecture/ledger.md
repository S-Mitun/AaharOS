# The stock ledger: double entry for kilograms and rupees

Every stock event is a **journal** with **lines**. A line is `(item, location, lot, qty_base, value)`.
For each journal: Σ qty = 0 **per item**, and Σ value = 0 **across all lines**. A balance is the sum of lines;
`inventory_balances` is only a projection that can be rebuilt at any time. This is why
*opening + receipts − issues ± adjustments = closing* holds by construction, the way a trial balance always balances.

Every number in the tables below was replayed with Python `Decimal` against the oracle before this page was written
(all journals balance, no store goes negative, and B-001 ends at ₹3,114.36 dispatched + ₹2,740.64 on hand = ₹5,855.00).

## 1. Locations

| Code | Kind | Meaning | May go negative? |
|---|---|---|---|
| `RAW_STORE` | STORE | Raw-material store (flour, oil, spice) | No |
| `PACK_STORE` | STORE | Packaging store (pouches, cartons, labels) | No |
| `WIP` | STORE | Production floor: issued to a batch, not yet consumed. Label: "Production floor" | No |
| `FG_STORE` | STORE | Finished goods, by lot | No |
| `IN_TRANSIT` | STORE | Dispatched, not yet delivered (reserved; not used in the benchmark) | No |
| `OPENING` | VIRTUAL | Source of opening balances | Yes |
| `SUPPLIER` | VIRTUAL | Source of purchases | Yes |
| `PRODUCTION` | VIRTUAL | Conversion: inputs are consumed here, finished goods come out of here | Yes |
| `CONVERSION_COST` | VIRTUAL | Source of labour, gas/power and other run costs absorbed into a lot (value only) | Yes |
| `SCRAP` | VIRTUAL | Damaged packaging, process waste, expired write-offs | Yes |
| `CUSTOMER` | VIRTUAL | Sold and dispatched. Its value is cost of goods sold | Yes |
| `ADJUSTMENT` | VIRTUAL | Count differences (reason and approver required) | Yes |

**Change from MASTER_PACK B.2:** B.2 uses one `PRODUCTION (WIP)` location. NIT's steps 2 (issue) and 3 (output) are
separate events, and the brief checks the flour balance (120 kg) right after the issue. So issuing moves stock to a
real `WIP` location at step 2, and the completion journal at step 3 consumes it into the virtual `PRODUCTION`
location. That also gives the brief's optional work-in-progress balance for free. (ADR-0002)

## 2. Journal kinds

| Kind | Source document | Typical lines |
|---|---|---|
| OPENING | opening balance sheet | OPENING → store |
| RECEIPT | purchase receipt | SUPPLIER → RAW/PACK_STORE |
| ISSUE / RETURN | material issue for a run | RAW_STORE ⇄ WIP |
| RUN_COMPLETION | production run | WIP → PRODUCTION, PACK_STORE → PRODUCTION / SCRAP, PRODUCTION → FG_STORE |
| COST_TRUE_UP | run costs entered after output | CONVERSION_COST → FG_STORE / CUSTOMER (value only) |
| DISPATCH | dispatch note | FG_STORE → CUSTOMER |
| SALES_RETURN | return note | CUSTOMER → FG_STORE or SCRAP |
| ADJUSTMENT | stock count | store ⇄ ADJUSTMENT |
| REVERSAL | any of the above | exact mirror of the reversed journal |

## 3. The NIT benchmark, journal by journal

Quantities in stock units (stored in base units: g, mL, piece). Values in ₹. "→" columns: negative line first, positive second.

### J0 Opening balances (source: opening sheet, assumption A1 for the FG lot)

| Item | Lot | OPENING | Store | Qty | Value |
|---|---|---|---|---:|---:|
| Flour | – | −100 kg | RAW_STORE +100 kg | 100 kg | 4,200.00 |
| Cooking oil | – | −30 L | RAW_STORE +30 L | 30 L | 4,200.00 |
| Spice mix | – | −5 kg | RAW_STORE +5 kg | 5 kg | 1,000.00 |
| Pouch 200 g | – | −500 | PACK_STORE +500 | 500 | 1,250.00 |
| Carton 20 | – | −30 | PACK_STORE +30 | 30 | 450.00 |
| Murukku 200 g | OPEN-LOT | −50 | FG_STORE +50 | 50 | 1,442.50 (50 × standard 28.85) |

### J1 Step 1: purchase 60 kg flour at ₹45 (source: purchase receipt)

| Line | Item | Location | Qty | Value |
|---|---|---|---:|---:|
| 1 | Flour | SUPPLIER | −60 kg | −2,700.00 |
| 2 | Flour | RAW_STORE | +60 kg | +2,700.00 |

WAC pool after: 160 kg, ₹6,900.00 → **₹43.125/kg** (assertion 16).

### J2 Step 2: issue to batch B-001 (source: material issue MI-1 → run B-001)

Raw-material lines carry **no lot**: a lot belongs to one item (MP02 enforces it with a (lot, item, org) FK),
and B-001 is a murukku lot. Which run a WIP balance belongs to comes from the journal's source (the material
issue names the run).

| Item | RAW_STORE | WIP | Value at WAC |
|---|---:|---:|---:|
| Flour | −40 kg | +40 kg | 1,725.00 (40/160 × 6,900) |
| Cooking oil | −10.5 L | +10.5 L | 1,470.00 (10.5/30 × 4,200) |
| Spice mix | −1.2 kg | +1.2 kg | 240.00 (1.2/5 × 1,000) |

Balances: **flour 120 kg** (₹5,175.00), **oil 19.5 L** (₹2,730.00), spice 3.8 kg (₹760.00) — assertions 1, 2, 15.

### J3 Step 3: run completion, 188 good, 6 damaged pouches, 9 cartons (source: run B-001)

| # | Item | Location | Lot | Qty | Value |
|---|---|---|---|---:|---:|
| 1 | Flour | WIP | – | −40 kg | −1,725.00 |
| 2 | Flour | PRODUCTION | – | +40 kg | +1,725.00 |
| 3–4 | Cooking oil | WIP → PRODUCTION | – | ∓10.5 L | ∓1,470.00 |
| 5–6 | Spice mix | WIP → PRODUCTION | – | ∓1.2 kg | ∓240.00 |
| 7 | Pouch 200 g | PACK_STORE | – | −194 | −485.00 |
| 8 | Pouch 200 g | PRODUCTION | – | +188 | +485.00 |
| 9 | Pouch 200 g | SCRAP | – | +6 | 0.00 (`SCRAP_IN`) |
| 10 | Carton 20 | PACK_STORE | – | −9 | −135.00 |
| 11 | Carton 20 | PRODUCTION | – | +9 | +135.00 |
| 12 | Murukku 200 g | PRODUCTION | B-001 | −188 | −4,055.00 |
| 13 | Murukku 200 g | FG_STORE | B-001 | +188 | +4,055.00 |

- Per item: flour −40+40, pouch −194+188+6, murukku −188+188 … all zero. Σ value = 0.
- **The 6 damaged pouches carry quantity to SCRAP but no value.** Their ₹15 stays in the batch cost (a normal loss
  absorbed by good output), which is why cost per packet uses 194 pouches. The variance engine still shows it
  (pouch damage ₹15, pouch flexible variance +3.19%). A reason code can later mark a loss as abnormal so it is
  written off instead (open question Q3).
- WIP for B-001 returns to zero (invariant S6). Lot B-001 is created with mfg date and best-before from the pack spec.
- Balances: **pouches 306**, cartons 21, **FG 238** (assertions 3, 4, 15). B-001 cost is **PROVISIONAL**: ₹4,055.00 materials only.

### Step 4: Salesman A orders 150 for Retailer A
No stock lines. A sales order is not a stock movement.

### Step 5: approve, invoice, dispatch
- **Approve:** reservation of 150 packets on Murukku 200 g at FG_STORE (a `reservations` row, not a journal).
  Available to promise: 238 on hand − 150 reserved = 88.
- **Invoice** `AHR/26-27/000001`: taxable 7,500.00, CGST 2.5% 187.50, SGST 2.5% 187.50, total 7,875.00. No stock lines.
- **J5 dispatch (FEFO, A3):**

| Item | Lot | FG_STORE | CUSTOMER | Value |
|---|---|---:|---:|---:|
| Murukku 200 g | OPEN-LOT | −50 | +50 | 1,442.50 |
| Murukku 200 g | B-001 | −100 | +100 | 2,156.91 (100/188 × 4,055.00, provisional) |

Reservation consumed. **FG 88** (assertion 5). FEFO 50 + 100 (assertion 21).

### Step 6: Distributor B orders 120 (Karnataka)
No stock lines. Availability check: on hand 88, reserved 0, available 88 → **shortage 32**, flagged.
The order stays SUBMITTED (not approved, not invoiced, no reservation), so stock can never go negative
(assertion 13). If it were invoiced, place of supply Karnataka ≠ Tamil Nadu → IGST (assertion 14).

### Step 7: payment ₹4,000 from Retailer A
No stock lines. Payment allocated to the invoice → outstanding 7,875.00 − 4,000.00 = **3,875.00** (assertion 12).

### J8 Step 8: labour ₹1,200 + gas/power ₹600 for B-001 (source: run costs RC-1)
NIT records these **after** 100 packets of B-001 have already left. The lot's value must still end up equal to the
full run cost, split between what was sold and what is on hand. A value-only true-up journal does that:

| Line | Item | Location | Lot | Qty | Value |
|---|---|---|---|---:|---:|
| 1 | Murukku 200 g | CONVERSION_COST | B-001 | 0 | −1,800.00 |
| 2 | Murukku 200 g | CUSTOMER | B-001 | 0 | +957.45 |
| 3 | Murukku 200 g | FG_STORE | B-001 | 0 | +842.55 |

- Target sold value = round(100 × 5,855.00 / 188) = **3,114.36**; already posted 2,156.91 → line 2 = 957.45.
- Line 3 is the remainder (1,800.00 − 957.45): the units still on hand absorb rounding, so nothing is lost.
- After: B-001 on hand 88 packets = **2,740.64**, sold 100 = **3,114.36**, total **5,855.00** (assertion 22).
  Cost status becomes **FINAL**; cost per good packet ₹31.143617 → shown as **₹31.14** (assertions 17, 18).
- COGS for invoice A = 1,442.50 + 3,114.36 = **4,556.86**; gross margin 2,943.14 (39.24%).
- If run costs are entered *before* completion, no true-up is needed: the completion journal's output line simply
  carries materials + conversion costs, with a `CONVERSION_COST` line for the costs.

### Step 9: reports
No stock lines. Reports read journals, lines, invoices and payments; nothing is re-typed.

**Proven in MP02:** `backend/tests/db/test_ledger_guards.py::test_nit_journals_balance_and_project` posts
J0, J1, J2, J3, J5 and J8 exactly as above against PostgreSQL. Every journal passes the deferred balance trigger
and the projection shows flour 120 kg / ₹5,175.00, oil 19.5 L / ₹2,730.00, pouches 306, FG 88 / ₹2,740.64,
CUSTOMER ₹4,556.86, WIP 0, and B-001 = ₹5,855.00.

## 4. Value rules

1. **Raw and packaging items** are valued from a weighted-average pool per item (`item_cost_state`: pooled qty and
   pooled value over the stores). Receipt: add qty and value. Issue: value = round_half_up(qty / pool_qty × pool_value)
   to paise; when the pool empties, the last issue takes exactly the remaining value. No per-gram unit cost is ever
   rounded and multiplied back, so the pool cannot drift. (ADR-0004)
2. **Finished goods** are valued per lot at actual cost: the lot holds (qty, value); a dispatch takes
   round(qty / lot_qty × lot_value); the last unit out takes the rest. (ADR-0005)
3. **Conversion costs** (labour, gas/power, other direct run costs) enter a lot through `CONVERSION_COST`, at
   completion or via a true-up. Monthly overheads (rent, salaries) are allocated in reports as "absorbed" cost by
   machine-hours (fallback: kg of bulk) and **do not** change lot values in v1. (MP07)
4. **Scrap and damage** carry quantity, not value: the cost stays in good output and appears in variances.
5. **Variance accounts:** books are kept at actual cost, so variances are not ledger lines. They are explicit
   `variance_results` rows (yield, usage, price, damage) whose ₹ impacts sum exactly to actual − standard
   (₹5,855.00 − ₹5,423.80 = ₹431.20). A `VARIANCE` location is reserved for a future standard-costing mode.
6. **Rounding:** money is rounded once, at posting, ROUND_HALF_UP to paise. Quantities are never rounded.
   Every split assigns the remainder to the last line, so totals are exact.
7. **Reversals** mirror the original journal line for line (same values), so history is never revalued.

## 5. Reservations and available to promise
- `reservations` hold FG for approved order lines (item level at FG_STORE; the lot is chosen at dispatch by FEFO).
- Available to promise = on hand (FG_STORE, non-expired lots) − active reservations. Approval locks the item's
  balance row `FOR UPDATE`, checks availability, then inserts the reservation in the same transaction.
- Dispatch consumes the reservation; cancel or reject releases it.

## 6. Checks run by `make integrity` (MP04, MP11)
1. Every journal: Σ qty per item = 0 and Σ value = 0.
2. Rebuild `inventory_balances` from lines and diff with the projection: zero differences.
3. No STORE balance negative; WIP of every completed run is zero.
4. Per run: lot value (on hand + sold) = materials consumed + conversion costs.
5. Tax tie-out: invoice tax lines = GST summary = export.
6. Audit hash chain verifies for every organization.
