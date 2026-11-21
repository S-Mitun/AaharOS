# ADR-0010: Cookie sessions with rotating refresh tokens, and a permission matrix in code

- Status: Accepted (MP03, 2026-11-21)

## Context
MP03 asks for:
- Argon2id passwords
- a short-lived access token in an httpOnly cookie, with a rotating refresh token
- logout that revokes the session
- `require(perm)` on every route
- a login rate limit
- an org GUC set per request

Salesmen use phones on weak networks, so sessions must survive a day in the field. The auditor must be read-only
through the API, not just in the UI.

## Decision
- **Access token:** an HS256 JWT holding user, organization and session id, valid 15 minutes, in the httpOnly cookie
  `aahar_access` (SameSite=Lax, path `/api`). It is not trusted on its own: every request also loads the session,
  membership and user rows. Logout and deactivation therefore take effect immediately, and a role change applies on
  the next request without waiting for a new token.
- **Refresh token:** 32 random bytes in the httpOnly cookie `aahar_refresh` (SameSite=Strict, path `/api/auth`), as
  `<org>.<session>.<secret>`. The org lets the server scope RLS before the lookup. Only the SHA-256 of the secret is
  stored.
  - Every refresh marks the old token used and issues a new one.
  - **Reusing a spent token revokes the whole session** (theft detection) and writes an audit row.
- **Passwords:** argon2-cffi `PasswordHasher` defaults (Argon2id, RFC 9106 low-memory profile), with rehash on
  login. An unknown email still costs one Argon2 verification, and gets the same 401 `invalid_credentials` as a wrong
  password.
- **Rate limit in the database (`login_attempts`):** 5 failures per email or 30 per IP within 15 minutes give 429.
  Database-backed, so it holds across workers and restarts.
- **Permission matrix in code** (`identity/domain.py`), mirrored into `role_permissions` by migration 0007 and kept
  equal by a test.
  - Permissions are split into read and mutating sets. The auditor holds read permissions only, and every mutating
    route must require a mutating permission.
  - Together with the generated route × role tests, this makes "the auditor gets 403 on every mutation" hold by
    construction for future routes too.
- **Org scoping in the auth dependency, not in middleware.** The RLS setting has to be on the same DB session the
  route uses, and only a dependency can reach that session. `org_scope` stores the scope in `session.info` and
  re-applies it on every new transaction (SQLAlchemy `after_begin`). A correlation-id middleware tags responses and
  audit rows.
- **Row filter for salesmen** (assigned customers, own orders) in the sales service, via
  `Principal.sees_only_own_rows`.
- **`users` gets RLS:** visible to itself and the members of the caller's organization. Login uses the
  SECURITY DEFINER function `aahar_login_lookup(email)`, executable only by `aahar_app`.
- **Deactivation is per organization** (`memberships.is_active`). The global `users.is_active` is an owner-only
  kill switch.
- **Failed logins go to `login_attempts`, not the audit chain.** Before login there is no organization, and the
  audit chain is per organization. ADR-0007 is updated to say so.

## Consequences
- Two cookies, no tokens in JavaScript or local storage, so XSS cannot steal a session.
- **CSRF** is covered by SameSite plus a CORS allow-list. A CSRF token can be added if a cross-site embed is ever
  needed.
- **One DB lookup per request** to validate the session. Fine for a small factory, and it buys instant revocation.
- **Multiple tabs:** two tabs refreshing the same token at the same instant revoke the session. This is safe, and
  documented in docs/security.md.
- **Rejected options:**
  - Server-side sessions with opaque cookies only: equivalent, but the JWT lets the server reject a forged or
    expired cookie without touching the DB.
  - Long-lived JWTs without a session row: no real logout.
  - Bearer tokens in local storage: readable by any XSS.
