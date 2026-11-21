# AaharOS

[![CI](https://github.com/S-Mitun/AaharOS/actions/workflows/ci.yml/badge.svg)](https://github.com/S-Mitun/AaharOS/actions/workflows/ci.yml)

**Every gram traced. Every rupee explained.**

Most billing apps record what was sold. AaharOS explains what was *made*, what it *cost*, where the profit *leaked*,
and what to do *next*. Every number on every screen can be traced to the stock movement or document that produced it.

An order-to-audit system for a small South Indian snack factory, built for the NIT Tiruchirappalli
Centre for Digital Infrastructure internship task. All data is fictional (**DEMO**).

> **Status: MP05 (valuation and purchase receipts).** Benchmark scoreboard **5/26** green: flour 120 kg, oil
> 19.5 L, pouches 306, spice 3.8 kg / cartons 21, and flour WAC ₹43.125/kg after the purchase, replayed through the
> real services. The rest are defined and marked "not built yet". Working today:
> - the schema and its guards (MP02)
> - logins per role and the hash-chained audit (MP03)
> - the stock ledger and its read-only API (MP04)
> - weighted-average valuation, purchase receipts and the purchase register (MP05)
> - the DEMO factory's master data and opening stock (`make seed-demo`)
> - the Start-here page and the guided tour
>
> Business features arrive MP by MP (see `docs/PROGRESS.md`).

## Try it

Needs Docker and `make` (Windows: `winget install ezwinports.make`).

```bash
make up          # postgres (:5442) + api (:8180) + web (:5180)
make migrate     # create the schema
make seed-demo   # DEMO factory, one login per role (passwords from .env), master data + opening stock
make seed-benchmark  # a fresh BENCHMARK tenant with NIT section 5 master data and opening stock
make benchmark   # 26-row scoreboard against benchmark/expected_results.yaml
make test        # backend tests (unit + PostgreSQL)
make integrity   # audit hash chain, law 1 per journal, balances rebuilt from the ledger (laws 2-4 arrive in MP11)
make e2e         # Playwright (official image, ~2 GB once) on a fresh scratch tenant: online, offline, duplicate, repeat-order time, stale price
```

Then open http://localhost:5180 (the only frontend; the API is http://localhost:8180, Swagger at `/docs`). The
**Start here** page explains the system and the **Guided tour** walks you through NIT's nine benchmark steps: who does
each step, where to click, what to type, and the number you should see. A **Guide** button on every page brings you
back to the right step. The sidebar lists every screen by role; a screen not built yet says which stage builds it.

**Try the salesman app in one minute:** Sign in → tap **Salesman A** → password `change-me-demo` (local default) →
**Today** → DEMO Retailer A → **New order** → type 150 → **Save order**. The order opens as **Received by factory**
with its number (SO/26-27/…) and ₹7,500.00 ex-tax. Turn the network off (browser dev tools → Offline) and save
another: it says **Saved on phone**, then sends itself when you go back online.

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
MP03 (`POST /api/auth/login`); the salesman app is live from MP08 (a salesman lands on **Today**); the other role
screens arrive with their MPs. The sign-in page has one-tap buttons that fill each DEMO email.

## Stack (and why)
PostgreSQL gives exact NUMERIC arithmetic, real transactions and constraint triggers, so the ledger's correctness is
enforced by the database, not only by app code. FastAPI with Pydantic and Python `Decimal` keep the money and tax logic
typed and testable, and Python gives direct access to OR-Tools and the analytics stack. A React PWA covers phone,
tablet and desktop from one codebase and supports offline order capture with no app-store dependency.

## Repository map
| Path | What |
|---|---|
| `apps/web` | React + TypeScript PWA, one app for every role: Start here, guided tour, salesman app (MP08), Where profit leaks |
| `e2e` | Playwright scenarios (`make e2e`) |
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
