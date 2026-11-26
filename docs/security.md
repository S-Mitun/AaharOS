# Security: roles, permissions, sessions, audit

The brief: *"Each role should see only what it needs. Role-based access is part of the requirement, not an extra."*
This page is the readable copy of what the code enforces. The source of truth is the matrix in
`backend/app/modules/identity/domain.py`. Migration 0007 seeds the same matrix into `role_permissions`, and
`tests/db/test_rbac.py::test_database_matrix_equals_code` keeps the two identical.

## Roles

| Role | Who | Device |
|---|---|---|
| SALESMAN | Field salesman (5–15 of them) | Phone, weak network |
| ADMIN | Factory admin / billing desk | Desktop |
| PRODUCTION | Production supervisor | Tablet or desktop on the floor |
| AUDITOR | External accountant / auditor | Desktop, **read-only** |
| OWNER | Owner | Any |

## Permission matrix

✓ = allowed. Read permissions are in *italics*; the auditor holds only those.

| Permission | What it allows | SALESMAN | ADMIN | PRODUCTION | AUDITOR | OWNER |
|---|---|:-:|:-:|:-:|:-:|:-:|
| *customer.read* | See customers (salesman: assigned ones only) | ✓ | ✓ | | ✓ | ✓ |
| *order.read* | See orders (salesman: own only) | ✓ | ✓ | | ✓ | ✓ |
| *stock.read* | See stock and movements ("available today" hint; a salesman gets quantities only, no rupee values) | ✓ | ✓ | ✓ | ✓ | ✓ |
| *report.read* | Reports, Explain this number | | ✓ | ✓ | ✓ | ✓ |
| *audit.read* | Audit log and chain verification | | | | ✓ | ✓ |
| order.create | Take a sales order | ✓ | | | | ✓ |
| customer.manage | Create and edit customers | | ✓ | | | ✓ |
| order.approve | Approve, reject, part-approve | | ✓ | | | ✓ |
| order.amend | Change price or quantity (with reason) | | ✓ | | | ✓ |
| price.manage | Publish a price list version | | ✓ | | | ✓ |
| invoice.post | Post a GST invoice | | ✓ | | | ✓ |
| invoice.cancel | Cancel an invoice (with reason) | | ✓ | | | ✓ |
| credit_note.post | Post a credit note | | ✓ | | | ✓ |
| dispatch.post | Post a dispatch | | ✓ | | | ✓ |
| payment.post | Record and allocate a payment | | ✓ | | | ✓ |
| receipt.post | Post a purchase receipt | | | ✓ | | ✓ |
| stock.adjust | Post a stock count adjustment | | ✓ | ✓ | | ✓ |
| stock.adjust.approve | Approve an adjustment | | | | | ✓ |
| recipe.manage | Recipe and pack spec versions | | | ✓ | | ✓ |
| run.start | Start a run and issue material | | | ✓ | | ✓ |
| run.complete | Record output | | | ✓ | | ✓ |
| run.cost | Enter labour, gas/power | | ✓ | ✓ | | ✓ |
| run.reverse | Reverse a run | | ✓ | | | ✓ |
| settings.manage | Effective-dated settings and tax rules | | ✓ | | | ✓ |
| period.lock | Close a month | | ✓ | | | ✓ |
| period.reopen | Reopen a closed month (with reason) | | | | | ✓ |
| user.manage | Add and deactivate staff | | | | | ✓ |
| benchmark.run | Run the NIT benchmark replay | | ✓ | | | ✓ |

**Row filter.** A salesman sees only the customers assigned to them (`salesman_customer_assignments`) and only
their own orders. This is applied in the sales service through `Principal.sees_only_own_rows`
(`tests/db/test_row_filter.py`).

## How a request is checked

1. `CorrelationIdMiddleware` accepts a client's `X-Correlation-Id` (if it is a UUID) or creates one. It is echoed on
   the response and stored on every audit row written by that request.
2. Each route depends on `require("<permission>")`, or on `require_login()` for "who am I". The dependency:
   - reads the access cookie
   - verifies the signed token (HS256, 15 minutes)
   - binds the request's DB session to the caller's organization and user (`org_scope`: RLS settings `app.org_id`,
     `app.user_id`)
   - loads the session, membership and user rows. A revoked session, a deactivated membership or user, or an
     expired session gives 401.
   - checks the role against the matrix. A missing permission gives 403 `forbidden`.
