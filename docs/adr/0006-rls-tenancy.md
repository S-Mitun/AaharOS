# ADR-0006: Organization tenancy with row-level security; a fresh tenant per benchmark replay

- Status: Accepted (MP01, approved 2026-11-21)

## Context
There is one demo factory today, but benchmark data, simulator data and demo data must never mix, and the interview
may ask for "a second factory". Posted records may never be deleted.

## Decision
- Every business table has `organization_id` (NOT NULL, FK). Row-level security policies on every org-scoped table
  compare it with `current_setting('app.org_id')`, which the request middleware sets per transaction (`SET LOCAL`).
- The application connects as a non-owner role so RLS cannot be bypassed; migrations run as the owner.
- Organization kinds: `LIVE` (the demo factory), `BENCHMARK`, `SIM`.
- **A benchmark replay never deletes.** Each `make seed-benchmark` or Judge Mode run creates a **new** BENCHMARK
  organization (`BENCHMARK-<timestamp>`), seeds it and replays NIT's steps. Older benchmark tenants stay as evidence
  and can be archived by a separate, explicitly confirmed maintenance command. Judge Mode works only when
  `JUDGE_MODE_ENABLED=true`.

## Consequences
- A buggy query cannot read another tenant's rows. A second factory is new organization and location rows.
- "Never delete a posted record" holds even for the benchmark.
- Rejected: schema per tenant (migrations × N); a reset that truncates tables (breaks immutability and the audit chain).
