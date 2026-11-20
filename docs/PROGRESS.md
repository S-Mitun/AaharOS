# PROGRESS

## Status: MP00 done / next: MP01

## Benchmark scoreboard: 0/26
All 26 assertions exist as named strict xfails ("not built yet (MPxx)"). Oracle integrity: 10/10 checks pass
(sha256 guard on `inputs` + `nit_expected`, plus a Decimal re-derivation of every oracle figure: no errors found).

Red items and the MP that turns them green:
- MP04: 1 flour, 2 oil, 3 pouches (stock part)
- MP05: 16 WAC
- MP06: 4 FG after run, 6 yield, 7 oil, 15 spice/cartons, 20 pouch flexible
- MP07: 17 run cost, 18 cost per packet, 19 waterfall
- MP09: 13 Distributor B shortage
- MP10: 5, 8–12, 14, 21, 22, 25
- MP11: 26 integrity
- MP12: 23 shortage attribution, 24 runway

## Done in MP00
- Repo initialised (`git init -b main`, nothing committed). Source docs placed byte-identical (sha256 checked):
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
- CI has never run: there is no GitHub remote yet. The README badge has an `OWNER/REPO` placeholder.
- Hosting provider for the demo URL not chosen (MP17; needs the user's account; free-tier limits to be documented).
- The 7-day plan is tight. Correctness first: no differentiator ships while a benchmark row is red.
- Alembic is not initialised yet (MP02). `make migrate`, `seed-benchmark`, `integrity`, `e2e`, `sim`, `ml-eval` exit 1 with "not built yet".
- Web dev server prints React Router v7 future-flag warnings (harmless).

## Exact next step
Run MP01 in plan mode: ERD (`docs/architecture/erd.mmd`), invariants, ledger table for all 9 NIT steps, BOM doc,
ADRs 0002–0007. No migrations.
