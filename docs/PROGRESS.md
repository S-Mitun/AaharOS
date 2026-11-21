# PROGRESS

## Status: MP03 done (2026-11-21) / next: MP04

## Benchmark scoreboard: 0/26
All 26 assertions exist as named strict xfails ("not built yet (MPxx)"). Oracle integrity: 10/10 checks pass
(sha256 guard on `inputs` + `nit_expected`, plus a Decimal re-derivation of every oracle figure: no errors found).
MP02 and MP03 build no benchmark step, so no row turned green (expected). No green row turned red.

Red items and the MP that turns them green:
- MP04: 1 flour, 2 oil, 3 pouches (stock part)
- MP05: 16 WAC
- MP06: 4 FG after run, 6 yield, 7 oil, 15 spice/cartons, 20 pouch flexible
- MP07: 17 run cost, 18 cost per packet, 19 waterfall
- MP09: 13 Distributor B shortage
- MP10: 5, 8–12, 14, 21, 22, 25
- MP11: 26 integrity
- MP12: 23 shortage attribution, 24 runway

## Done in MP03 (identity, RBAC, hash-chained audit)
- **Gate met:**
  - Generated authorisation tests over every guarded route × all 5 roles pass (35 cases today; new routes join
    automatically).
  - The auditor gets 403 on every mutation.
  - An edited, deleted or tail-deleted audit row is detected (`tests/db/test_audit.py`, `make integrity`).
- **Sessions ([ADR-0010](adr/0010-cookie-sessions-and-rbac.md), [docs/security.md](security.md)):**
  - Argon2id passwords.
  - Access token: 15-minute HS256 JWT in an httpOnly cookie (SameSite=Lax, path /api). The session row is checked on
    every request, so logout and deactivation act immediately.
  - Rotating refresh token: httpOnly, SameSite=Strict, path /api/auth, stored as SHA-256. Reusing a spent token
    revokes the session.
  - Login rate limit: 5 per email or 30 per IP in 15 minutes give 429 (`login_attempts`).
  - Unknown email and wrong password give the same 401.
  - Users with several organizations choose one at login.
- **Permission matrix in code:** `identity/domain.py`, 28 permissions split into read and mutating. Mirrored into
  `role_permissions` by migration 0007; a test keeps them equal.
- **`require(perm)` and `require_login()` dependencies:** a route without a guard (and not on the explicit public
  list) fails CI.
- **Salesman row filter:** assigned customers and own orders only (`GET /api/customers`, `GET /api/orders`).
- **RLS scope from the auth dependency:** the same DB session as the route. The scope is re-applied after every
  commit through SQLAlchemy `after_begin` (why not middleware: docs/security.md).
- **Correlation-id middleware:** `X-Correlation-Id` echoed on responses and stored on audit rows.
- **`audit.record()`:**
  - locks `audit_chain_heads` (no forked chains under concurrency; a test runs 3 writers × 10 rows)
  - redacts secret-looking keys and refuses floats
  - `audit.verify()` also uses the head, so deleting the newest rows is caught
  - `GET /api/audit/log` and `GET /api/audit/verify` serve the auditor and the owner
- **Migration 0007:**
  - tables `auth_sessions`, `refresh_tokens` (RLS) and `login_attempts`; column `memberships.is_active`
  - RLS on `users` (yourself plus members of your organization), so other tenants' password hashes are unreadable
  - `aahar_login_lookup(email)`, a SECURITY DEFINER function executable only by `aahar_app`
  - the `role_permissions` seed
- **CLIs:**
  - `make seed-demo`: LIVE `DEMO-FACTORY` organization with 6 DEMO logins (2 salesmen, admin, production, auditor,
    owner), passwords from `.env`, listed in the README
  - `make integrity`: audit chain for every organization; the laws are listed as "not built yet (MP04/MP11)", never
    as passing
- **Error envelope:** now also covers 401 / 403 / 429, framework 404/405 and request validation (422).
- **Tests:** 134 in total, all passing in Docker (107 PostgreSQL-backed, 27 pure). New in MP03: `test_auth.py` (13),
  `test_rbac.py` (6 + 35 generated), `test_row_filter.py` (2), `test_audit.py` (7), plus pure tests in
  `app/modules/audit/tests` and `app/modules/identity/tests`.
- **Checked live** against the running API on :8180: DEMO admin login, then `/me` as ADMIN; owner-only and
  auditor-only routes give 403; no cookie gives 401.
- **Checks run:** ruff check/format clean, mypy --strict clean (69 files), import-linter 2/2 kept, `alembic check`
  clean, float grep clean, benchmark runs (0/26, oracle 10/10), `make integrity` OK.

