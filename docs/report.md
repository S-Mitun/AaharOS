# AaharOS: a short report

**Every gram traced. Every rupee explained.** · Live app: https://aaharos-demo.onrender.com

## 1. What it is
AaharOS is an order-to-audit system for a small South Indian snack factory (murukku and similar products). One app,
one address, five people:

| Person | Device | What they do in AaharOS |
|---|---|---|
| Salesman | Phone | Takes a shop's order in under 30 seconds, even without network |
| Factory admin | Desktop | Approves orders against stock that can really be promised, raises GST invoices, dispatches oldest batch first, records payments |
| Production supervisor | Tablet | Buys raw material, runs a batch on a digital batch card, records good packets, damage and costs |
| Owner | Any | Starts the day with three actions ranked by rupee impact, and sees where profit leaks |
| Auditor | Desktop, read-only | Downloads the month's registers, GST summary and evidence pack; every number opens its source document |

Two loops run through it and meet at the finished-goods stock: **sales** (order → approval → GST invoice → dispatch →
payment) and **production** (purchase → issue per recipe → batch → good packets → cost and variance).

## 2. Why it is needed
A small snack factory usually runs on a billing app, a notebook and a spreadsheet. The billing app records what was
sold, but not what was made, what it cost, or why a customer was short. AaharOS closes those gaps:
- **Stock is never guessed.** Every gram moves through a double-entry stock ledger, so balances are always the sum of
  posted movements and can never go below zero.
- **Cost is explained.** Each batch's cost per good packet is computed from the actual material, labour and gas, and the
  gap against standard is shown as a waterfall: yield loss, oil overuse, price changes, damaged pouches.
- **Tax is consistent.** Invoice tax lines, the GST summary and the GSTR-1 file are the same numbers by construction.
- **Every number can be checked.** Tap ⓘ beside any figure to see its formula and the record it came from.
- **People are not slowed down.** Salesmen order offline on a phone; the admin approves in one tap; month end is a
  download instead of a week of copying.
- **It speaks the factory's language.** The whole app switches to Tamil in one tap, and the guided tour reads itself
  aloud in Tamil or English.

## 3. How the guided tour works (step-by-step algorithm)
The tour is one working day of the factory, in twelve cards. Each card says who does it, where to go, what to type
and the number you should see.

1. Open the app and press **Start the guided tour** (or **Restart tour** in the top bar, at any time).
2. Read the step card: **who** does it, **where** (**Take me there** opens the screen), **what to do**, **what you should see**.
3. The voice guide reads the step aloud by itself at normal speed and ends with "tick *I have done this step*, then
   press Next". Press **தமிழ்** for Tamil text and a Tamil voice; Pause, Stop or **Listen to this step** at any time.
4. Sign in as the person the card names: on the sign-in page one tap on a DEMO login fills it in.
5. Do the step on the screen and compare your numbers with **What you should see**. Tap ⓘ on any number to see where it came from.
6. Press the **Guide** button (bottom right) to come back to the same step, tick **I have done this step**, then
   press **Next**. Next stays locked until the step is ticked, and the step list cannot skip ahead.
7. Repeat for all 12 steps. On the last step tick it and press **Finish the tour**.
8. Choose **Create your own factory**, or **Sign in to my account**.

The twelve steps: before you start → buy flour → start a batch → record what it made → Salesman A's order → approve,
invoice and dispatch → Salesman B's order runs short → Retailer A's payment → labour, gas and cost per packet → the
owner's morning → the month's reports → the sample-day check.

## 4. How to get and use your own factory (step-by-step guide)
1. Finish the guided tour on this device: creating a factory opens only after the tour.
2. Press **Create your own factory** (on the finish panel, the home page or the sign-in page).
3. Enter a factory name, your name, your email and a password of at least 10 characters, then press **Create my factory**.
4. You are signed in as the **Owner** of a private factory with the same opening stock, recipe, customers and prices
   as the tour, so the tour's numbers come out exactly the same.
5. Work through a day in the menu: Purchases → Batch card → Today (orders) → Order inbox → Invoices and dispatch →
   Collections → Run costs → Morning brief → Reports.
6. Change thresholds, prices or GST rates in **Owner → Settings**; a change applies from the date you pick.
7. **Sign out** from the top bar. Next time, sign in with the same email and password to continue where you left off.
8. Press **Restart tour** at any time to go over a step again.

Both lists are also inside the app: press **How to** in the top bar and the panel stays open beside any screen, so you
can read a step and do it at the same time.

## 5. Results on the sample day
Done in a newly created factory on the live app, every figure matched the expected values: flour average ₹43.13/kg;
flour 160 → 120 kg; 238 packets after the batch; oil +5%, yield −6% and pouches +3.19% flagged; invoice ₹7,500 +
CGST ₹187.50 + SGST ₹187.50 = ₹7,875.00; dispatch 50 from the opening lot + 100 from batch B-001; Distributor B 88
available and 32 short (IGST ₹300, or ₹220 on the 88); Retailer A owes ₹3,875.00; run cost ₹5,855.00 and ₹31.14 per
good packet; ₹431.20 above standard; one more full batch possible. The **Sample-day check** replays the whole day on a
practice factory and checks all 26 figures in under a minute.

## 6. How it is built
One web address serves the app and its API from a single server (Render); the database and the sign-in service are
Supabase (PostgreSQL 16 and Supabase Auth). Money is exact decimal arithmetic, posted documents are never edited
(mistakes are reversed), and every privileged change is written to a hash-chained audit log. All company, people,
GSTIN and licence data in the app is fictional (DEMO).
