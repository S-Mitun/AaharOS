# Hosted demo: Render (app) + Supabase (database and sign-in)

**Live: https://aaharos-demo.onrender.com** (Render service `aaharos-demo`, blueprint-managed, deploys `main`).

One address serves everything: the API also serves the built web app (`AAHAR_WEB_DIST`), so judges open a single
link. Free tiers only.

## What runs where
- **Render free web service** (`render.yaml`, root `Dockerfile`, region Singapore). On every start
  (`backend/deploy/start.sh`): `alembic upgrade head` → `python -m app.cli.seed_demo` (the permanent DEMO factory,
  its six logins, master data and the MP13 history; idempotent, and it re-activates the DEMO logins and resets their
  passwords) → in the background, the NIT benchmark on a fresh BENCHMARK tenant (the home page scoreboard) →
  uvicorn as the row-level-security role. `python -m app.cli.supabase_users` checks the DEMO logins in Supabase Auth.
- **Supabase free project** `aaharos-demo` (ap-southeast-1), reached through the session pooler
  (`aws-1-ap-southeast-1.pooler.supabase.com:5432`, IPv4). Roles: `aahar_owner` (owns the tables, runs migrations and
  seeds; not a superuser) and `aahar_app` (created by migration 0001; RLS applies). Supabase's `anon` and
  `authenticated` roles have no grant on any AaharOS table, so its public Data API exposes nothing.

- **Supabase Auth** (same project): email + password sign-in, sign-up and sign-out
  ([ADR-0023](adr/0023-supabase-auth-token-exchange.md)). `render.yaml` sets `AAHAR_AUTH_MODE=supabase`,
  `AAHAR_SUPABASE_URL` and the publishable key (public by design). The six DEMO logins are pre-confirmed users. For
  visitors to sign in right after sign-up, switch off **Authentication → Sign In / Providers → Email → Confirm
  email**; with it on, they confirm by email first (set **Authentication → URL Configuration → Site URL** to the
  Render URL so the link comes back to the app).

## Secrets (never committed)
`.env.deploy` (git-ignored) holds the generated passwords; `backend/deploy/supabase_env.py` turns it into
`.env.supabase` (git-ignored) with exactly the three values Render needs: `AAHAR_DATABASE_URL`,
`AAHAR_MIGRATION_DATABASE_URL`, `AAHAR_APP_DB_PASSWORD`. Render generates `AAHAR_AUTH_SECRET` itself.

## Deploy (once)
1. Sign in at https://dashboard.render.com with GitHub and allow access to `S-Mitun/AaharOS`.
2. **New → Blueprint** → pick the repository → branch `main` → Render reads `render.yaml`.
3. When it asks for the three `sync: false` values, paste them from `.env.supabase` (or use **Add from .env**).
4. **Apply**. The first build takes about 10 minutes; later pushes to `main` redeploy by themselves.
5. Open `https://aaharos-demo.onrender.com` (Render shows the exact URL).

## Free-tier limits (honest)
- Render free services sleep after 15 minutes without visits; the next visit wakes it in about a minute (migrations
  and the seed are quick no-ops; the benchmark replay runs in the background).
- 512 MB of memory: measured peak about 300 MB while the start-up benchmark runs.
- Supabase free projects pause after a week without activity; resume from the Supabase dashboard. 500 MB of data:
  each start adds one small BENCHMARK tenant (`AAHAR_BENCHMARK_ON_START=0` turns that off).
- Rate limits (sign-up 5 per IP per hour, public passport 30 per IP per minute) are per process.

## Who can do what on the hosted demo
- Anyone: the home page, the guided tour, the scoreboard, public batch passports.
- The shared DEMO factory: one-tap DEMO logins on the sign-in page (`@aaharos.demo`, shared password `change-me-demo`). Everyone
  shares it, so it fills up with visitors' orders; each restart re-activates the DEMO logins.
- **Create your own factory** (`/sign-up`): a private sandbox (SIM tenant) with NIT's Section 5 starting data and the
  visitor as its Owner. Use fictional data only.
