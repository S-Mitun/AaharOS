# Demo video script (under 8 minutes, NIT's step order, phone + admin)

Record on https://aaharos-demo.onrender.com (open it a minute early: the free server wakes up), or locally after
`make up && make migrate && make seed-demo`. Phone views: browser dev tools → a phone size. Each step is also a card in
the guided tour, which says exactly what to type.

| Time | Screen (login) | Do and say |
|---|---|---|
| 0:00 | Home (signed out) | "Most billing apps record what was sold; AaharOS explains what was made." Point at "26 of 26 benchmark checks passing" and **Start the guided tour**: the tour is everyone's first task. |
| 0:20 | Salesman app → Today (Salesman A, phone size) | DEMO Retailer A → **Repeat last order** or New order 150 → Save. Turn the network off (dev tools → Offline), save another: "Saved on phone". Back online: it sends itself once. |
| 1:10 | Purchases → New receipt (Production) | DEMO Flour Mills, flour 60 kg at ₹45, supplier lot FL-1 → Post. ⓘ on the average cost: ₹43.125/kg = (4,200 + 2,700) / 160. |
| 1:50 | Batch card (Production, tablet size) | Start batch → flour 40, oil 10.5, spice 1.2: the preview shows 160 → 120 kg. Issue. Good 188, damaged 6 (chip "Seal failure"), cartons 9 → Post batch: 120 kg / 19.5 L / 306 pouches / 238 packets. |
| 3:00 | Where profit leaks (Owner) | Yield −6.00% and oil +5.00% flagged; the waterfall ₹431.20; "pouches are judged per good packet: 194 used for 188 good = +3.19%". |
| 4:00 | Order inbox → Invoices (Factory admin) | Approve Retailer A 150 → Create invoice: ₹7,500 + CGST ₹187.50 + SGST ₹187.50 = ₹7,875.00 → printable invoice (FSSAI, DEMO UPI QR, batch passport QR) → dispatch FEFO: 50 opening + 100 of B-001 → 88 left. |
| 4:50 | Order card, Distributor B (admin) | 120 asked, 88 available, 32 short; IGST preview; the options; **Why short?** "12 of the 32 came from this batch's yield loss"; Batch planner: runway 1 full batch, pouches run out first. |
| 5:40 | Collections, then Run costs (admin, Production) | Payment ₹4,000 → ₹3,875 still owed (MSME terms: at most 45 days). Labour ₹1,200 + gas ₹600 → ₹5,855.00, ₹31.14 a packet; on Where profit leaks, FIFO ₹30.90 / last price ₹31.54 beside it. |
| 6:30 | Reports, Close month, Evidence, Trace and recall (Auditor, Production) | Sales register and GST summary; the close checklist with the four laws; the evidence ZIP; trace B-001 back to its flour and forward to Retailer A's invoice; a recall simulation (DEMO, nothing sent). |
| 7:20 | Judge Mode | 26 of 26 green, each row linked to its tour step; the CI badge on GitHub. Close: "Every gram traced. Every rupee explained." |

Say once, plainly: GST, IRP and e-way bill calls are mocks; every name, GSTIN and licence number is DEMO.
