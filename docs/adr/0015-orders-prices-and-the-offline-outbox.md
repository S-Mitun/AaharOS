# ADR-0015: Orders, server-side prices and the salesman's offline outbox

- Status: Accepted (MP08, 2026-11-21; plan and decisions G1–G8 approved by the user the same day, G9 added by the user)
- Builds on: ADR-0006 (tenancy, scratch tenants), ADR-0007 (audit), ADR-0010 (cookie sessions and RBAC),
  ADR-0011 (idempotency)

## Context
NIT steps 4 and 6 start with a salesman taking an order on the phone. Phones lose the network, salesmen tap twice, and
prices change while a phone is offline. MP08 builds order taking (the API and a mobile-first salesman app) so that an
order reaches the factory exactly once, at the factory's price, and the phone never claims more than the server has
confirmed. Approval, reservations and the inbox are MP09.

## Decision

### G1. Prices come from the server's price list, never from the phone; a stale price is flagged, not refused
- The price in force for a customer on a date: its customer-specific list if one is in force, else the general list's
  highest version in force (`sales.domain.price_list_in_force`).
- The phone sends the price list version it showed and the price per line. The server takes `price_captured` from that
  version; any other price is refused (`price_mismatch`, 422), so a tampered phone cannot set prices.
- If that version is no longer the one in force when the factory receives the order, the order is accepted and
  flagged **stale**, with the current price shown alongside; the admin decides in MP09. The flag is recomputed on
  read from the versions known when the order was received (`known_at` = the order's `created_at`), so publishing a
  later version never turns an earlier order stale. No column is added.
- Price list items are append-only (migration 0009: trigger + grants, SQLSTATE AH002). Prices change by publishing a
  new version (`POST /api/price-lists`, `price.manage`).

### G2. Orders are in whole packets
Quantities travel as whole-number strings and are stored as integers. The carton-aware stepper (tap + = 1 packet,
hold + or "+1 carton" = one carton) takes packets per carton from the item's ACTIVE pack spec
(`recipe.service.units_per_carton`); the order stores packets only.

### G3. Numbers and dates
`SO/26-27/000001`, gapless per financial year (`aahar_next_doc_number`, doc type `SO`), given when the factory
**receives** the order; a refusal rolls the number back with the savepoint. `order_date` = the factory's business date
on receipt; `captured_at` = when the order was saved on the phone ("saved on phone at").

### G4. Idempotency
The phone makes a UUIDv7 when the order is saved and sends it as `Idempotency-Key`; it is also stored on the order. A
replay returns the original order (200, `replayed: true`); the same key with a different order is 409
(`idempotency_key_reused`) and lands in the phone's Needs-attention view. The request hash covers customer, price list
version, `captured_at` and the lines, independent of line order and trailing zeros.

### G5. The outbox and sync
- Dexie (IndexedDB, `dexie@4.0.10`) holds the outbox; `vite-plugin-pwa@0.21.1` adds the manifest and a service worker
  that caches the app shell (production build only; the dev server does not register it).
- States: Saved on phone → Sending → Received by factory (only after the server's 201/200 with an order number) →
  Approved / Rejected (read from the server; approval is MP09).
- Sync runs on app start, on the browser's `online` event, and on a timer with exponential backoff (2 s doubling to
  5 min, jitter 0.8–1.2). The Background Sync API is not used (Safari lacks it).
- Network errors, 5xx, 408 and 429 keep the order "Saved on phone"; any other 4xx moves it to **Needs attention**
  with the server's reason, where it can be discarded, or edited and re-sent with a new key; a 401 pauses sync until
  the salesman signs in again (the outbox is kept). An order left "Sending" by a closed tab returns to "Saved" on start.
- The engine (`apps/web/src/sales/sync.ts`) is a pure state machine with an injected clock, network and store.

### G6. Minimal device cache, wiped at logout
Only the assigned customers, the priced catalog, the last order per customer and the salesman's own orders of the last
30 days are cached. Logout deletes the whole IndexedDB database; with unsent orders it first says how many and offers
"Send now" or "Delete them and sign out". A phone signed into by a different user is wiped first. See
docs/security.md.

### G7. Role shells after sign-in
A SALESMAN lands on `/sales` (Today · My orders · Summary). Other roles keep today's pages until their MPs. The
"available today" hint is quantities only (✓ in stock / ⚠ partial), from `stock.read`, never values. Product pictures
are generated DEMO illustrations.

### G8. Playwright in its own compose service
`mcr.microsoft.com/playwright:v1.49.1-jammy`, profile `e2e`, run by `make e2e` against the dev stack. Each run makes
a fresh **SIM** scratch tenant with its own logins and a random per-run password (`python -m app.cli.seed_e2e`), so it
never touches the DEMO factory, and Judge Mode (which reads BENCHMARK tenants) never sees it. The repeat-order time is
measured and printed; no target is claimed.

### G9. One web app and one backend, the guided tour first
`apps/web/src/guide/screens.ts` is the single registry for the sidebar (grouped Guide · Salesman · Admin · Production ·
Owner · Auditor · Judge), the routes (`src/routes.tsx`) and the tour's "Take me there" links. A screen not built yet
opens an honest "Coming in MPxx" page. Signed out, everything can be browsed; signed in, the sidebar hides what the
role cannot use (the API still enforces every permission).

## Consequences
- The benchmark replay posts steps 4 and 6 as SUBMITTED orders (no salesman: BENCHMARK tenants have no logins); no
  benchmark row changes (13 is MP09).
- ADMIN does not hold `order.create` (OWNER and SALESMAN do): an admin entering an order for a customer is an MP09
  question (phone orders taken at the factory).
- Running totals on the order screen are estimates computed from the server's prices with exact decimals and labelled
  "estimated"; the confirmed total (an `Explained` value) appears once the factory has received the order.
- `make seed-demo` now tops up an older DEMO factory with what later MPs added (MP06 items, recipe, pack specs, card,
  tolerance; the MP08 price list), never changing or deleting anything.
