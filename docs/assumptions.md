# Assumptions

The brief says: *"Where something is unclear, make a reasonable assumption and write it down."* These are ours.
Everything marked **DEMO** is fictional and must be replaced and verified (by a CA where noted) before real use.

## Benchmark assumptions (from `benchmark/expected_results.yaml`)

| Id | Assumption | Why |
|---|---|---|
| A1 | The opening 50 finished packets have no cost in the brief; they are valued at the standard cost ₹28.85/packet. | Needed for COGS and margin on the Retailer A dispatch. |
| A2 | The standard cost card uses opening purchase rates and BOM quantities at full yield. | Gives a stable standard to measure variances against. |
| A3 | Finished goods are lot-tracked; dispatch picks first-expiry-first-out (opening lot first). | Food products; FEFO is a stretch goal in the brief. |
| A4 | Labour ₹1,200 and gas/power ₹600 are direct costs of this run, assigned 100% to it. | The brief gives them "for the run". |
| A5 | A carton is both a consumed packaging item and a packing unit (1 carton = 20 packets). | The brief lists cartons in the BOM and says a carton holds 20 packets. |
| A6 | Retailer A and Distributor B are GST-registered (DEMO GSTINs), so their invoices are B2B (GSTR-1 Table 4A). | The brief gives no registration status. |

## Gaps in the brief, and what we assume

| Id | Gap | Assumption |
|---|---|---|
| G1 | Factory GSTIN, legal name, address | **DEMO**: "AaharOS Demo Snacks", a Tamil Nadu GSTIN-shaped DEMO value (state code 33). |
| G2 | Customer GSTINs and addresses | **DEMO** values with the right state codes (Tamil Nadu 33, Karnataka 29). |
| G3 | HSN code for murukku | Config field, default 2106 90 (commonly used for namkeen), marked **verify with CA**. |
| G4 | GST rate and its date | 5% per the brief; stored as an effective-dated rule. 5% also matches the post-22-Sep-2025 rate for pre-packaged namkeen (earlier 12%); verify with CA. |
| G5 | Financial year and invoice series | FY starts 1 April. Series `AHR/26-27/000001`, gapless per FY, ≤ 16 characters (Rule 46). |
| G6 | FSSAI licence number, Udyam number | **DEMO** 14-digit FSSAI and Udyam values, printed on invoices, from config. |
| G7 | Murukku shelf life | 90 days (config on the pack spec), used for best-before and FEFO. |
| G8 | Opening finished-goods lot dates | One opening lot "OPEN-LOT", manufactured before the benchmark run, earlier best-before than batch B-001. |
| G9 | Bulk yield of the recipe | One batch yields 40.0 kg of bulk murukku = 200 expected packets × 200 g net: the seed derives it from the BOM's expected output and the pack's net weight (MP06). |
| G10 | Dates of the benchmark steps | All nine steps happen in one month in FY 2026-27 so one month's reports contain them. |
| G11 | Timezone | Stored in UTC, shown and reported in Asia/Kolkata. |
| G12 | Factory state / place of supply | Factory in Tamil Nadu (brief). Place of supply = customer's state. |
| G13 | Rounding | Tax per line, ROUND_HALF_UP to paise; unit costs stored to 6 dp; the last unit of a lot absorbs rounding so lot value = run cost. |
| G14 | Tolerance | 3% (brief), effective-dated, overridable per BOM line. |
| G15 | Inter-state e-way bill threshold | ₹50,000 consignment value (config). Distributor B's ₹6,300 is below it. |
| G17 | 500 g pack (seed data only) | **DEMO**: `murukku_500g` in `pouch_500g`, 10 packets per outer carton (the same `carton_20` box), 90 days shelf life. Not part of the benchmark run. |
| G18 | Pouches used in the NIT run | Pouches taken from the store = good packets + damaged pouches (188 + 6 = 194); the damaged go to SCRAP at no value. |
| G19 | Standard rates and the conversion standard | The 200 g standard cost card uses the opening rates (A2) and this run's labour 1,200 + gas 600 as the conversion standard per batch: 28.85 per packet. No 500 g card (no input rate for `pouch_500g`). |
| G20 | Overheads | Monthly overheads are not absorbed into lots in v1 (MP11 reports them); costing shows direct cost. |
| G16 | Payment terms | 45 days (MSME written-agreement maximum) unless a customer has shorter terms; verify with CA. |

## Not assumed
- No real company, person, GSTIN or licence number is used anywhere.
- No live GST, IRP or e-way bill calls: these are mock adapters, labelled as such.
