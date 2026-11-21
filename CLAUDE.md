# AaharOS — project memory for Claude Code

This file is loaded at the start of every Claude Code session. Keep it under 200 lines.
The full blueprint lives in @docs/MASTER_PACK.md. Read the section a task needs; don't read all of it every time.
The problem statement is @docs/PROBLEM_STATEMENT.md. The benchmark oracle is @benchmark/expected_results.yaml.

## What we are building
AaharOS is an order-to-audit system for a small South Indian snack factory (NIT Trichy CDI internship task).
Tagline: **"Every gram traced. Every rupee explained."**
Two loops: Sales (order → approve → GST invoice → dispatch → collection) and Production
(purchase → issue per BOM → run → finished goods → variance and cost). They meet at finished-goods stock.

## The four conservation laws (never break these)
1. **Quantity:** every stock journal's lines sum to zero per item (double-entry across locations).
2. **Value:** rupees moved into WIP or finished goods = rupees taken out of raw stock + run costs. Variances are explicit lines, never silent residue.
3. **Mass (food):** recipe input mass is reconciled against good output + scrap + recorded loss. Any unexplained gap is shown, not hidden.
4. **Tax:** sum of invoice tax lines = GST summary = GSTR-shaped export.
Each law has a property test and a CLI check (`make integrity`).

## Golden rules
- Money: Python `Decimal` + PostgreSQL `NUMERIC`. Never float. Round only at posting, ROUND_HALF_UP, to paise. Unit costs are stored to 6 dp.
- Quantities: stored in the canonical base unit (g, mL, piece) as NUMERIC. Conversions only within the same dimension.
- Stock balances are projections of the ledger. No endpoint may write a balance directly.
- Posted documents (invoice, run, receipt, payment) are immutable. Correct them with reversal or credit-note documents.
- Every movement references a source document (type + id). Every privileged mutation writes a hash-chained audit row.
- Every production run freezes a snapshot of its recipe and pack BOM version.
- Every computed figure the UI shows comes from the backend as an `Explained` value (value, unit, formula, inputs with source refs).
- Tax rates, thresholds, HSN, the FSSAI number, GSTIN and the Udyam number are effective-dated config. Never hard-code them.
- Demo data is fictional and labelled DEMO. Never use real company or customer data.
- The benchmark inputs and `nit_expected` in the oracle are sacred. Never change them to make a test pass.

## Architecture (modular monolith)
```
apps/web        React + TypeScript + Vite PWA (salesman mobile, admin desktop, production tablet, owner, auditor)
backend/app     FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16
  modules/      identity, catalog, uom, ledger, valuation, procurement, recipe, production, costing,
                sales, tax, billing, dispatch, collections, planning, traceability, reports, audit, transport, analytics
  each module:  api.py (routes) · service.py (use cases) · domain.py (pure logic, no DB) · models.py · schemas.py · tests/
analytics/      factory simulator, data contracts, SPC, forecasting, evaluation (never writes to the ledger)
benchmark/      expected_results.yaml + runner
docs/           MASTER_PACK.md, PROBLEM_STATEMENT.md, adr/, design-note.md, PROGRESS.md
```
Rule: `domain.py` holds pure functions (variance, tax, valuation, unit conversion) and is 100% unit-testable without a DB.
Modules talk through `service.py` interfaces, never by importing another module's models directly.

## Commands (keep this section accurate; update it when commands change)
- `make up`: start the stack with docker compose
- `make migrate`: apply Alembic migrations
- `make seed-demo`: the LIVE DEMO organization, one login per role (passwords from .env), master data + opening stock (first run)
- `make seed-benchmark`: a fresh BENCHMARK tenant with Section 5 master data and opening stock (older tenants kept, ADR-0006)
- `make benchmark`: run the 9 NIT steps and print the scoreboard against the oracle
- `make test`: backend unit + integration tests
- `make e2e`: Playwright (own compose service, profile `e2e`) on a fresh SIM scratch tenant from `app.cli.seed_e2e`; needs `make up`
- `make integrity`: audit hash chain, laws 1-4 (law 3 flags gaps above tolerance, law 4 = tax lines = GST summary = GSTR-1 export), balance rebuild diff, receipt values, S6 run WIP, reservations covered, invoice tax lines = header
- `make sim`: generate the synthetic 24-month dataset (fixed seed)
- `make ml-eval`: backtests vs baselines + planted-truth recovery report

## How to work on a master prompt (MPxx)
1. Read `docs/PROGRESS.md` first. It records what is done, the scoreboard, open decisions and the next step.
2. Read only the MP section you were asked to run in docs/MASTER_PACK.md, plus any parts it references.
3. Plan before you edit. For MP01, MP02 and anything touching ledger/tax/valuation, show the plan and wait for approval.
4. Implement in small, coherent steps. Run tests after each step. Never claim PASS unless a command ran and you read its output.
5. Update `docs/PROGRESS.md`: done items, benchmark scoreboard (x/26 green), decisions (link the ADR), known gaps, the exact next step.
6. Propose a conventional-commit message (feat(ledger): …). The user commits. One logical change per commit.
7. Stop. Do not start the next MP on your own.

## Definition of done (every MP)
- Tests for the new behaviour exist and pass, including at least one failure-path test.
- `make benchmark` runs. No previously green assertion turned red.
- No float in money or quantity code paths (`grep -rn "float(" backend/app/modules` is clean, or each hit is justified).
- Any new decision touching money, stock, tax, units or audit has an ADR in docs/adr/.
- The UI shows no number that does not come from the database.

## Never do
- Microservices, blockchain, chatbot-first navigation, continuous GPS tracking.
- Live GST, IRP or e-way-bill API calls. These are mock adapters only, clearly labelled.
- Let ML or an LLM write to ledger, invoice, payment or production tables.
- Silently clamp negative stock to zero, or delete a posted record.
- Commit `.env`, secrets or real personal data.
- Rewrite working code just to match the folder plan. Adapt the plan and record why.

## Vocabulary (use these words in UI copy, not database terms)
"Available to promise" (not ATP_qty), "Good packets", "Damaged", "Waste", "Batch", "Recipe", "Pack",
"Stock movement", "Where profit leaks", "Explain this number".