## Review of MP00, MP01 and MP02 (2026-11-21, before MP03)
- **MP00:** deliverables are present and match the prompt:
  - traceability covers sections 2–10
  - assumptions A1–A6 and G1–G16
  - 26 strict-xfail assertions plus the oracle-integrity checks
  - CI with lint, tests and benchmark, and the README badge
  - pre-commit, ADR-0000 and ADR-0001
- **MP00 findings fixed:**
  - Traceability still named tables that MP01 renamed (`run_issues`, `run_outputs`) and had placeholder test ids
    for RBAC, row filter and audit. Now updated to the real ones.
  - The error envelope covered only domain errors. Framework 404/405, validation errors and auth errors returned
    FastAPI's default `{"detail": ...}` shape. Fixed in `core/errors.py`.
  - The README status still said "scaffold (MP00)".
- **MP01:** reviewed in the MP02 session; its 9 schema findings and the lot-of-item finding were fixed in MP02.
  Nothing new found.
- **MP02 findings fixed in migration 0006 (`0006_mp02_review_hardening.py`):**
  1. **Cross-tenant leak:** PostgreSQL runs BEFORE triggers before the RLS WITH CHECK. The SECURITY DEFINER
     allocation guard could therefore read another tenant's invoice number or status and leak it in its error
     message, for a row stamped with that tenant's id. A same-org trigger now fires first (42501); see
     `test_rls.py::test_allocation_for_other_org_rejected_before_its_guard_runs`.
  2. **LIVE organizations:** the app role could create LIVE organizations. Now only BENCHMARK and SIM; the LIVE
     factory is seeded by the owner.
  3. **Migration tests:** they hard-coded revision 0005. Now generic: every revision is downgraded and re-applied
     one step at a time, comparing tables, triggers, policies and functions.
  4. **Test count:** this file and the MP02 commit message said "37 new DB tests"; the real number was 42 (53 total
     minus 11 pre-existing). Corrected below. The pushed commit message is left as is.

## Done in MP02 (schema, migrations, database-enforced guards)
- **Gate met:** an unbalanced journal is rejected by PostgreSQL itself at commit (SQLSTATE AH001,
  `tests/db/test_ledger_guards.py::test_unbalanced_journal_rejected`).
- Models for 67 tables, one `models.py` per owning module, plus kernel tables in `app/core/models.py`. Registry:
  `app/db_models.py`. Column types in `app/core/db.py`: `Money` NUMERIC(14,2), `Qty` / `UnitCost` NUMERIC(18,6),
  `Pct` NUMERIC(9,4) ([ADR-0008](adr/0008-money-as-numeric-rupees.md)).
- Alembic, 5 revisions (`backend/migrations/versions/`):
  - 0001: `btree_gist` and the non-owner login role `aahar_app`
  - 0002: schema (autogenerated, reviewed)
  - 0003: guards and triggers
  - 0004: RLS on 61 org-scoped tables plus least-privilege grants
  - 0005: seed of 5 roles, 28 permission codes, 6 system units
- Guards ([ADR-0009](adr/0009-database-enforced-ledger-guards.md)):
  - deferred balance triggers (Σ qty per item, Σ value per journal, ≥ 1 line)
  - line-role sign CHECKs
  - balances maintained by a trigger; the app can only read them
  - store-not-negative CHECK
  - insert-only ledger, invoice lines, payments and allocations, credit notes
  - invoice POSTED → CANCELLED only, with a reason, not if paid
  - run snapshots frozen; completed runs change only cost status or get reversed
  - receipt and BOM-version lines frozen after DRAFT
  - period locks on journals, invoices, credit notes, payments
  - allocations ≤ payment and ≤ invoice
  - gapless `aahar_next_doc_number()`
  - EXCLUDE no-overlap on effective-dated settings and tax rules
  - composite same-org FKs, and lot-of-item FKs
- MP01 review fixes applied to the schema, `erd.mmd` and `ledger.md`:
  - codes and numbers unique per organization
  - balance key allows "no lot" (NULLS NOT DISTINCT)
  - `audit_log` keyed (org, seq), plus `audit_chain_heads`
  - `location_kind` copied onto balances so S1 is a CHECK
  - `payments.unallocated` dropped (computed instead)
  - `credit_note_lines` and `credit_note_tax_lines` added
  - `posting_date` business date drives period locks
  - line roles defined: IN / OUT / SCRAP_IN / VALUE_ONLY
  - raw-material WIP lines carry no lot (a lot belongs to one item)
