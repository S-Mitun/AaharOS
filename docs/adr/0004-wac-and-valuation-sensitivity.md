# ADR-0004: Weighted-average cost in the books; FIFO and last price as sensitivity

- Status: Accepted (MP01, approved 2026-11-21)

## Context
The brief says: pick a method (last price, weighted average or FIFO) and justify it. Money must not drift.
NIT records labour and gas for the run after part of its output has already been sold.

## Decision
- **Book method: perpetual moving weighted average** per raw/packaging item. The state is the pooled (qty, value)
  over the stores (`item_cost_state`), never a rounded unit cost. Issue value = round_half_up(qty / pool_qty ×
  pool_value) to paise; the last unit out takes the remaining value. The displayed unit cost (per kg, per L) is
  derived and shown to 6 dp. Benchmark: (100 × 42 + 60 × 45) / 160 = ₹43.125/kg; an issue of 40 kg = ₹1,725.00.
- **Landed cost:** purchase value = qty × rate. Freight and other charges are recorded separately on the receipt
  and **excluded** from inventory value in v1 (shown in the purchase register). GST paid on purchases is input
  credit, never stock value.
- **Sensitivity:** FIFO layers (`valuation_layers`) and last price are computed for the comparison panel only and
  never post. Benchmark: WAC ₹31.14, FIFO ₹30.90, last price ₹31.54 per packet.
- **Run cost** = materials at issue value + direct conversion costs (labour, gas/power). Cost per good packet =
  run cost ÷ good packets (188, not 200). Monthly overheads are allocated in reports (machine-hours, fallback kg of
  bulk) and do not change lot values in v1.
- **Late conversion costs:** if run costs arrive after output, a value-only `COST_TRUE_UP` journal spreads them over
  the lot by quantity: sold units to CUSTOMER (COGS), units on hand to FG_STORE (on hand absorbs rounding).
  The run's cost status moves PROVISIONAL → FINAL.
- Changing the book method is a governed, effective-dated configuration change for future periods with its own ADR.
  History is never revalued.

## Consequences
- The benchmark reproduces exactly: ₹5,855.00 = ₹3,114.36 sold + ₹2,740.64 on hand.
- Reports show cost status; a provisional cost per packet is labelled as provisional.
- Rejected: FIFO as the book method (more layers to explain, no benefit for fungible flour); last price
  (swings with a single invoice and is not a recognised inventory valuation method).
