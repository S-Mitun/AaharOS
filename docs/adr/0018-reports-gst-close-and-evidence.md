# ADR-0018: Reports, GST export and law 4, law 3 as a check, month-end close, evidence pack

- Status: Accepted (MP11, 2026-11-21; plan and decisions K1–K9 approved by the user the same day, built in five
  commits, one per module)
- Builds on: ADR-0007 (audit chain), ADR-0009 (period-lock guard), ADR-0013 (mass balance), ADR-0017 (invoices)

## Context
NIT step 9 asks for the month's reports; benchmark row 26 asks that the four conservation laws hold, balances rebuild
identically and the audit chain is valid. Before MP11, law 3 was reported but not checked and law 4 was checked per
document only. MP11 adds the reports, the GST summary and export, law 3 and law 4 as real checks, the month-end close
and the evidence pack.

## Decision

### K1. One report engine, three formats
`reports.domain.Report`: a header (title, organization, filters, generated-at, notes), typed columns, rows of exact
strings and totals, each row carrying its source document (`_source`) for drill-down. Rendered as JSON (the screen),
CSV, XLSX (`openpyxl==3.1.5`, Decimals written as numbers) and a printable page (the browser saves it as PDF). Totals
are tested against direct SQL over posted rows.

### K2. The reports
Sales register (net of credit notes; cancelled invoices listed, not totalled), purchase register (MP05 reused), stock
summary (opening, in, out, value adjustments, closing per item and store; closing = opening + in − out + adjustments
and ties to the balance projection), stock ledger, production report, receivables ageing (0–15, 16–45, 46–90, 90+,
age from the invoice date, MSME 45-day marker), and the bank statement (K8).

### K3. GST summary, export and law 4
The month's posted invoices and credit notes sorted into GSTR-1 tables 4A, 5 (B2CL above the effective-dated
`gst.b2cl_threshold`, required only when an unregistered inter-state invoice exists), 7, 9B (CDNR / CDNUR), 12
(HSN) and 13 (documents issued, cancelled counted) and GSTR-3B 3.1(a) net of credit notes. A GSTR-1 JSON in the
portal offline tool's shape, labelled DEMO, for review only: never filed, never sent. **Law 4:** per month, Σ posted
invoice tax lines − Σ credit-note tax lines (direct SQL) = the summary = the export read back; `make integrity` runs
it per organization under row-level security.

### K4. Law 3 as a pass/fail check with flagged gaps
A completed run holds when expected bulk = good packed + scrap + loss + the disclosed unexplained gap, exactly, and
its good output equals what the completion journal posted (packets × net weight). A gap above the variance tolerance
is flagged and shown, never failed or hidden: NIT's B-001 (2.4 kg, 6%) holds and is flagged.

### K5. Month-end close
The Close Cockpit lists open items (orders to decide, orders to invoice, invoices to dispatch, provisional run costs,
open batches, flagged mass gaps, advances, overdue customers) with links, and the organization's 8 integrity checks.
Closing (`period.lock`: admin and owner, as the MP03 matrix already granted) is refused while a check fails; open
items are warnings. Migration 0011: locks get an id, are never deleted, and are reopened once (`period.reopen`:
owner) with time, who and reason through a guard trigger; one active lock per month; the lock function ignores
reopened locks. A future month cannot be closed.

### K6. Evidence Pack
One ZIP: every report as CSV, the GST summary and the GSTR-1 file, every stock line of the range, the audit-chain
verification with its current head hash (the external anchor MP03 asked for), the integrity results, the assumptions
(from the oracle, Decimal loader) and the latest benchmark scoreboard.

### K7. Tally XML
A standard import envelope with one balanced sales voucher per posted invoice (party debited the total; sales and
each tax ledger credited). A DEMO file: nothing connects to Tally.

### K8. Bank stock and book-debts statement
Drawing power = stock at book value × (1 − stock margin) + book debts up to 90 days × (1 − debtors margin); debts
over 90 days are not eligible. Margins are effective-dated settings (DEMO 25% and 40%).

### K9. Auditor → Reports and row 26
One screen (tabs Reports, GST, Close month, Evidence) for every `report.read` role; closing and reopening appear only
for the roles that may. Row 26 reads the NIT tenant's 8 integrity checks from the replay: all pass.

## Also fixed in MP11
- **Single-flight session refresh (web):** several requests finding the access cookie expired at once each started a
  refresh; the second presented an already-rotated token and the server's reuse detection revoked the session. One
  shared refresh now serves every caller in a tab, and the start-up "who am I" check uses it too (a reload after 15
  minutes no longer signs the user out).

## Consequences
- Benchmark 24/26; red: 23 and 24 (MP12).
- `make integrity` now has no "not built yet" lines.
- Reports are synchronous; `export_jobs` stays unused until a report needs a background job.
