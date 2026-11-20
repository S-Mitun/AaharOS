# ADR-0008: Money as NUMERIC(14,2) rupees; quantities and unit costs as NUMERIC(18,6)

- Status: Accepted (MP02, 2026-11-21; open question Q1 approved as recommended)

## Context
MP02 asks for one choice: money as BIGINT paise or NUMERIC(14,2). CLAUDE.md requires Python `Decimal` with
PostgreSQL `NUMERIC`, rounding only at posting (ROUND_HALF_UP to paise) and unit costs to 6 dp. Exports, the
auditor's SQL and the live interview all read amounts directly.

## Decision
- **Money: `NUMERIC(14,2)` in rupees** (`app.core.db.Money`). Up to ₹999,999,999,999.99, far above a small factory.
- **Quantities: `NUMERIC(18,6)`** in the item's base unit: g, mL or piece (`Qty`).
- **Unit costs and rates: `NUMERIC(18,6)`** (`UnitCost`), e.g. ₹31.143617 per packet, ₹43.125 per kg.
- **Percentages: `NUMERIC(9,4)`** (`Pct`), e.g. GST 5.0000, yield variance −6.0000.
- Every column is mapped with `asdecimal=True`, so values reach Python as `Decimal`. `app.core.money` rejects floats.
- Rounding stays in Python (`round_money`, ROUND_HALF_UP) and happens once, at posting. The database never rounds:
  a value with more than 2 dp is rejected by the column scale only after Python has already rounded it.

## Consequences
- Amounts read the same in SQL, the API, CSV exports and the GSTR-shaped export, with no ×100 conversions to explain.
- Exactness equals BIGINT paise: NUMERIC is exact decimal arithmetic, not binary floating point.
- The balance trigger compares `sum(value) <> 0` exactly; there is no tolerance to tune.
- Rejected: BIGINT paise (exact too, but every report, export and live SQL query needs a conversion, and unit costs
  at 6 dp would still need NUMERIC, giving two money representations).
