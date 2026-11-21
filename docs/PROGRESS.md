# PROGRESS

## Status: MP05 done (2026-11-21) / next: MP06

## Benchmark scoreboard: 5/26
- **Green:**
  - 1 flour closing 120 kg, 2 oil 19.5 L, 3 pouches 306, 15 spice 3.8 kg / cartons 21 (MP04)
  - **16 flour WAC ₹43.125/kg after the purchase** (MP05), an `Explained` value from `valuation.wac`, read from
    the ledger
- They are replayed through the real services into a fresh BENCHMARK tenant (`app/modules/judge/replay.py`):
  - J0 opening, valued
  - J1 as a purchase receipt
  - J2 at WAC
  - J3 run output still a labelled stand-in for MP06
- Oracle integrity: 10/10 checks pass (the sha256 guard on `inputs` + `nit_expected` included). No green row turned
  red.

Red items and the MP that turns them green:
- MP06: 4 FG after run, 6 yield, 7 oil, 20 pouch flexible
- MP07: 17 run cost, 18 cost per packet, 19 waterfall
- MP09: 13 Distributor B shortage
- MP10: 5, 8–12, 14, 21, 22, 25
- MP11: 26 integrity
- MP12: 23 shortage attribution, 24 runway

## Done in MP05 (valuation, procurement and lots)
- **Gate met:**
  - WAC = ₹43.125/kg after the NIT receipt (assertion 16 green, 5/26).
  - A duplicate submit gives one receipt (`test_duplicate_submit_gives_one_receipt`: 201 then 200, one journal).
  - FIFO layers are consumed oldest first (property `test_fifo_consumes_the_oldest_layers_first`).
  - Value is conserved: the property `test_wac_pool_drains_to_exactly_zero` checks issued + remaining = received
    after every issue and a drained pool at exactly (0, 0).
  - No green row turned red.
- **Decisions D1–D4 (approved; [ADR-0012](adr/0012-valuation-from-the-ledger.md)):**
  - D1: the WAC pool is read from `inventory_balances` at RAW_STORE + PACK_STORE under the per-(item, store) lock
  - D2: FIFO and last price are replayed from the ledger history and never post
  - D3: OPEN-LOT at the standard ₹28.85, derived from the inputs by `costing.domain.standard_cost`
  - D4: supplier lots go to `lots` and the receipt line; raw stock stays lot-less
  - `item_cost_state` and `valuation_layers` are left unused
- **`valuation`:**
  - `domain.py` (pure): `proportional_value`, `unit_cost`, `line_value`, and the `ValuationMethod` interface with
    WAC / FIFO / LAST and `gain_value` (WAC, else last price, else ₹0 as NO_COST_YET)
  - `service.py`: `pool`, `history`, `wac` (Explained), `issue_value` (locks first), `sensitivity`, `gain_value`,
    `post_opening`, `valuation_summary`
- **`procurement`:**
  - suppliers
  - purchase receipts posted in one savepoint: gapless `GRN/26-27/000001`, DRAFT → POSTED, a SUPPLIER → store
    journal at accepted qty × rate, audit row
  - rejected qty and freight recorded, not stocked (freight shown separately in the register)
  - supplier lot records
  - reversal by mirror journal → REVERSED
  - the purchase register (totals count POSTED receipts)
  - `receipt_value_mismatches` for integrity
- **Kernel:** `app/core/idempotency.py` (claim / complete / request_hash) is now shared by ledger and procurement, and
  `app/core/calendar.py` holds `business_date` and `financial_year`.
- **API** (all covered by the generated route × role tests):
  - `POST /api/purchases/receipts` (`receipt.post`, Idempotency-Key header, decimals as strings: a JSON number is a
    422)
  - `POST /api/purchases/receipts/{id}/reverse`
  - `GET /api/purchases/receipts/{id}`
  - `GET /api/purchases/register`
  - `GET /api/suppliers`
  - `GET /api/stock/valuation` (`report.read`: a salesman gets 403)