3. **Why a dependency and not middleware sets the org.** MASTER_PACK MP03 says "the request middleware sets the
   org GUC". The setting must be on the same DB session and transaction the route uses, and FastAPI shares one
   `get_session` instance per request between the dependency and the route. Middleware has no access to that
   session. The scope is kept in `session.info` and re-applied at the start of every transaction, so a commit in
   the middle of a request cannot drop it.
4. Public routes are listed explicitly. Today they are login, refresh, logout, `/health` and the read-only
   benchmark guide. `tests/db/test_rbac.py::test_every_route_is_guarded_or_deliberately_public` fails if a new route
   has no guard.

**Tests that prove it** (`tests/db/test_rbac.py`):
- **Route × role matrix:** generated over every guarded route and all five roles. An allowed role never gets
  401/403; a role without the permission always gets 403.
- **Auditor:** gets 403 on every mutating route.
- **Mutating routes:** every POST/PUT/PATCH/DELETE route must require a mutating permission.

## Sessions and tokens (ADR-0010)

| | Access token | Refresh token |
|---|---|---|
| Form | signed JWT: user, org, session id, 15-minute expiry | opaque random secret, stored only as SHA-256 |
| Cookie | `aahar_access`, httpOnly, SameSite=Lax, path `/api` | `aahar_refresh`, httpOnly, SameSite=Strict, path `/api/auth` |
| Lifetime | 15 minutes | 7 days (the session's lifetime) |
| Revocation | immediate: every request checks the session row | rotated on every use; reusing a spent token revokes the whole session |

- JavaScript can never read either cookie. `Secure` is on outside local dev (`AAHAR_COOKIE_SECURE`).
- **Logout** revokes the session at once; the access token stops working even before it expires.
- **Passwords:** Argon2id with argon2-cffi defaults (the RFC 9106 low-memory profile), at least 10 characters for new
  staff, rehashed on login if the parameters change.
- **Login lookup:** an unknown email costs the same Argon2 work as a wrong password, and both get the same
  `invalid_credentials` answer.
- **Rate limit:** 5 failed logins per email, or 30 per IP, within 15 minutes give 429 for the rest of the window,
  even with the right password. Attempts are recorded in `login_attempts`.
- **Secret:** `AAHAR_AUTH_SECRET` signs tokens. The DEMO default is refused at startup when `AAHAR_ENV` is not
  `dev` or `test`.
- **Org choice:** a user with memberships in several organizations must pass `organization_code` at login.

## Database layer (ADR-0006, ADR-0009)

- The API connects as `aahar_app`, which is not a superuser, has no BYPASSRLS and owns no tables.
- **Organization scoping:** row-level security filters every org-scoped table by `app.org_id`. Without it the app
  sees nothing.
- **`users` is RLS-protected too:** a session sees itself and the members of its own organization, so another
  tenant's password hashes are never readable.
- **Login lookup:** login runs before an organization is known, so it uses one narrow SECURITY DEFINER function,
  `aahar_login_lookup(email)`. Only `aahar_app` may execute it.
- **Privileged triggers:** a trigger that runs with owner rights first checks that the row belongs to the session's
  organization (migration 0006).

## Audit trail (ADR-0007)

- `audit.record()` writes one row per privileged action, in the same transaction as the action:
  - login and logout
  - refresh-token reuse
  - user create and deactivate
  - the DEMO seed
  - every posting from MP04 on
- **Each row holds:**
  - actor, action and entity
  - a before/after summary (secret-looking keys such as password, token, secret or hash are replaced with
    `[redacted]`; floats are refused)
  - the correlation id and the time
  - `prev_hash` and `hash = sha256(prev_hash ‖ canonical_json(row))`
- **The chain head:** a per-organization row locked `FOR UPDATE` while writing, so concurrent writers queue instead
  of forking the chain. It also records the last seq and hash, so deleting the newest rows is detected too.
- **Insert-only:** the app has no UPDATE/DELETE right on `audit_log`, and a trigger blocks even the owner.
- **Verification:** `make integrity` recomputes every organization's chain and exits 1 on any break.
  `GET /api/audit/verify` does the same for the caller's organization. Tests edit, delete and tail-delete rows (with
  the trigger switched off, as a superuser could) and the verification catches each one (`tests/db/test_audit.py`).

## DEMO logins

`make seed-demo` creates the LIVE DEMO organization `DEMO-FACTORY` and six logins. The passwords come from `.env`
(`DEMO_PASSWORD_<ROLE>`; the default `change-me-demo` is for local use only). See the README for the list.

## What the salesman's phone stores, and when it is wiped (MP08, ADR-0015 G6)

The salesman app keeps a small IndexedDB database, `aaharos-salesman`, so orders can be taken with no network:

