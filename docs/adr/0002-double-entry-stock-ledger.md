# ADR-0002: Double-entry stock ledger with a real WIP location

- Status: Accepted (MP01, approved 2026-11-21)

## Context
The brief: stock balances must be derived from a ledger of movements, every movement traces to its source, and
posted records are never edited. NIT's benchmark issues material (step 2) and records output (step 3) as separate
steps, and checks the flour balance right after the issue.

## Decision
- Every stock event is a journal of lines `(item, location, lot, qty_base, value)` with Σ qty = 0 per item and
  Σ value = 0 per journal, enforced by a deferred PostgreSQL constraint trigger (MP02) and by `ledger.domain`.
- Locations are STORE (never negative) or VIRTUAL (counterparties); see `docs/architecture/ledger.md`.
- **Split of MASTER_PACK B.2's `PRODUCTION (WIP)`**: an issue moves stock RAW_STORE → `WIP` (a real store, shown as
  "Production floor"); run completion moves WIP → `PRODUCTION` (virtual conversion) and creates FG out of `PRODUCTION`.
- **Scrap lines carry quantity, not value** (a normal loss absorbed by good output); the loss shows in variances.
- **Value-only lines** (qty 0) are allowed only for cost true-ups of a finished-goods lot.
- `inventory_balances` is a projection updated in the same transaction and rebuildable by `make integrity`.
- Corrections are reversal journals that mirror the original. Nothing posted is updated or deleted.

## Consequences
- Conservation law 1 is enforced by the database itself. Balances can always be recomputed and compared.
- WIP is visible between issue and completion, matching the floor and NIT's step order.
- Virtual-location balances double as audit totals (CUSTOMER value = cost of goods sold).
- Rejected: a single signed-movement table with no counterparty (cannot prove conservation); overwriting balances
  (forbidden by the brief).
