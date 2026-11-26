# ADR-0022: Production screens, Judge Mode, Tamil / English, accessibility checks, and the tour-first flow

- Status: Accepted (MP15, 2026-11-26; the user asked for the regression review first, then MP15, all today)
- Builds on: ADR-0013 (the run), ADR-0014 (run costs), ADR-0015 (one app, one screen registry), ADR-0006 (a new
  BENCHMARK tenant per replay)

## Context
The guided tour is the mandatory first task for every visitor, but three of its screens (Purchases, Batch card, Run
costs) were "Coming" pages, so NIT steps 1, 2, 3 and 8 could not be done in the browser. MP15 also asks for Judge
Mode, Tamil / English, accessibility and batch-card polish.

## Decision
- **P1 Production screens.** Purchases → New receipt (supplier lot recorded, the new average cost shown with ⓘ),
  Batch card (start from the recipe and pack or a planner DRAFT; issue with a stock-impact preview that refuses going
  below zero; good packets, damaged pouches with a reason chip, cartons, optional oil and fill samples; big inputs,
  a sticky action bar; the card is a draft on the device until posted), Run costs (labour, gas / power, cost per good
  packet, mark final). They call the existing APIs only; no new posting rule.
- **P2 Judge Mode.** `POST /api/judge/run` (`benchmark.run`) starts `benchmark/runner.py` as a separate process,
  one at a time, on a fresh BENCHMARK tenant; `GET /api/judge/status` is public and holds no data. Guarded by
  `AAHAR_JUDGE_MODE` (on for the demo). The page shows the nine steps with captions and the 26 rows with the oracle's
  values and the tour step that shows each. It never touches the DEMO factory or a visitor's factory.
- **P3 Tamil / English.** A gettext-style catalogue keyed by the English text with English fallback; the shell,
  menu, screen names, tour chrome, home hero and sign-in are translated; all Tamil is marked "needs fluent review";
  numbers, units, codes and document numbers are never translated. Gaps: `docs/i18n-gaps.md`.
- **P4 Accessibility.** axe (WCAG 2.1 A / AA) runs in Playwright on 16 screens signed out and signed in; serious or
  critical violations fail the build. It found white text on the turmeric accent at 3.8:1: filled buttons, the
  Guide button, the active salesman tab and the selected filter chip now use the strong accent (5.6:1). Scrollable
  tables are keyboard-focusable.
- **P5 The tour comes first (deployment review).** Sign-up and signing in with a non-DEMO email stay closed until the
  tour is finished on this device (every step opened, then Finish); the finish panel offers an own account or a
  restart; "Restart tour" is in the top bar on every page. The gate is in the browser (there is no account yet to
  hold it on the server); the DEMO logins stay open because the tour uses them.

## Consequences
- Every screen in the registry is built; the tour can be followed end to end in the browser, and Playwright does NIT
  steps 1-3 and 8 there and gets Rs 31.14 a packet.
- Judge Mode adds one BENCHMARK tenant per run (as `make benchmark` does).
- The tour gate can be bypassed by someone who edits local storage; it guides, it does not secure anything.
- Tamil covers the frame of the app, not the screen bodies, until a fluent speaker reviews a fuller catalogue.