| Stored | Why | Removed |
|---|---|---|
| The outbox: orders saved on the phone (customer, products, packets, list price shown, Idempotency-Key, status) | Send them when the network is back | When received, they stay as a record of what the phone sent until logout |
| Assigned customers | Today screen offline | Logout |
| The priced catalog per customer (price list version, prices ex-tax, packets per carton, the "available today" quantity hint) | Order screen offline | Logout |
| The last order per customer, and the salesman's own orders of the last 30 days | Repeat last order, My orders offline | Logout |
| The id of the user the data belongs to | Wipe it if someone else signs in on the same phone | Logout |

- **No tokens or passwords** are stored by the app: sessions stay in httpOnly cookies (ADR-0010).
- **No stock values, costs or other customers' data:** the catalog carries prices ex-tax and quantity hints only.
- **Logout deletes the whole database.** If orders have not reached the factory, logout first says how many and offers
  "Send now" or "Delete them and sign out". A phone signed into by a different user is wiped before use.
- **Prices cannot be set from the phone:** the server takes each line's price from the price list version the phone
  showed and refuses any other price (`price_mismatch`). A version that went out of force while the phone was offline
  is accepted and flagged stale for the admin (MP09).
- **The service worker caches the app shell only** (HTML, JS, CSS, the icon), never API responses.

## Hardening (MP17)
- **Headers** on every response (`app/core/hardening.py`): `X-Content-Type-Options: nosniff`, `X-Frame-Options:
  DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, a restrictive `Permissions-Policy`, HSTS when cookies
  are secure (HTTPS). The web app served by the API gets a Content Security Policy: scripts from this origin only (the
  Vite build has no inline script), `frame-ancestors 'none'`.
- **CSRF:** the session cookies are SameSite (access `lax`, refresh `strict`, both httpOnly). On top of that, a write
  (POST / PUT / PATCH / DELETE) whose `Origin` is another site (or `null`) is refused with 403 `cross_site_request`.
  Requests without an Origin (curl, the test client) carry no ambient browser credentials from another site.
- **Rate limits:** failed logins per email and per IP (MP03, in the database); sign-up 5 per IP per hour and public
  passports 30 per IP per minute (in-process, per server process).
- **Readiness and logs:** `GET /health` (process up) and `GET /ready` (the database answers as the app role); one JSON
  log line per request (method, path, status, ms, correlation id); never bodies or cookies.
- **Backups:** `make backup` (pg_dump to the git-ignored `backups/`) and `make restore-check` (restores into a scratch
  database and compares row counts of journals, lines, invoices, payments, audit rows, organizations; run on
  2026-11-26: identical).
- **Dependency audit (2026-11-26):** PyJWT 2.10.1 -> 2.15.1 and OR-Tools 9.11 -> 9.15 (protobuf 5.26 -> 6.33) upgraded,
  React Router 6.28 -> 6.30.6 (two high advisories). **Accepted for now:** Starlette 0.41.3 (pinned by FastAPI 0.115):
  FastAPI 0.165 / Starlette 1.x changes request handling and breaks the RBAC tests, so the upgrade is a separate
  change; the app uses no multipart uploads, no sessions middleware and no StaticFiles. React Router's two remaining
  moderate advisories need v7: one is server-side rendering (not used), the other a backslash redirect in
  `<Link>` / `navigate` (our targets are internal paths). pip and pytest advisories are build and test tools only.
- **Secret scan:** the git history has no `.env`, key or certificate file and no real secret; the only matches are
  test constants labelled as such. Deployment secrets live in git-ignored files and the host's dashboard.
- **Performance (DEMO scale, 20 calls each, p95):** inbox 18 ms, stock ledger 26 ms, sales register 29 ms, stock
  summary 16 ms, GST summary 27 ms, freshness 17 ms, cost-to-serve 82 ms, Morning brief 292 ms (the CP-SAT planner).
  Not measured on a 24-month SIM tenant: the simulator writes files, not the ledger (`backend/deploy/perf.py`).

## Known limits (tracked in PROGRESS.md)

- **CSRF:** relies on SameSite cookies (Lax for access, Strict for refresh) plus CORS limited to the web origin.
  There is no separate CSRF token yet.
- **Multiple tabs:** two tabs refreshing with the same token at the same instant look like reuse, and the session is
  revoked. That is safe, and the user logs in again.
- **Login rate limit:** stored in the database, so it holds across API workers. There is no CAPTCHA, by design.
- **Head anchoring:** the chain head lives in the same database. An attacker with superuser rights who rewrites
  rows *and* the head can only be caught against an exported head hash. The month-end evidence pack (MP11) records
  that hash.
