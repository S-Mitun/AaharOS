# Tamil / English: what is translated and what is not (MP15)

**Every Tamil string needs fluent review.** They were written for the DEMO and have not been checked by a fluent
speaker. Until a person verifies them, treat the Tamil UI as a preview.

## How it works
- `apps/web/src/lib/i18n.tsx`: the English text is the key (gettext style). A string with no Tamil entry falls back
  to English, so nothing is ever blank. The language is remembered on this device (`aaharos.lang`) and sets
  `<html lang>`. The switch is in the top bar (தமிழ் / English).
- Never translated: numbers, rupee amounts, units (kg, L, packets), item codes, document numbers (SO/…, AHR/…,
  GRN/…, MI/…, TRP/…), GSTINs, HSN codes, dates.

## Translated (Tamil, needs fluent review)
The top bar (sign in / out, restart tour, menu, skip link, the language switch), the menu groups and every screen
name in the sidebar, the guided tour's chrome (title, back, finish, the end-of-tour offer), the home page headline
and its two buttons, and the sign-in page (heading, email, password, buttons).

## Not translated yet (falls back to English)
- The body of every screen: tables, explanations, buttons and messages (order inbox, invoices, collections,
  purchases, batch card, run costs, planner, trace and recall, oil and fill weights, trips, freshness, reports,
  Judge Mode, the salesman app).
- The guided tour's step texts (who / where / what to type / why) and the oracle labels.
- Server messages (`error.message` from the API) and the "Explain this number" formulas and labels.
- The printed invoice and the draft recall notice (server-rendered, English).

The next step is a catalogue per screen (the salesman app first: it is used on the road), reviewed by a fluent
Tamil speaker from the factory.
