# AaharOS

[![CI](https://github.com/S-Mitun/AaharOS/actions/workflows/ci.yml/badge.svg)](https://github.com/S-Mitun/AaharOS/actions/workflows/ci.yml)

**Every gram traced. Every rupee explained.**

Most billing apps record what was sold. AaharOS explains what was *made*, what it *cost*, where the profit *leaked*,
and what to do *next*, for a small South Indian snack factory. Every number on every screen can be traced, with ⓘ, to
the stock movement or document that produced it. Built for the NIT Tiruchirappalli Centre for Digital Infrastructure
internship task. All companies, people, GSTINs and licence numbers are fictional (**DEMO**).

## Open the app
**https://aaharos-demo.onrender.com** is the whole product: the instructions, the voice-guided tour, the shared DEMO
factory and your own factory, on one address. Nothing to install. Free hosting: after a quiet spell the first visit
takes about a minute to wake the server.

### Start here: the Instructions page
**Instructions** (menu → Guide → Instructions, the home-page button, or the top bar) is the in-app report: what
AaharOS is, why it is needed, and the two step-by-step routines every visitor follows, each with a 🔊 **Listen**
button in English or Tamil.

**Routine 1: the guided tour (first, for everyone)**
1. Press **Start the guided tour** (or **Restart tour** in the top bar, at any time).
2. The **voice guide** reads the step aloud by itself at normal speed: who does it, where, what to type, the number
   you should see, and finally "tick *I have done this step*, then press Next". Pause / Stop / Listen again at any time.
3. Press **Take me there**, sign in as the person the card names (one tap on a DEMO login), and do the step.
4. Tick **I have done this step**. **Next** stays locked until you do, and the step list cannot skip ahead.
5. Repeat for all 12 steps (a working day: buy flour → batch → output → two orders → approve, invoice and dispatch →
   a shortage → payment → run costs → the owner's morning → the month's reports → the sample-day check), then
   **Finish the tour**.

**Routine 2: your own factory**
1. On the finish panel press **Create your own factory**: factory name, your name, email, a password of 10+
   characters.
2. You become the Owner of a private factory with the same opening stock, recipe, customers and prices as the tour,
   and land on its step-by-step instructions.
3. Work through a day: Purchases → Batch card → Today (orders) → Order inbox → Invoices and dispatch → Collections →
   Run costs → Morning brief → Reports. The tour's figures come out exactly (₹43.13/kg flour, ₹7,875.00 invoice,
   ₹3,875.00 owed, ₹31.14 per good packet).
4. Sign out from the top bar; sign in again later with the same email and password.

**Everywhere:** **தமிழ்** switches every screen and the voice to Tamil at once (English to go back). **Keep these
steps beside the screen** docks the routines next to any page. The **Sample-day check** replays the whole day on a
practice factory and checks 26 figures in under a minute. Tap ⓘ beside any number to see its formula and source.

A short written report (what it is, why it is needed, both routines, results): [docs/report.md](docs/report.md).

### DEMO logins (shared factory, password `change-me-demo`)
| Person | Email | Lands on | Can do |
|---|---|---|---|
| Salesman A / B | `salesman.a@aaharos.demo` / `salesman.b@aaharos.demo` | Today | Take orders on the phone, offline too; own customers only |
| Factory admin | `admin@aaharos.demo` | Order inbox | Approve, invoice, dispatch, payments, trips, month close |
| Production supervisor | `production@aaharos.demo` | Batch planner | Purchases, batch card, run costs, trace, oil and fill weights |
| Owner | `owner@aaharos.demo` | Morning brief | Everything, including staff, settings and reopening a month |
| Auditor | `auditor@aaharos.demo` | Where profit leaks | Read everything; every change is refused |

The DEMO factory is shared by every visitor, so it fills up with their orders. Your own factory is private.

## Run it yourself (one command set, Docker)
Needs Docker Desktop and `make` (Windows: `winget install ezwinports.make`). No `.env` is needed for a local run.
```
git clone https://github.com/S-Mitun/AaharOS.git && cd AaharOS
make up            # database, backend (http://localhost:8180/docs) and web app (http://localhost:5180)
make migrate       # create the schema and its guards
make seed-demo     # the DEMO factory: six logins, section 5 master data, opening stock
make benchmark     # replay the section 5 scenario on a fresh factory and print the 26 checks
```
Open http://localhost:5180 and sign in with any DEMO login below (password `change-me-demo`). Checks: `make test`
(backend), `make web-test`, `make e2e` (browser), `make integrity` (the four conservation laws). `make seed-benchmark`
loads only the section 5 master data into a new factory. More: [docs/development.md](docs/development.md).

## How it fits together
```
 Browser (phone · tablet · desktop PWA)
   │  1. sign in / sign up / sign out ───────────────► Supabase Auth (email + password, OAuth 2 password grant)
   │  2. Supabase access token ──► POST /api/auth/exchange
   ▼
 https://aaharos-demo.onrender.com  — one Render web service, one container
   ├─ the built React app (same origin, so no CORS, strict CSP)
   └─ FastAPI: checks the token with Supabase once, opens its own httpOnly session cookie;
      every request then runs as the row-level-security role of the signed-in factory
   ▼
 Supabase PostgreSQL 16 (session pooler)
   ledger · valuation · recipes · production · sales · GST · audit chain · settings
   one schema, every factory separated by row-level security
```
- **Sign-in** is Supabase Auth: the browser signs in at Supabase, the app verifies that token with Supabase and opens
  its own session; **Sign out** ends both. The app stores no passwords for hosted accounts.
- **On every start** the server migrates the schema, refreshes the permanent DEMO factory and its logins, and (in the
  background) replays the sample day for the Sample-day check, and tops the shared DEMO factory's raw and packing
  stock back up to its opening level with an ordinary DEMO purchase receipt.
- Modular monolith: `identity, catalog, uom, ledger, valuation, procurement, recipe, production, costing, sales, tax,
  billing, dispatch, collections, planning, traceability, reports, audit, transport, analytics`. Each module has
  routes, use cases and pure domain logic tested without a database. Details: [docs/architecture/overview.md](docs/architecture/overview.md).

## The four conservation laws (checked by the database and by tests)
1. **Quantity:** every stock journal's lines sum to zero per item. Balances are projections of the ledger.
2. **Value:** rupees into WIP or finished goods = rupees out of raw stock + run costs; variances are explicit lines.
3. **Mass:** recipe input mass = good output + scrap + recorded loss; any gap is shown, never hidden.
4. **Tax:** invoice tax lines = GST summary = GSTR-1-shaped export.

Money is `Decimal` / `NUMERIC` (never float), rounded once at posting to paise. Posted documents are immutable and
corrected by reversals or credit notes. Every privileged change writes a hash-chained audit row. Tax rates, HSN,
GSTIN, FSSAI and thresholds are effective-dated settings the Owner can change.

## Benchmark: NIT Section 5
**26 / 26 green**, oracle integrity 10 / 10, live in the app's Sample-day check. The oracle is
`benchmark/expected_results.yaml` (NIT's inputs and expected values are guarded by a checksum test).

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
never posted. Cost per packet divides by good packets (188), not the expected 200. **Margin:** ₹50.00 − ₹31.14 =
**₹18.86 a packet (37.71% of the selling price)**, shown on Run costs. Monthly overheads are not added to
batches (direct cost only). Assumptions A1-A6: [docs/assumptions.md](docs/assumptions.md).

## What the problem statement asked for, and where it is in the app
| Tier | Feature | Where |
|---|---|---|
| Must | Salesman order on the phone, offline outbox, repeat order | Salesman → Today |
| Must | Approval against available to promise, edit a line's packets or price (with a reason), part-approve, backorder, reject | Admin → Order inbox |
| Must | GST invoice (CGST / SGST or IGST), printable; FEFO dispatch; payments and outstanding | Admin → Invoices, Dispatch, Payments |
| Must | Purchases at WAC, issue per recipe, production run, good packets, damaged, waste, variances | Production → Purchases, Batch card |
| Must | Run cost, cost per good packet, margin against the selling price, where profit leaks (waterfall) | Production → Run costs; Owner → Where profit leaks |
| Must | Reports, GST summary, GSTR-1-shaped export, month close, audit trail | Auditor → Reports |
| Should | Batch planner, material runway, shortage reasons, Morning brief | Owner → Morning brief; Production → Batch planner |
| Should | Trace a batch, recall simulator, batch passport QR, freshness radar, oil and fill weights | Production → Trace and recall, Oil and fill weights |
| Stretch | Trips, cost-to-serve, Deal Desk price floor, CO₂ estimate | Admin → Trips |
| Stretch | Guided tour with a step-by-step voice guide (English and Tamil, Next opens only when a step is done), Instructions page | Guide → Guided tour; Guide → Instructions |
| Stretch | Tamil / English on every screen, accessibility checks, sample-day check | Top bar; Guide → Sample-day check |
| Stretch | Changeable settings and GST rates (effective-dated) | Owner → Settings |
| Mock | E-way bill and IRP payloads, UPI QR on invoices | Labelled DEMO; nothing is sent |

## Tests
| Suite | Result |
|---|---|
| Backend unit + PostgreSQL (`make test`) | 986 passed |
| Web (`make web-test`) | 101 passed |
| Browser, Playwright: salesman, full journey (tour gate, sign-up, own factory), production, axe accessibility (`make e2e`) | 11 passed |
| Benchmark (`make benchmark`) | 26 / 26, oracle 10 / 10 |
| Conservation laws (`make integrity`) | OK |
| Analytics on a synthetic factory, planted truths (`make ml-eval`) | 5 passed; [analytics/REPORT.md](analytics/REPORT.md) |

## Stack (and why)
PostgreSQL gives exact NUMERIC arithmetic, real transactions, constraint triggers and row-level security, so the
ledger's correctness is enforced by the database, not only by app code. FastAPI with Pydantic and Python `Decimal`
keep money and tax logic typed and testable, and Python gives direct access to OR-Tools for the planner and trips. A
React PWA covers phone, tablet and desktop from one codebase and supports offline order capture without an app store.
Supabase provides the managed database and the sign-in service on a free tier; Render runs the single container.

## Known gaps (honest)
Real GST filing, IRP and e-way bill calls are mocks; HSN, rates, GSTIN, FSSAI, RUCO, TPC and Legal Metrology figures
are DEMO settings to verify with a chartered accountant and the regulators. Tamil text and the Tamil voice need a
fluent speaker's review before real use; the invoice's amount-in-words line stays in English. The tour's voice is
pre-recorded (re-run `scripts/tour-voice` when the tour text changes). Analytics run on synthetic data and have no
screen. The supplier-lot recall can over-name batches (conservative by design). Trips use straight-line distance × a road factor. Free hosting sleeps when idle. Full
list: [docs/PROGRESS.md](docs/PROGRESS.md#known-gaps--risks).

## Documentation
- [Report](docs/report.md) · [Design note (2 pages)](docs/design-note.md) · [Demo script (8 minutes)](docs/demo-script.md) ·
  [Impact](docs/impact.md) · [Judge readiness](docs/judge-readiness.md)
- [Architecture](docs/architecture/overview.md) · [Decisions (ADRs)](docs/adr/) · [Assumptions](docs/assumptions.md) ·
  [Security](docs/security.md) · [Hosting](docs/deploy.md) · [Developer setup](docs/development.md) ·
  [Requirements traceability](docs/requirements-traceability.md) · [Progress](docs/PROGRESS.md)
