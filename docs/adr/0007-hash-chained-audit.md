# ADR-0007: Tamper-evident, hash-chained audit log

- Status: Accepted (MP01, approved 2026-11-21)

## Context
The brief: edits to invoices and runs are logged with user and time. Auditors need to trust that the log itself has
not been edited.

## Decision
- `audit_log` per organization with a gapless `seq`. Each row stores actor, action, entity, a before/after summary
  (never passwords or tokens), correlation id, `prev_hash` and `hash = sha256(prev_hash ‖ canonical_json(row))`.
- `audit.record()` runs in the same transaction as the mutation and locks the organization's chain head
  (`SELECT … FOR UPDATE`), so concurrent writers cannot fork the chain.
- `audit_log` is insert-only for the application role (UPDATE/DELETE revoked and blocked by a trigger).
- `make integrity` recomputes the chain; any edited, inserted or deleted row breaks verification at that `seq`.
- Every privileged mutation writes one row: posting, reversal, approval, amendment, price change, period lock,
  settings change, login, logout, refresh-token reuse, user create/deactivate.
- **MP03 amendment:** failed logins are recorded in `login_attempts` (global), not in the chain. Before login there
  is no organization, and the chain is per organization (ADR-0010).
- **Implemented in MP03:** `audit_chain_heads` holds the last seq and hash, so deleting the newest rows is also
  detected. Secret-looking keys in summaries are redacted, and floats are refused.

## Consequences
- Blockchain-style evidence without a blockchain. The evidence pack (MP11) includes the verification result.
- Writes serialise per organization on the chain head, which is fine for a small factory.