- **Seeds:**
  - `make seed-benchmark` creates a fresh BENCHMARK tenant with the section 5 master data and the valued opening
    stock, and prints its code.
  - `make seed-demo` now also adds, on the first run only, to the LIVE DEMO organization: the items, `SUP-DEMO`,
    `RET-A` (TN) and `DIST-B` (KA) with fictional DEMO GSTINs, salesman A → RET-A and salesman B → DIST-B, and the
    opening stock.
  - The master data is written as `aahar_app`, because the owner bypasses RLS.
  - Run on the dev DB, then checked live on :8180:
    - admin sees the valuation (flour ₹42.000000/kg before any purchase)
    - salesman A sees only RET-A, and finished-goods stock without values; 403 on the valuation
- **`make integrity`** adds the receipt-value check; run on the dev DB: all PASS.
- **The state machine** now values outgoing lines with `valuation.domain.proportional_value` instead of its own copy.
- **Replay values checked against ledger.md** (`tests/db/test_replay.py`):
  - flour ₹5,175.00, oil ₹2,730.00, spice ₹760.00, pouches ₹765.00, cartons ₹315.00
  - WIP 0, OPEN-LOT 50 / ₹1,442.50, B-001 188 / ₹4,055.00
  - flour 40 kg sensitivity: WAC ₹1,725.00, FIFO ₹1,680.00, LAST ₹1,800.00
- **Tests:** 279 in total (was 210), all passing in Docker. New in MP05:
  - pure: `valuation/tests/test_domain.py`, `procurement/tests/test_domain.py` (with the financial year and request
    hash), `costing/tests/test_domain.py` (standard cost)
  - Hypothesis found a rounding slip in a test's own expected value (half-even vs the books' half-up), fixed in
    the test; import-linter caught a test importing a higher layer, moved to `costing/tests`
  - PostgreSQL: `tests/db/test_procurement.py`, `tests/db/test_replay.py`
  - generated RBAC cases for the 6 new routes
- **Checks run:** ruff check / format clean, mypy --strict clean, import-linter 2/2 kept, `alembic check` clean (no
  new migration in MP05), float grep clean, benchmark 5/26 (oracle 10/10), `make integrity` OK.

## Review of MP04 (2026-11-21, before MP05)
Three defects found and fixed, each with a test:
1. **Salesmen saw rupee values.** `stock.read` exists for the salesman's "available today" hint, but both stock
   routes returned stock values, which are cost (margin) data. Salesmen now get quantities only
   (`ledger/api.py::_for`; `test_stock_api_balances_and_ledger` asserts no `"value"` key reaches a salesman).
   docs/security.md and ADR-0011 §5b updated.
2. **Deadlocks were 500s.** Two journals that touch the same two balance rows in opposite order (a receipt and its
   reversal) can deadlock; PostgreSQL rolls one back with 40P01. 40P01 and 40001 now become `409 retry` (nothing was
   written, so a retry is safe). `tests/test_pg_errors.py`.
3. **A duplicate item code was a 500.** `catalog.create_item` now runs in a savepoint and reports `item_code_taken`;
   the caller's transaction stays usable. `test_duplicate_item_code_is_a_clear_error`.
- Re-run after the fixes: 210 tests pass (204 + 6), ruff / format / mypy --strict / import-linter clean, benchmark
  4/26 with oracle 10/10.
- Looked at and left as is: idempotency under concurrent duplicates (the second insert waits on the first and then
  replays), savepoint rollback of consumed reservations, running balances under `limit` (the response says
  `truncated`), cross-tenant ids (RLS returns 404 or empty).

