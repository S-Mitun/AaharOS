# AaharOS

[![CI](https://github.com/S-Mitun/AaharOS/actions/workflows/ci.yml/badge.svg)](https://github.com/S-Mitun/AaharOS/actions/workflows/ci.yml)

**Every gram traced. Every rupee explained.**

Most billing apps record what was sold. AaharOS explains what was *made*, what it *cost*, where the profit *leaked*,
and what to do *next*, for a small South Indian snack factory. Every number on every screen can be traced, with ⓘ, to
the stock movement or document that produced it. Built for the NIT Tiruchirappalli Centre for Digital Infrastructure
internship task. All companies, people, GSTINs and licence numbers are fictional (**DEMO**).

**Live demo:** https://aaharos-demo.onrender.com (one address: the guided tour, the shared DEMO factory and your own
factory). Free hosting: after a quiet spell the first visit takes about a minute to wake the server.

## How to use it (the guided tour comes first)
1. Open the site → **Start the guided tour**. Twelve short steps in NIT's order, each saying who does it, where to
   click, what to type and the number you should see. **Take me there** opens the screen; tap a DEMO login on the
   sign-in page (shared password `change-me-demo`) to act as that role.
2. When every step has been opened, **Finish the tour** offers to **Create your own factory** (a private copy with
   NIT's starting stock, recipe and prices; you are its Owner) or **Sign in to my account**. Own accounts open only
   after the tour.
3. **Restart tour** is in the top bar on every page, any number of times. **Judge Mode** shows the 26-row scoreboard
   and lets the DEMO admin or owner replay NIT's nine steps on a fresh benchmark factory. **தமிழ்** switches the
   app's frame to Tamil (needs fluent review).

## Run it locally (Docker; 4 commands)
Needs Docker and `make` (Windows: `winget install ezwinports.make`). No `.env` is needed for a local run (DEMO
defaults); copy `.env.example` to `.env` to change passwords.
```
make up          # postgres :5442, backend :8180 (/docs), frontend :5180
make migrate     # the schema and its guards
make seed-demo   # the DEMO factory: six logins, master data, opening stock, a short history, transport set-up
make benchmark   # NIT's nine steps replayed on a fresh benchmark factory: the 26-row scoreboard
```
Then open http://localhost:5180. More: `make test` (backend), `make web-test`, `make e2e` (Playwright),
`make integrity` (the four conservation laws), `make sim` / `make ml-eval` (synthetic analytics), `make backup` /
`make restore-check`.

| Login (password `change-me-demo` locally) | Lands on | Can do |
|---|---|---|
| Salesman A / B `salesman.a@aaharos-demo.invalid` | Today | Orders on the phone, offline too; own customers only |
| Factory admin `admin@aaharos-demo.invalid` | Order inbox | Approve, invoice, dispatch, payments, trips, month close |
| Production `production@aaharos-demo.invalid` | Batch planner | Purchases, batch card, run costs, trace, oil and fill weights |
| Owner `owner@aaharos-demo.invalid` | Morning brief | Everything, including staff and reopening a month |
| Auditor `auditor@aaharos-demo.invalid` | Where profit leaks | Read everything; every write returns 403 |

## Benchmark: NIT Section 5 (real output of `make benchmark`, 2026-11-26)
**26 / 26 green**, oracle integrity 10 / 10. The oracle is `benchmark/expected_results.yaml` (inputs and NIT's
expected values are guarded by a checksum test).

| # | Check | Result | # | Check | Result |
|---|---|---|---|---|---|
| 1 | Flour closing 120 kg | green | 14 | Distributor B IGST ₹300 (₹220 on 88) | green |
| 2 | Oil closing 19.5 L | green | 15 | Spice 3.8 kg, cartons 21 | green |
| 3 | Pouches closing 306 | green | 16 | Flour WAC ₹43.125/kg | green |
| 4 | Finished packets after the run 238 | green | 17 | Run cost ₹5,855.00 | green |
| 5 | Finished packets after dispatch A 88 | green | 18 | Cost per good packet ₹31.14 | green |
| 6 | Yield variance −6.00% (flagged) | green | 19 | Waterfall ₹431.20 unfavourable | green |
| 7 | Oil variance +5.00% (flagged) | green | 20 | Pouch flexible variance +3.19% | green |
| 8 | Invoice A taxable ₹7,500.00 | green | 21 | FEFO: 50 opening + 100 of B-001 | green |
| 9 | CGST ₹187.50 | green | 22 | Value conservation (sold + on hand) | green |
| 10 | SGST ₹187.50 | green | 23 | 12 of B's 32 short come from yield loss | green |
| 11 | Invoice A total ₹7,875.00 | green | 24 | Material runway: 1 full batch | green |
| 12 | Retailer A outstanding ₹3,875.00 | green | 25 | B's e-way bill not required | green |
| 13 | B: 120 asked, 88 available, 32 short | green | 26 | Integrity: four laws, audit chain, rebuild | green |

**Cost method:** weighted average cost (WAC) posts; FIFO (₹30.90/packet) and last price (₹31.54) are shown beside it,
never posted. Cost per packet divides by good packets (188), not the expected 200. **Overheads** are not absorbed
into lots (direct cost only; ADR-0014 F7). **Assumptions A1-A6** (opening finished packets at standard ₹28.85, the
standard card at opening rates, FEFO lots, labour and gas direct to the run, the carton as packing and packaging,
both customers GST-registered): [docs/assumptions.md](docs/assumptions.md).

## What NIT asked for, and what is built
| Tier | Feature | Status |
|---|---|---|
| Must | Salesman order (mobile, offline outbox, repeat order) | built (MP08) |
| Must | Approval against available-to-promise, part-approve and backorder | built (MP09) |
| Must | GST invoice (CGST / SGST or IGST), printable, FEFO dispatch, payments and outstanding | built (MP10) |
| Must | Purchases at WAC, BOM issue, production run, finished goods, variances | built (MP05-MP06, MP15 screens) |
| Must | Run cost, cost per packet, where profit leaks (waterfall) | built (MP07) |
| Must | Reports, GST summary and GSTR-1-shaped export, month close, audit trail | built (MP11, MP03) |
| Should | Batch planner (CP-SAT), material runway, shortage attribution, Morning brief | built (MP12) |
| Should | Trace a lot, recall simulator, batch passport QR, freshness radar, oil and fill weights | built (MP13) |
| Stretch | Trips (CVRP), cost-to-serve, Deal Desk floor, CO₂ estimate | built, light (MP14) |
| Stretch | Tamil / English, accessibility checks, Judge Mode | built (MP15; Tamil covers the app's frame) |
| Stretch | Synthetic factory simulator and analytics vs baselines | built (MP16; synthetic only, no UI) |
| Mock | E-way bill and IRP payloads, UPI QR on invoices | mock adapters, labelled DEMO; nothing is sent |

## Tests (real results, 2026-11-27)
| Suite | Command | Result |
|---|---|---|
| Backend unit + PostgreSQL | `make test` | 976 passed |
| Web | `make web-test` | 93 passed |
| Browser (Playwright: salesman, journey, production, axe accessibility) | `make e2e` | 11 passed |
| Benchmark | `make benchmark` | 26/26, oracle 10/10 |
| Conservation laws | `make integrity` | OK |
| Analytics (synthetic, planted truths) | `make ml-eval` | 5 passed; report in [analytics/REPORT.md](analytics/REPORT.md) |

## Stack (and why)
PostgreSQL gives exact NUMERIC arithmetic, real transactions and constraint triggers, so the ledger's correctness is
enforced by the database, not only by app code. FastAPI with Pydantic and Python `Decimal` keep money and tax logic
typed and testable, and Python gives direct access to OR-Tools for the planner and trips. A React PWA covers phone,
tablet and desktop from one codebase and supports offline order capture without an app store.

## Known gaps (honest)
Real GST filing, IRP and e-way bill calls are mocks; HSN, rates, GSTIN, FSSAI, RUCO, TPC and Legal Metrology figures
are DEMO settings to verify with a chartered accountant and the regulators. Tamil covers the frame of the app, not the
screen bodies. Analytics run on synthetic data only and have no screen. The supplier-lot recall can over-name batches
(conservative by design). Trips use straight-line distance × a road factor. Starlette 0.41 stays until a FastAPI
upgrade is tested. Free hosting sleeps when idle. Full list: [docs/PROGRESS.md](docs/PROGRESS.md#known-gaps--risks).

## Documentation
- [Design note (2 pages)](docs/design-note.md) · [Demo script (8 minutes)](docs/demo-script.md) ·
  [Impact](docs/impact.md) · [Judge readiness](docs/judge-readiness.md)
- [Architecture](docs/architecture/overview.md) · [Decisions (ADRs 0000-0022)](docs/adr/) ·
  [Assumptions](docs/assumptions.md) · [Security](docs/security.md) · [Deploy](docs/deploy.md) ·
  [Requirements traceability](docs/requirements-traceability.md) · [Progress](docs/PROGRESS.md)
