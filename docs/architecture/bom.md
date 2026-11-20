# Recipes and pack specs: a two-level, driver-based BOM

The brief's BOM mixes two different things: what goes into **making murukku** (flour, oil, spice: per batch) and what
goes into **packing it** (pouches, cartons: per packet made). AaharOS keeps them apart, so a second pack size is data,
not code.

```
RECIPE  "Murukku dough and fry"  v1     → makes BULK murukku: 40,000 g per batch
  flour 40 kg · oil 10 L · spice mix 1.2 kg          driver PER_BATCH

PACK SPEC "Murukku 200 g"  v1           → packs 200 g of bulk per good packet, 20 packets per carton
  pouch_200g 1 · carton_20 0.05 (= 1/20)             driver PER_GOOD_UNIT

PACK SPEC "Murukku 500 g"  v1           → packs 500 g of bulk per good packet (seed data, not in the benchmark)
  pouch_500g 1 · carton_500 1/N (N from the pack spec) driver PER_GOOD_UNIT
```

## 1. Drivers

| Driver | Standard quantity for a run | Used for |
|---|---|---|
| `PER_BATCH` | `qty × batch_multiplier` | ingredients (recipe lines) |
| `PER_GOOD_UNIT` | `qty_per_good_unit × actual good units` (flexible standard) | packaging (pack spec lines) |

Packaging is compared with the standard **for what was actually made**, ingredients with the standard **for the batch
that was started**. That is a flexible budget, and it is what exposes the damaged pouches:

| View | Pouch standard | Actual 194 | Variance | Flag at 3% |
|---|---:|---:|---:|---|
| Batch (old way) | 200 | 194 | −3.00% | not flagged, looks favourable |
| Flexible (AaharOS) | 188 | 194 | **+3.19%** | **flagged** |

Both views are shown; the flexible one drives the alert (assertion 20).

## 2. Formulas

```
expected_bulk_g           = recipe.bulk_yield_g × batch_multiplier                    40,000 × 1 = 40,000 g
expected_units(pack line) = bulk_allocated_g / pack.net_g                             40,000 / 200 = 200
Σ bulk_allocated_g        = expected_bulk_g   (else the run shows "unallocated bulk")
std_qty(PER_BATCH line)   = line.qty × batch_multiplier
std_qty(PER_GOOD_UNIT)    = line.qty_per_good_unit × good_units                       carton: 0.05 × 188 = 9.4
usage variance %          = (actual − std) / std × 100                                oil: (10.5 − 10) / 10 = +5.00%
yield variance %          = (good − expected) / expected × 100                        (188 − 200) / 200 = −6.00%
flag                      = |variance| > tolerance (line override, else org setting, effective-dated; default 3%)
packing                   = divmod(good_units, units_per_carton)                      188 → 9 cartons + 8 loose
mass balance              = expected_bulk = Σ good × net + scrap_g + loss_g + unexplained   40.0 = 37.6 + 0 + 0 + 2.4 kg
```

Benchmark result table:

| Line | Driver | Standard | Actual | Variance | Flag |
|---|---|---:|---:|---:|---|
| Yield (good packets) | – | 200 | 188 | −6.00% | **flagged** |
| Flour | PER_BATCH | 40 kg | 40 kg | 0.00% | – |
| Cooking oil | PER_BATCH | 10 L | 10.5 L | +5.00% | **flagged** |
| Spice mix | PER_BATCH | 1.2 kg | 1.2 kg | 0.00% | – |
| Pouch 200 g | PER_GOOD_UNIT | 188 | 194 | +3.19% | **flagged** |
| Carton 20 | PER_GOOD_UNIT | 9.4 | 9 | −4.26% | favourable, info: 8 loose packets |

## 3. Worked examples

**200 g (the benchmark):** 1 batch → 40,000 g bulk → one pack line, 40,000 g allocated → 200 expected packets.
Standard packaging for 188 good: 188 pouches, 9.4 cartons.

**500 g:** 1 batch → 40,000 g bulk → one pack line "Murukku 500 g", 40,000 g allocated → 40,000 / 500 = **80** expected
packets. Ingredients identical (same recipe). Packaging standard for, say, 78 good: 78 pouch_500g.

**Mixed split:** 1 batch → two pack lines on the same run:

| Pack line | Bulk allocated | Expected | Example good | Lot |
|---|---:|---:|---:|---|
| Murukku 200 g | 20,000 g | 100 | 97 | B-002-A |
| Murukku 500 g | 20,000 g | 40 | 39 | B-002-B |

Ingredient variances are computed once for the run; yield and packaging variances per pack line. Material cost is
split between lots by bulk allocated (good units × net weight is shown alongside), documented in ADR-0003.

## 4. The interview change: "add a 500 g pack sharing the same BOM" — zero code

Rows to add (all through the admin screens or a seed file):

1. `items`: `murukku_500g` (FG, packet), `pouch_500g` (PACK), a carton item for 500 g packs if it differs.
2. `pack_specs` + `pack_spec_versions`: recipe = "Murukku dough and fry", net_g = 500, units_per_carton = N,
   shelf_life_days.
3. `pack_spec_lines`: pouch_500g 1 per good unit, carton 1/N per good unit (PER_GOOD_UNIT).
4. `uom_conversions`: carton = N packets, scoped to this pack spec version.
5. `price_list_items`: price for murukku_500g. `tax_rules` already cover the HSN.
6. Optional: `standard_cost_cards` row for 500 g (computed from the same rates).

Nothing in `production.domain` mentions 200, 20 or "murukku": every number comes from the snapshot of the recipe and
pack spec frozen on the run. Old runs keep their snapshots, so they are unchanged (rehearsed in MP19).

## 5. Versioning
- Recipes and pack specs have versions with status DRAFT → ACTIVE → RETIRED. A version used by any run is immutable.
- A run stores `recipe_snapshot` and `pack_snapshot` (JSONB copies, plus version ids) when it starts.
- Standard cost cards are versioned per pack spec version and effective-dated.
