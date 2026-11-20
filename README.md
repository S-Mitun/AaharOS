# AaharOS

[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)

**Every gram traced. Every rupee explained.**

Most billing apps record what was sold. AaharOS explains what was *made*, what it *cost*, where the profit *leaked*,
and what to do *next*. Every number on every screen can be traced to the stock movement or document that produced it.

An order-to-audit system for a small South Indian snack factory, built for the NIT Tiruchirappalli
Centre for Digital Infrastructure internship task. All data is fictional (**DEMO**).

> **Status: scaffold (MP00).** Benchmark scoreboard **0/26**: every assertion is defined and marked "not built yet".
> The Start-here page and guided tour work today; business features arrive MP by MP (see `docs/PROGRESS.md`).

## Try it

Needs Docker and `make` (Windows: `winget install ezwinports.make`).

```bash
make up          # postgres (:5442) + api (:8180) + web (:5180)
make benchmark   # 26-row scoreboard against benchmark/expected_results.yaml
make test        # backend tests
```

Then open http://localhost:5180. The **Start here** page explains the system and the **Guided tour** walks you
through NIT's nine benchmark steps: who does each step, where to click, what to type, and the number you should see.
A **Guide** button on every page brings you back to the right step.

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
- [Progress and next step](docs/PROGRESS.md)

Benchmark numbers, demo logins, design note and known gaps are added as they are built (MP03–MP18).
