# ADR-0023: Supabase Auth signs people in; the app keeps its own session

- Status: Accepted (2026-11-27; the user asked for proper sign-in and sign-out with an OAuth server and chose
  Supabase email + password)
- Builds on: ADR-0010 (sessions and tokens), ADR-0006 (tenants), ADR-0022 (the tour comes first)

## Context
The hosted demo kept its own password table (Argon2id). The user wants sign-in, sign-up and sign-out handled by a
real identity server, and one simple flow for the DEMO logins and for visitors' own factories.

## Decision
- **Hosted mode** (`AAHAR_AUTH_MODE=supabase`, `AAHAR_SUPABASE_URL`, `AAHAR_SUPABASE_KEY` = the publishable key):
  the browser signs in, signs up and signs out at Supabase Auth itself (`/auth/v1/token?grant_type=password`,
  `/auth/v1/signup`, `/auth/v1/logout`). It sends the Supabase access token once to `POST /api/auth/exchange`; the
  server checks it with Supabase (`GET /auth/v1/user`), requires a confirmed email, finds the membership by email and
  opens the app's usual httpOnly session (ADR-0010 unchanged: 15-minute access cookie, rotating refresh cookie,
  revocation, audit row). `POST /api/auth/login` (password here) answers 401 `use_supabase_sign_in`.
- **Sign-up** sends the Supabase token instead of a password; the new Owner row has no password hash.
- **Sign-out** ends the app session and the Supabase session.
- **DEMO logins** live in Supabase Auth too, pre-confirmed (the `.demo` domain receives no mail);
  `app.cli.supabase_users` checks them at every start and never sends a sign-up mail while "Confirm email" is on.
- **Authorization stays in the app:** roles, permissions, organizations and row-level security do not depend on
  Supabase; a Supabase account with no membership here gets 401.
- `GET /api/auth/config` (public) tells the browser which mode is on and the public Supabase URL and key; the CSP's
  `connect-src` allows exactly that Supabase URL.
- **Local mode** (the default: tests and `make up`) keeps password sign-in as before.

## Rejected
- Supabase JWTs as the app's session: the app would lose immediate revocation and its own refresh rotation, and every
  request would depend on Supabase's signing keys.
- supabase-js in the browser: three plain REST calls do the job without another dependency.
- A Supabase secret (service-role) key on the server: not needed for verification; one less secret to hold.

## Consequences
- Signing in on the hosted demo needs Supabase to be up; the app session then works on its own for its lifetime.
- With "Confirm email" on in Supabase, a new visitor confirms the email before the first sign-in; the sign-up screen
  says so.
