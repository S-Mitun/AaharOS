# Impact pack (estimates to verify; nothing here is a measured saving)

## What a pilot costs
| Item | Cost | Note |
|---|---|---|
| Phones the salesmen already have, the office laptop | ₹0 | the app is a PWA: no app store, works offline for orders |
| Optional 10" Android tablet for the batch card | ₹10,000-15,000 | estimate; any recent browser works |
| Optional thermal label printer (batch passport QR) | ₹6,000-12,000 | estimate |
| Optional USB barcode / QR scanner | ₹1,500-3,000 | estimate; a phone camera also scans the passport |
| Hosting | ₹0 on free tiers (sleeps when idle); about ₹1,500-2,500 a month for an always-on small server and database | estimates in USD-priced plans; verify the current price |

## Where the money is (formulas tied to what the app measures)
| Lever | Formula (the app shows each input with ⓘ) | Where it comes from |
|---|---|---|
| Yield loss | (expected − good packets) × standard cost per packet, per batch; B-001: 12 × ₹25.60 = ₹307.20 | Where profit leaks |
| Overfill giveaway | grams over declared × good packets × ingredient cost per kg; DEMO B-002: ₹144.43 | Oil and fill weights |
| Expiry returns avoided | packets that may be on shelves near best-before × price | Freshness radar, Morning brief "Visit" |
| Month-end hours | hours to close before vs after; the close checklist and evidence pack replace manual reconciliation | Reports → Close month (measure in the pilot) |
| Delivery km and cost | planned vs actual km per trip; cost-to-serve per customer; the Deal Desk floor | Trips and cost-to-serve |
| Working capital | overdue and MSME-45-day balances called first | Collections, Morning brief |

## Funding pathways (status to verify)
- **Bank cash-credit limit:** the stock and debtors statement with drawing power at the bank's margins (DEMO
  `bank.stock_margin_pct` 25%, `bank.debtors_margin_pct` 40%) comes from Reports, from the books, not a typed number.
- **PMFME** (Pradhan Mantri Formalisation of Micro Food Processing Enterprises): credit-linked subsidy for micro food
  units; eligibility and the current status of the scheme to verify with the district resource person.
- **Udyam registration** (DEMO number on invoices) enables the MSME 45-day payment protection the collections screen
  tracks.

## Social value (baselines to record at the start of a pilot)
- Food safety: every batch traceable to its supplier lots and customers in seconds; oil discarded above the TPC limit.
- Fair weight: short fills flagged against the declared net (Legal Metrology tolerances, DEMO values).
- Waste: fewer expired packets on shelves (freshness radar); yield loss made visible per batch.
- Inclusion: phone-first, offline-tolerant, Tamil interface frame (needs fluent review).

All figures above are illustrative unless the app computed them from DEMO data; record real baselines before claiming
savings.