- Tests: 42 new DB tests, 53 backend tests in total, all passing in Docker. They include:
  - migrations up, down one step, up again; full down and up
  - `alembic check` (models match migrations)
  - J0–J8 of the NIT replay as raw journals: flour 120 kg / ₹5,175.00, oil 19.5 L, pouches 306,
    FG 88 / ₹2,740.64, CUSTOMER ₹4,556.86, B-001 ₹5,855.00
- Wiring:
  - `make migrate` = `alembic upgrade head`
  - compose runs the API as `aahar_app`, migrations as the owner, and DB tests with `AAHAR_REQUIRE_DB=1`
  - CI backend job now has a Postgres 16 service, runs `alembic upgrade head && alembic check`, and runs the DB tests
  - new setting `AAHAR_APP_DB_PASSWORD` (in `.env.example`)
- Checks run: ruff check/format clean, mypy --strict clean, import-linter 2/2 kept, float grep clean, benchmark runs (0/26).

## Done in MP01 (design only; no code, no migrations)
- `docs/architecture/erd.mmd`: 64 entities with keys and cardinalities (renders in Mermaid 11). Corrected in MP02 (see above).
- `docs/architecture/invariants.md`: the 4 conservation laws + 22 invariants, each with where it is enforced and its test id.
- `docs/architecture/ledger.md`: locations, journal kinds, the journal table for every NIT step with quantities and
  values, value and rounding rules. Replayed with `Decimal` before writing: every journal balances per item and in
  value, no store goes negative, B-001 = ₹3,114.36 sold + ₹2,740.64 on hand = ₹5,855.00, COGS A ₹4,556.86.
- `docs/architecture/bom.md`: recipe vs pack spec, drivers, formulas, 200 g / 500 g / mixed-split examples,
  the zero-code 500 g change.
- ADR-0002 to ADR-0007, Accepted on approval (2026-11-21). `docs/architecture/open-questions.md`: Q1–Q8 with recommendations.
- CI actions bumped (checkout v5, setup-python v6, setup-node v5) to clear the Node 20 deprecation warnings.

## Done in MP00
- Repo initialised and pushed to GitHub (S-Mitun/AaharOS); first CI run green. Source docs placed byte-identical (sha256 checked):
  `CLAUDE.md`, `docs/MASTER_PACK.md`, `docs/PROBLEM_STATEMENT.md`, `benchmark/expected_results.yaml`,
  `docs/reference/MASTER_PACK_v1.md`.
- Backend skeleton: `app/core` kernel (config, db, money, Explained, errors, oracle loader), 21 module packages with
  owner MP + allowed deps, FastAPI `/health`, public `GET /api/guide/expected` and `/api/guide/scoreboard`.
- import-linter contracts (layering + core-is-kernel), ruff, mypy --strict, pytest.
- Benchmark: 26 assertions, oracle-integrity tests, scoreboard runner (`make benchmark`) writing `benchmark/results/latest.json`.
- Web: Start-here page, 11-step guided tour, Guide side panel on every page; all numbers from the oracle API.
- Docker Compose (postgres:16, api, web), Makefile, CI workflow, pre-commit, .env.example (DEMO).
- Docs: architecture overview + 4 pipelines, requirements traceability, assumptions (A1–A6, G1–G16), ADR-0000, ADR-0001.

## Decisions (ADRs)
- [ADR-0000](adr/0000-source-precedence.md) source precedence; v1 vs v2 pack conflicts resolved for v2.
- [ADR-0001](adr/0001-modular-monolith-postgres-ledger.md) modular monolith, shared kernel `app/core`, layered modules,
  added `judge` module, everything in Docker.
- Commands: one Makefile, all targets run in Docker; Windows needs `winget install ezwinports.make` once.
- Web styling: plain CSS with tokens (no Tailwind yet). Revisit only if a later MP needs it.
- MP01 (accepted, see ADRs 0002–0007 and open-questions.md): real `WIP` location between issue and completion;
  scrap carries quantity, not value; WAC as a pooled (qty, value) with no rounded unit cost; late run costs via a
  value-only true-up; FG lots at actual cost, FEFO; a new BENCHMARK tenant per replay (no deletes).
- MP02: [ADR-0008](adr/0008-money-as-numeric-rupees.md) money NUMERIC(14,2) rupees, quantities and unit costs
  NUMERIC(18,6). [ADR-0009](adr/0009-database-enforced-ledger-guards.md):
  - balances are maintained by a DB trigger (pulled forward from MP04)
  - guard errors use SQLSTATE AH001–AH005
  - the API runs as the non-owner role `aahar_app` so RLS applies
  - composite same-org and lot-of-item FKs
