# AaharOS

[![CI](https://github.com/S-Mitun/AaharOS/actions/workflows/ci.yml/badge.svg)](https://github.com/S-Mitun/AaharOS/actions/workflows/ci.yml)

**Every gram traced. Every rupee explained.**

Most billing apps record what was sold. AaharOS explains what was *made*, what it *cost*, where the profit *leaked*,
and what to do *next*. Every number on every screen can be traced to the stock movement or document that produced it.

An order-to-audit system for a small South Indian snack factory, built for the NIT Tiruchirappalli
Centre for Digital Infrastructure internship task. All data is fictional (**DEMO**).

> **Status: MP03 (identity, RBAC, audit chain).** Benchmark scoreboard **0/26**: every assertion is defined and marked
> "not built yet". The database schema and its guards (MP02), logins per role and the hash-chained audit (MP03), the
> Start-here page and the guided tour work today. Business features arrive MP by MP (see `docs/PROGRESS.md`).

## Try it

Needs Docker and `make` (Windows: `winget install ezwinports.make`).

```bash
make up          # postgres (:5442) + api (:8180) + web (:5180)
make migrate     # create the schema
make seed-demo   # DEMO factory + one login per role (passwords from .env)
make benchmark   # 26-row scoreboard against benchmark/expected_results.yaml
make test        # backend tests (unit + PostgreSQL)
make integrity   # verify the audit hash chain (conservation laws arrive in MP04/MP11)
```

Then open http://localhost:5180. The **Start here** page explains the system and the **Guided tour** walks you
through NIT's nine benchmark steps: who does each step, where to click, what to type, and the number you should see.
A **Guide** button on every page brings you back to the right step.

## Test logins

`make seed-demo` creates the DEMO organization `DEMO-FACTORY` with one login per role. Every password is
`DEMO_PASSWORD_<ROLE>` from your `.env`; if you have not set one, it is the local-only default `change-me-demo`.
Set your own before exposing the app anywhere.

| Role | Email | What it can do |
|---|---|---|
| Salesman | `salesman.a@aaharos-demo.invalid`, `salesman.b@aaharos-demo.invalid` | Take orders; sees only assigned customers and own orders |
| Admin | `admin@aaharos-demo.invalid` | Approve orders, invoice, dispatch, payments, price lists, month close |
| Production | `production@aaharos-demo.invalid` | Receipts, recipes, runs, run costs |
| Auditor | `auditor@aaharos-demo.invalid` | Read-only: every mutation returns 403 |
| Owner | `owner@aaharos-demo.invalid` | Everything, including staff and reopening a closed month |

The full permission matrix and the session design are in [docs/security.md](docs/security.md). The API is live from
MP03 (`POST /api/auth/login`); the role screens arrive with MP08 onwards.

## Stack (and why)
PostgreSQL gives exact NUMERIC arithmetic, real transactions and constraint triggers, so the ledger's correctness is
enforced by the database, not only by app code. FastAPI with Pydantic and Python `Decimal` keep the money and tax logic
typed and testable, and Python gives direct access to OR-Tools and the analytics stack. A React PWA covers phone,
tablet and desktop from one codebase and supports offline order capture with no app-store dependency.

## Repository map
| Path | What |
|---|---|
| `apps/web` | React + TypeScript web app (Start here, guided tour; role apps later) |
| `backend/app` | FastAPI modular monolith: `core/` kernel + 21 modules in 7 layers |
| `benchmark/` | NIT oracle, 26 assertions, oracle-integrity checks, scoreboard runner |
| `analytics/` | Simulator and analytics (MP16), read-only |
| `docs/` | Brief, master pack, architecture, ADRs, assumptions, traceability, progress |

## Documentation
- [Architecture and pipelines](docs/architecture/overview.md)
- [Requirements traceability](docs/requirements-traceability.md)
- [Assumptions](docs/assumptions.md)
- [Decisions (ADRs)](docs/adr/)
- [Security: roles, permissions, sessions, audit](docs/security.md)
- [Progress and next step](docs/PROGRESS.md)

Benchmark numbers, demo logins, design note and known gaps are added as they are built (MP03–MP18).