## Done in MP04 (units and the double-entry stock ledger)
- **Gate met:**
  - The Hypothesis `RuleBasedStateMachine` (`tests/db/test_ledger_state_machine.py`) ran **500 examples clean**
    against PostgreSQL (217 s locally under Docker Desktop; 2,393 accepted steps and about 2,700 refusals of 6 kinds).
  - Benchmark stock assertions 1–3 and 15 are green: scoreboard **4/26**.
- **Units (`uom.domain`, pure):**
  - Converting to base units (g, mL, piece) only multiplies, so it is exact. More than 6 dp, or a fractional piece,
    is refused, never rounded.
  - Back to kg / L / cartons is display only. `split_into_cartons` is divmod (188 → 9 + 8).
  - A carton's size comes from the pack spec version's `units_per_carton`. Mass ↔ volume needs the item's density
    row in `uom_conversions`.
  - `uom.service` reads densities; a test keeps the seeded `uoms` equal to `domain.SYSTEM_UNITS`.
- **Journal rules (`ledger.domain.build_journal`, pure):**
  - converts every line to base units
  - Σ qty per item = 0 and Σ value = 0
  - the line role is derived from the signs
  - each kind must cite its own source document type
  - reason for ADJUSTMENT / REVERSAL, approver for ADJUSTMENT, a lot on lot-tracked items
  - values already rounded to paise; floats refused
  - incoming lines ordered first
  - the request hash for idempotency is unit-independent (60 kg and 60000 g are the same request)
