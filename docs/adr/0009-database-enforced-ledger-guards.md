# ADR-0009: The database enforces the ledger: trigger-maintained balances, guards, and a non-owner app role

- Status: Accepted (MP02, 2026-11-21; approved with the MP02 plan)

## Context
Invariants S1 (stores never negative), S3 (no endpoint writes a balance), D1 (posted records immutable) and P2
(organization isolation) were assigned to "DB" in MP01. Doing them only in service code means one buggy endpoint,
script or seed can break them. MP01 planned for the ledger service (MP04) to update `inventory_balances`.

## Decision
- **Balances are maintained by a trigger.** `aahar_project_balance()` (SECURITY DEFINER, owned by the migration
  role) runs AFTER INSERT on every `stock_lines` row. The application role has `SELECT` only on
  `inventory_balances`. This moves the projection from MP04 into the schema; MP04 still builds and tests the
  journal-posting service and the rebuild check.
- **It is two statements, not one upsert.** PostgreSQL evaluates CHECK constraints on the proposed `INSERT` row
  before it resolves `ON CONFLICT`. Upserting the signed delta would reject every outgoing line (−40 kg looks
  negative). The trigger inserts a zero row if none exists (`ON CONFLICT DO NOTHING`), then `UPDATE`s by the delta
  under the row lock. The `store_not_negative` CHECK then judges the real new balance. This was found by the NIT
  replay test.
- **Store-negative check is immediate, per line.** Within one journal, lines that add to a store must be inserted
  before lines that take from it. The ledger service (MP04) inserts positive lines first.
- **Guards, all in migration 0003, with their own SQLSTATE codes:**
  | Code | Guard |
  |---|---|
  | AH001 | deferred constraint triggers: Σ qty per (journal, item) = 0, Σ value per journal = 0, every journal has lines |
  | AH002 | immutability: insert-only tables, invoice POSTED → CANCELLED only, run snapshots frozen, receipts and BOM versions frozen after DRAFT |
  | AH003 | posting into a locked period (journals, invoices, credit notes, payments, invoice cancellation) |
  | AH004 | payment allocations over the payment or the invoice (locks both rows) |
  | AH005 | value-only lines outside a cost true-up or reversal |
- **Two walls for immutability.** The app role has no UPDATE or DELETE privilege on insert-only tables (fails with
  42501), and a trigger blocks the change even for the table owner (AH002).
- **The API connects as `aahar_app`.** That role is not a superuser and not a table owner, and has no BYPASSRLS, so
  row-level security applies to every query. Migrations run as the owner. Policies compare `organization_id` with
  `aahar_current_org()`, which reads the transaction-local GUC `app.org_id`. When the GUC is unset, the app sees
  nothing. Organizations may be inserted by the app (a fresh BENCHMARK tenant per replay, ADR-0006).
- **Composite foreign keys** on stock and money paths: (id, organization_id), and (lot, item, organization) for lot
  references. A row cannot point at another tenant's parent, or at a lot of a different item, even as the owner.
- **Numbering:** `aahar_next_doc_number(org, doc_type, fy)` upserts the counter row and holds its lock until commit.
  A rolled-back transaction rolls the counter back too, so numbers are gapless.

## Consequences
- Conservation law 1 and the value half of law 2 are enforced by PostgreSQL itself (MP02 gate), as are S1, S3, D1,
  D2, D3, D5, D7 (no overlapping effective dates) and P1/P2.
- Service code still validates first, to give friendly errors. The database is the backstop, not the UI.
- The MP03 login flow needs to find a user's memberships before an org is chosen. It will need a narrow
  SECURITY DEFINER lookup, because `memberships` is RLS-protected.
- Rejected: maintaining balances in service code only (one bypass breaks S3); `FORCE ROW LEVEL SECURITY` for the
  owner (migrations and SECURITY DEFINER guards would then need the GUC too, for no gain while the app is non-owner).
