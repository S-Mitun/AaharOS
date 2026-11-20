# ADR-0005: Lot-tracked finished goods, dispatched first-expiry-first-out

- Status: Accepted (MP01, approved 2026-11-21)

## Context
Food needs batch and expiry tracking (a "strong plus" in the brief). The opening 50 packets have no cost in the brief.

## Decision
- Every finished unit belongs to a lot: production lots (B-001, …) with mfg date and best-before from the pack
  spec's shelf life, and one opening lot `OPEN-LOT` valued at standard ₹28.85 (assumption A1).
- Lots carry their own (qty, value): actual cost per lot, not a pooled average across lots.
- Approval reserves at item level; dispatch picks lots by earliest best-before (then earliest mfg date) and skips
  expired lots. The admin may override the pick with a reason (audited).
- Dispatch value per lot = round(qty / lot_qty × lot_value); the last unit takes the rest.

## Consequences
- Benchmark: Retailer A receives 50 from OPEN-LOT + 100 from B-001; 88 of B-001 remain.
- Trace this packet and the recall simulator (MP13) work from dispatch lines.
- Rejected: FIFO by receipt time (ignores shelf life); one average across all FG (hides each batch's real cost).
