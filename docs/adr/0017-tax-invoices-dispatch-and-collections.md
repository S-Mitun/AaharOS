# ADR-0017: GST tax engine, invoices, FEFO dispatch and collections

- Status: Accepted (MP10, 2026-11-21; plan and decisions J1–J10 approved by the user the same day)
- Builds on: ADR-0005 (FEFO lots), ADR-0011 (posting rules, reservations), ADR-0014 (run-cost true-ups),
  ADR-0015 (orders), ADR-0016 (approval and reservations)

## Context
NIT steps 5 and 7 turn Retailer A's approved order into a GST invoice, a dispatch from finished-goods stock and a
part-payment; step 6 asks what Distributor B's order would cost in tax. MP10 builds the tax engine, billing,
dispatch and collections so that the invoice, the stock movement and the customer's balance come from one approval,
with nothing typed twice, and turns benchmark rows 5, 8–12, 14, 21, 22 and 25 green.

## Decision

### J1. A pure tax engine on effective-dated rules
`tax.domain`: supplier state = place of supply → CGST + SGST (each half the rate), else IGST. Tax per line, per head,
ROUND_HALF_UP to paise; CGST and SGST are each round(taxable × rate/2), so they are always equal. The header is the
exact sum of the lines (property-tested). An optional rupee round-off line (setting `invoice.round_to_rupee`, off)
is explicit, never silent. The rate is the `tax_rules` row for the line's HSN in force on the invoice date. Seeds:
HSN 21069099 (DEMO, verify with a CA) at the oracle's `gst_rate_percent` from 22-Sep-2025.

### J2. Invoices from approved packets only
One invoice covers the approved packets not yet invoiced (`invoice_lines` already on POSTED invoices of the order),
at `price_final ?? price_captured`. `AHR/26-27/000001` (≤ 16 characters), gapless per FY through
`aahar_next_doc_number` in the posting savepoint (proven with parallel requests). The order becomes INVOICED when
every agreed packet is invoiced (a part-approved order keeps PART_APPROVED while a backorder is owed).

### J3. Cancellation before dispatch; credit notes after
An invoice is cancelled (reason required) only with no dispatch, no payment and no credit note; the order returns to
APPROVED and its stock stays held. Otherwise a credit note (`CN/26-27/…`) reduces an invoice line's taxable value,
its tax reversed at the line's own heads and rates, never beyond what is left of the line. MP10 credit notes are
value-only; returned goods are MP13 (food safety: returns must not rejoin sellable stock silently).

### J4. The invoice document
Server-rendered HTML with print styles (`GET /api/invoices/{id}/document`); the browser saves it as PDF. Rule 46
particulars, amount in words (Indian numbering), DEMO FSSAI and Udyam numbers, batch / lot numbers once dispatched,
and a DEMO UPI QR (`segno`, pure Python) for a fictional payee, stamped "DEMO - do not pay". WhatsApp (`wa.me`) and
email (`mailto:`) carry a text summary only: no public PDF link and nothing sent by the server. A server-made PDF file
(WeasyPrint needs system libraries) is left to MP17.

### J5. Business identity and thresholds as effective-dated settings
`org.gstin`, `org.fssai_no`, `org.udyam_no`, `org.address`, `org.upi_vpa`, `eway.threshold_interstate`,
`eway.threshold_intrastate`, `invoice.round_to_rupee` (DEMO values in the seeds). Nothing is hard-coded.

### J6. Dispatch, first expiry first out, at lot value
`ledger.fefo_lots`: best-before ascending, undated (opening) lots first, expired lots excluded. A lot's share of its
value is proportional, rounded half up; the last packets of a lot take all of its remaining value. One DISPATCH
journal FG_STORE → CUSTOMER (cost of goods sold) consumes exactly the packets leaving: a larger reservation is
released and re-held as (leaving, staying). Partial dispatch is allowed; choosing other lots needs a reason (stored on
the dispatch line). The admin sees the stock movement before posting (`dispatch-preview`). Dispatches are
insert-only (migration 0010).

### J7. e-Way Bill check: mock only
Required when the consignment value (the dispatched share, tax included) is above the threshold for the movement
(inter- or intra-state settings, ₹50,000 DEMO; the intra-state figure varies by state). A reason sentence and a MOCK
payload are stored on the dispatch (`dispatches.eway_payload`); nothing is ever sent to the portal.

### J8. Payments and collections
`RCP/26-27/…` with an Idempotency-Key; allocation by hand or oldest-due first; over-allocation refused (service and
the `aahar_check_allocation` guard); the remainder is an advance. Outstanding = invoice total − allocations − credit
notes; it now feeds the MP09 credit check. Due date = invoice date + terms; under MSME terms at most 45 days (15 when
none is agreed). Bounced cheques (a payment reversal document) are a known gap.

### J9. The replay in NIT's order
… approve A → invoice → dispatch (J5 at B-001's provisional materials value) → order B → payment ₹4,000 → labour and
gas (true-ups spread 957.45 to CUSTOMER, 842.55 to FG_STORE) → FINAL. Row 4 now reads FG right after the run (the
replay continues past it); rows 17–19 are unchanged.

### J10. Screens
Admin → Invoices and dispatch (Ready to invoice, the invoice with print / share, preview then record dispatch, credit
note, cancel) and Collections (owed, overdue, advance, record payment). The order card shows the tax and e-way preview
for each option (rows 14, 25).

### Providers across layers
Lower layers never import higher ones, so three questions go upward through providers registered at import (and
imported by `app/db_models.py`, which every entry point loads): billing → sales "packets invoiced per item", dispatch
→ billing "packets and lots dispatched per invoice", collections → billing and sales "payments allocated" and
"outstanding".

## Consequences
- Benchmark 23/26; red: 23, 24 (MP12), 26 (MP11).
- `make integrity` adds "each invoice's lines and tax lines add up to its header" (law 4 per document); the GST
  summary and export (law 4 in full) are MP11.
- The tour's steps 5 and 7 are the real clicks.