- MP03: [ADR-0010](adr/0010-cookie-sessions-and-rbac.md):
  - cookie sessions with rotating refresh tokens and reuse detection
  - the permission matrix in code, mirrored in `role_permissions`
  - the org scope set by the auth dependency, not middleware
  - per-org deactivation
  - failed logins in `login_attempts`, not the audit chain (ADR-0007 amended)
- Commits use the GitHub no-reply email (repo-local git config) because the account blocks pushes exposing a private email.
- Host ports: web **5180**, API **8180**, Postgres **5442** (Vite `strictPort`). Other local projects use
  AgriVision 4280-81, 5000, 5280-81, 6379, 8080, 8100-01 and Nexora 5173, 8000. Container-internal ports are unchanged.

## 7-day schedule (deadline set by the user on 2026-11-21: everything incl. a hosted demo within 7 days)
| Day | MPs | Gate |
|---|---|---|
| 1 | MP00, MP01, MP02 | scaffold + CI; ERD approved; migrations + zero-sum trigger green |
| 2 | MP03, MP04, MP05 | RBAC + audit chain; ledger state machine; WAC → 1–3, 15 (stock), 16 |
| 3 | MP06, MP07 | production run + costing → 4, 6, 7, 17–20, 22 (run) |
| 4 | MP08, MP09, MP10 | salesman PWA, inbox, tax/invoice/dispatch/payments → 5, 8–14, 21, 25 |
| 5 | MP11, MP12 | reports, close, planner → 23, 24, 26 → **26/26** |
| 6 | MP15 (Judge Mode, Tamil), MP13 light, MP17 + deploy | hosted demo URL live |
| 7 | MP18, MP19 (+ MP14 / MP16 only if time) | README, design note, video script, red-team |

Cut line, in order: MP14 transport → MP16 ML models (keep simulator + SPC) → MP13 radar.
Never cut: MP00–MP12, Judge Mode, MP17, MP18.

## Known gaps / risks
- `make` is not installed on this Windows machine yet; until it is, run the `docker compose …` lines from the Makefile.
- CI runs on GitHub (S-Mitun/AaharOS) from the first push.
- Hosting provider for the demo URL not chosen (MP17; needs the user's account; free-tier limits to be documented).
- The 7-day plan is tight. Correctness first: no differentiator ships while a benchmark row is red.
- `seed-benchmark`, `e2e`, `sim`, `ml-eval` still exit 1 with "not built yet". `migrate`, `seed-demo` and
  `integrity` (audit chain only) work.
- Web dev server prints React Router v7 future-flag warnings (harmless).
- **MP04 must insert a journal's incoming lines before its outgoing lines.** The store-not-negative CHECK runs per
  line, not at commit (ADR-0009).
- **No login screen yet.** The API supports login; the web app gets its login and role shells with MP08.
- **Salesman assignments:** none are seeded yet. `make seed-demo` creates users only; customers and assignments
  come with the master-data seed (MP05).
- **CSRF:** relies on SameSite cookies plus the CORS allow-list; there is no CSRF token (docs/security.md).
- **Multiple tabs:** two tabs refreshing with the same refresh token at the same instant revoke the session (safe,
  and the user re-logs in).
- **Audit chain head:** stored in the same database. A superuser rewriting rows *and* the head is caught only
  against an exported head hash, which the evidence pack records (MP11).
- **DEMO passwords:** they default to `change-me-demo` when `.env` sets none. Set real ones before hosting (MP17).
  `AAHAR_AUTH_SECRET` must be set outside dev/test; the app refuses to start with the DEMO default.
- `erd.mmd` was edited for the MP02 fixes but not re-rendered (no Mermaid renderer available locally). The
  authoritative schema is `0002_schema.py`.
- The dev DB is migrated to head (0007) and seeded with the DEMO logins.
- Host Python on this Windows machine defaults to cp1252 and CRLF. Scripted file edits must use UTF-8 and LF
  (`.gitattributes` enforces LF on commit).

## Exact next step
Run MP04 in plan mode (it touches the ledger, so the plan needs approval first): the UOM and double-entry ledger
engine.
- `uom.domain` conversions, with property tests for exact round-trips.
- `ledger.domain.build_journal`, which orders incoming lines before outgoing ones (ADR-0009).
- `ledger.service.post` in one transaction, with an audit row and the Idempotency-Key honoured; reversals.
- The balance-rebuild check added to `make integrity`.
- A Hypothesis state machine with at least 500 examples.
- The stock ledger query.
- Turn benchmark assertions 1–3 and 15 (stock parts) green.
