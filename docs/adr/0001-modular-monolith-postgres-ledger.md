# ADR-0001: Modular monolith on PostgreSQL with a ledger as the source of truth

- Status: Accepted (MP00, 2026-11-21)

## Context
One small factory, one developer, a 30-minute live interview, and a benchmark judged on exact numbers.
The brief requires ledger-derived stock, no float money, traceability, an audit trail and one-command deployment.

## Decision
- **One FastAPI application** (`backend/app`) with business modules under `app/modules/`, one PostgreSQL 16 database,
  one transaction boundary. No microservices.
- **Shared kernel** `app/core` (config, DB session, money rounding, `Explained`, error envelope, oracle loader).
  CLAUDE.md lists only modules; a kernel is needed so modules don't import each other for basics. `core` may never
  import a module (import-linter contract `core-is-kernel`).
- **Layered modules** (import-linter contract `module-layers`):
  L1 identity, audit → L2 catalog, uom → L3 ledger → L4 recipe, valuation → L5 production, sales, procurement, tax →
  L6 costing, billing, dispatch, collections, transport → L7 judge, reports, planning, traceability, analytics.
  A module may import only from its own or lower layers, and only through the other module's `service.py`.
- **`judge` module** added (not in CLAUDE.md's list): it hosts the public guide endpoints now and Judge Mode in MP15.
- **Stock balances are projections** of a double-entry stock ledger (ADR-0002, MP01). Nothing writes a balance directly.
- **Money and quantities are `Decimal` / `NUMERIC`.** `app.core.money` rejects floats at runtime; the oracle loader
  parses YAML floats straight into `Decimal`.
- **Everything runs in Docker** (Python 3.12, Node 24, Postgres 16) so the host's Python/Node versions don't matter.

## Consequences
- `docker compose up` gives the whole system; the benchmark runs in the same image as the API.
- Module boundaries are checked in CI, so a later split is possible but not planned.
- Alternatives rejected: microservices (needless distribution), SQLite (no constraint triggers / RLS, weaker NUMERIC),
  Node backend (weaker decimal story and no OR-Tools / analytics stack).