- **Posting (`ledger.service`):**
  - `post()` runs in a savepoint and never commits (the caller's use case commits once):
    - claim the Idempotency-Key
    - per-(item, store) lock
    - insert the journal and lines
    - consume reservations
    - fire the deferred balance triggers now (`SET CONSTRAINTS … IMMEDIATE`)
    - check available ≥ 0
    - audit row
  - `reverse()` posts the exact mirror; a reversal is not reversible and a journal is reversed once.
  - `reserve()` checks available to promise (non-expired lots minus active reservations) under the lock;
    `release()` needs a reason.
  - DB refusals (AH001–AH005, 23514 by constraint, 23505, 23503, 42501) become clear errors via
    `app/core/pg_errors.py`. New `ConflictError` (409).
  - Also: `create_lot`, `ensure_locations` (the 12 standard locations), `catalog.service.create_item / units_for`,
    `identity.service.create_scratch_tenant` (BENCHMARK / SIM only).
- **Read-only stock API:**
  - `GET /api/stock/balances`: stores by default, `include_virtual`, filters
  - `GET /api/stock/ledger`: item / location / lot / date filters, opening balance, running balance per item, the
    source document per row
  - Both need `stock.read`; the generated route × role tests cover them. Checked live on :8180: auditor login →
    200 on both, no cookie → 401.
- **`make integrity`** adds law 1 (and law 2 per journal) re-summed from the lines, and `inventory_balances` rebuilt
  from `stock_lines` and diffed (diff only, never repair). Run on the dev DB: all PASS.
- **State machine:**
  - Steps: receipts, opening lots, issues and returns, run completions with scrap, dispatches (some consuming a
    reservation), adjustments, reversals, reserve / release, Idempotency-Key replays and 409s, float receipts.
  - Quantities arrive in mixed units (g / kg, mL / L, piece / packet / carton of 20).
  - A model predicts every outcome. After every step: the projection equals the model and a rebuild, law 1 holds,
    no store is negative, available ≥ 0, and no float is read back.
  - Refused steps must leave the database unchanged.
  - A vacuity guard asserts that accepted steps and refusals (negative stock, floats) both really happened.
- **Benchmark replay:** J0 opening, J1 purchase, J2 issue and J3 run output through `ledger.service`, reading only
  the oracle's `inputs`. The CI benchmark job now has a PostgreSQL 16 service and runs the migrations first.
- **Tests:** 204 in total at MP04 close (was 134; 210 after the review), all passing in Docker. New in MP04:
  - pure: `uom/tests/test_domain.py`, `ledger/tests/test_domain.py`
  - PostgreSQL: `tests/db/test_ledger_service.py`, `test_uom.py`, `test_ledger_state_machine.py` (1 test × 500
    examples), plus 10 new generated RBAC cases (2 routes × 5 roles)
- **Checks run:** ruff check / format clean, mypy --strict clean, import-linter 2/2 kept, `alembic check` clean
  (no new migration in MP04), float grep clean, benchmark 4/26 (oracle 10/10), `make integrity` OK.

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
- MP04: [ADR-0011](adr/0011-ledger-posting-rules.md):
  - `post()` runs in a savepoint and never commits; the deferred balance triggers fire inside it
  - the idempotency hash covers the journal's meaning in base units
  - **deviation from the approved plan:** the per-(item, store) lock is a transaction advisory lock, not
    `SELECT … FOR UPDATE` on `inventory_balances`. FOR UPDATE needs UPDATE privilege, and the app role may only read
    the projection (ADR-0009). Same serialisation; proven by the parallel-approval test.
  - a movement that would eat into active reservations is refused, adjustments included
  - the benchmark replay posts at ₹0.00 as a labelled stand-in (approved; replaced by valued postings in MP05)
- MP05: [ADR-0012](adr/0012-valuation-from-the-ledger.md) (amends ADR-0004):
  - D1: the WAC pool is read from the projection
  - D2: FIFO / LAST are replayed from the history
  - D3: the opening FG lot is at the derived standard
  - D4: supplier lots are recorded, not stocked
  - receipts value accepted qty × rate; freight is excluded; decimals arrive as strings
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
- `e2e`, `sim`, `ml-eval` still exit 1 with "not built yet". `migrate`, `seed-demo`, `seed-benchmark`,
  `benchmark` (needs a migrated DB since MP04) and `integrity` (audit chain, law 1, balance rebuild, receipt
  values) work.
- Web dev server prints React Router v7 future-flag warnings (harmless).
- **State-machine cost:** 500 examples take about 3.5 minutes under Docker Desktop on Windows, more than the
  1–2 minutes the plan estimated. CI on Linux should be faster (not measured yet). `AAHAR_SM_EXAMPLES=60` runs a
  quick version locally.
- **Reserved stock cannot be adjusted away** without releasing the reservation first (ADR-0011). If that is too strict
  for real count losses, MP09 can add an "adjust and release" use case.
- **Benchmark tenants accumulate:** every `make benchmark` and `make seed-benchmark` creates a fresh BENCHMARK
  organization in the dev DB (ADR-0006: no deletes). Judge Mode (MP15) will show only the newest.
- **Unused tables:** `item_cost_state` and `valuation_layers` are no longer written (ADR-0012). Drop them in a later
  migration together with `erd.mmd`.
- **No supplier or item management routes yet:** suppliers and items come from the seeds. Adding them through the UI
  needs routes (MP09 / MP17) and a permission decision (there is no `supplier.manage` yet).
- **Raw-material expiry is recorded, not enforced:** supplier lot dates are stored, but raw stock is lot-less (D4),
  so FEFO for raw materials waits for MP13.
- **No stock-posting route:** posting happens inside receipts (MP05), runs (MP06) and dispatches (MP10). No HTTP
  route moves stock without its source document.
- **No login screen yet.** The API supports login; the web app gets its login and role shells with MP08.
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
Run MP06: recipe, pack specs and the atomic production run. Plan first: it touches stock and valuation, so show the
plan and wait for approval. MP06 should:
- replace the replay's J3 stand-in (`app/modules/judge/replay.py`) with a real production run that freezes the recipe
  and pack snapshots, issues at WAC through `valuation.issue_value`, and completes atomically
- turn 4 (FG 238), 6 (yield −6.00%), 7 (oil +5.00%) and 20 (pouch flexible +3.19%) green
- keep 1–3, 15 and 16 green, and keep the replay values equal to ledger.md (`tests/db/test_replay.py`)
