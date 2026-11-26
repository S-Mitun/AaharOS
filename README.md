# AaharOS

[![CI](https://github.com/S-Mitun/AaharOS/actions/workflows/ci.yml/badge.svg)](https://github.com/S-Mitun/AaharOS/actions/workflows/ci.yml)

**Every gram traced. Every rupee explained.**

**Live demo: https://aaharos-demo.onrender.com** · open it and press **Start the guided tour** (no login needed).
To try a role, **Sign in** and tap a DEMO login (shared password `change-me-demo`), or **Create your own factory**
for a private copy. Free hosting: after a quiet spell the first visit takes about a minute to wake the server.

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
make up          # postgres (:5442) + backend (:8180) + frontend (:5180)
make migrate     # create the schema
make seed-demo   # DEMO factory, one login per role (passwords from .env), master data + opening stock
make seed-benchmark  # a fresh BENCHMARK tenant with NIT section 5 master data and opening stock
make benchmark   # 26-row scoreboard against benchmark/expected_results.yaml
make test        # backend tests (unit + PostgreSQL)
make integrity   # audit hash chain, law 1 per journal, balances rebuilt from the ledger (laws 2-4 arrive in MP11)
make e2e         # Playwright (official image, ~2 GB once) on a fresh scratch tenant: online, offline, duplicate, repeat-order time, stale price
```

**Hosted demo:** https://aaharos-demo.onrender.com (Render + Supabase, see [docs/deploy.md](docs/deploy.md)): the guided tour works without a
login, the sign-in page has one-tap DEMO logins (shared password `change-me-demo`), and **Create your own factory**
gives you a private copy with the same starting data. Free tier: the first visit after a quiet spell takes about a
minute to wake the server.

Then open http://localhost:5180 (the frontend; the backend API is http://localhost:8180, Swagger at `/docs`). The
**Start here** page explains the system and the **Guided tour** walks you through NIT's nine benchmark steps: who does
each step, where to click, what to type, and the number you should see. A **Guide** button on every page brings you
back to the right step. The sidebar lists every screen by role; a screen not built yet says which stage builds it.

**Try the salesman app in one minute:** Sign in → tap **Salesman A** → password `change-me-demo` (local default) →
**Today** → DEMO Retailer A → **New order** → type 150 → **Save order**. The order opens as **Received by factory**
with its number (SO/26-27/…) and ₹7,500.00 ex-tax. Turn the network off (browser dev tools → Offline) and save
another: it says **Saved on phone**, then sends itself when you go back online.

**Then decide as the factory:** Sign out → **Factory admin** → you land on the **Order inbox**. Open the order: the
card shows available to promise (on hand − reserved), the shortage, the credit check, and one button per option:
approve all, **send what is available now and backorder the rest**, wait for the next batch, or reject. Stock is held
the moment you approve, and can never go below zero.

**Then bill and collect:** Invoices and dispatch → **Create invoice** (CGST + SGST inside Tamil Nadu, IGST outside) →
**Open printable invoice** to save it as PDF → **Preview the dispatch** (oldest batch first, with the e-way bill
verdict) → **Record dispatch**. Collections → the customer → **Record payment**: it is applied to the oldest unpaid
invoice, and the rest stays owed.

**Then check the month:** Reports (any admin, owner or auditor) → pick a report and dates → **Show**, or download CSV,
Excel or Print / PDF. **GST** has the month's GSTR-1 tables and GSTR-3B 3.1 and a GSTR-1 file for your CA (for review,
never filed). **Close month** lists what is still open and runs the four conservation laws; closing locks the month
against new postings. **Evidence** downloads the whole month in one ZIP.

**Then start the owner's day:** Sign in as **Owner** → you land on the **Morning brief**: five cards (today's orders,
available vs pending, where profit leaks, material runway, money to collect) and **Today's 3 actions**, biggest rupee
impact first; tap ⓘ on any amount to see how it is worked out. **Production → Batch planner** shows how many batches
each material allows (the ones that run out first are marked), what to make next and what to buy. Its buttons create
a **draft** batch or a **draft** purchase order only; nothing is posted until a person does it.

**Then plan the deliveries:** Admin → **Trips and cost-to-serve** → pick a dispatch date: the planner puts the
day's dispatch notes on vehicles within their carton capacity (shortest route; straight-line distance × a road
factor, no map service), with the trip cost, each stop's share, an estimated CO₂ and a backhaul suggestion when a
supplier is on the way → **Create these trips** → record the actual km and tolls when the vehicle is back. Below,
**cost-to-serve** per customer and the **Deal Desk floor**: the lowest price that still covers the product and the
cost of serving that customer.

**Then trace a batch:** `make seed-demo` adds a short DEMO history (supplier lots, batches B-001 to B-003, orders from
three retailers). **Production → Trace and recall** → pick **B-002**: where it came from (recipe and pack versions,
operator, each material issue and the supplier lots it *may contain*) and where every packet went (dispatch, invoice,
customer, still in store). Pick the flour lot **DEMO-FL-02** → **Simulate recall**: the batches it may be in, every
retailer holding those packets with their invoices, and a printable draft notice marked DEMO (nothing is sent). The
**Batch passport** QR opens a public page with only what is printed on the pack; the QR on a printed invoice also lets
the retailer **Ask for more**, which hands their salesman a link to a pre-filled order. **Production → Oil and fill
weights** shows frying oil per day against the RUCO threshold, oil to discard, and the giveaway in rupees. In the
salesman app, **Freshness** estimates what may still be on each shelf and flags packets near their best-before.

## Test logins

`make seed-demo` creates the DEMO organization `DEMO-FACTORY` with one login per role. Every password is
`DEMO_PASSWORD_<ROLE>` from your `.env`; if you have not set one, it is the local-only default `change-me-demo`.
Set your own before exposing the app anywhere.

| Role | Email | What it can do |
|---|---|---|
| Salesman | `salesman.a@aaharos-demo.invalid`, `salesman.b@aaharos-demo.invalid` | Take orders; sees only assigned customers and own orders |
| Admin | `admin@aaharos-demo.invalid` | Approve orders, invoice, dispatch, payments, price lists, month close |
| Production | `production@aaharos-demo.invalid` | Receipts, recipes, runs, run costs, draft batches and purchase orders, trace and recall, oil and fill weights |
| Auditor | `auditor@aaharos-demo.invalid` | Read-only: every mutation returns 403 |
| Owner | `owner@aaharos-demo.invalid` | Everything, including staff and reopening a closed month |

The full permission matrix and the session design are in [docs/security.md](docs/security.md). The API is live from
MP03 (`POST /api/auth/login`); the salesman app is live from MP08 (a salesman lands on **Today**) and the order inbox
from MP09 (an admin lands on it); the other role screens arrive with their MPs. The sign-in page has one-tap buttons that fill each DEMO email.

## Stack (and why)
PostgreSQL gives exact NUMERIC arithmetic, real transactions and constraint triggers, so the ledger's correctness is
enforced by the database, not only by app code. FastAPI with Pydantic and Python `Decimal` keep the money and tax logic
typed and testable, and Python gives direct access to OR-Tools and the analytics stack. A React PWA covers phone,
tablet and desktop from one codebase and supports offline order capture with no app-store dependency.

## Repository map
| Path | What |
|---|---|
| `apps/web` | React + TypeScript PWA, one app for every role: Start here, guided tour, salesman app (MP08), Where profit leaks, trace and recall (MP13) |
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
