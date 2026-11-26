# AaharOS analytics report (SYNTHETIC data: `make ml-eval`)

Simulator seed 20261126. Every figure below comes from the run that wrote this file. Synthetic-only performance: it shows the methods recover known truths, not how they would do on a real factory.

## Pipeline (rows in -> out, and why rows left)
- contract: 44588 -> 44588 {}
- de-duplicated: 44588 -> 43701 {'same idempotency key': 887}
- canonical units: 43701 -> 43701 {'unit slip corrected (/1000)': 218}
- chronology: 10576 -> 10576 {'paid before invoiced': 0}

## Planted truths recovered
- Deepavali uplift: recovered x3.18 (planted x3.2)
- Onam uplift: recovered x2.65 (planted x2.5)
- Pongal uplift: recovered x1.89 (planted x1.8)
- S-05 flour lots yield: recovered -5.0% (95% CI -5.2% to -4.9%; planted -5.0%) -> flagged
- O-3 oil use: recovered +3.9% (planted +4.0%); EWMA first signal on O-3's run 2 (gate: within 30), false alarms 0.20 per 50 runs (gate: < 1)
- Route R-7 pays in 60.0 days on average (planted 60)
- 500 g cannibalises 200 g in TN: recovered -15.1% (planted -15%)
- Duplicate syncs caught: 100.0% recall, 100.0% precision (887 injected; gate >= 99%)
- Unit slips flagged: 100.0% recall, 100.0% precision (218 injected; gate >= 95%)

## Methods vs baselines (test months 22-24, rolling one week ahead)
- Weekly demand WAPE: seasonal-naive 57.1%, 4-week average 36.5%, festival-aware model 24.3% (57% better than seasonal-naive; gate 10%) -> SHIPS
- Oil drift: EWMA catches O-3 at run 2; the fixed 3% rule catches 76% of O-3's runs with 2.79 false alarms per 50 runs of others
- Late payment (> 45 days): logistic Brier 0.002 vs 'pays like last time' 0.004, AUC 1.00 -> SHIPS as a reminder priority
  (route R-7 is cleanly separable in this synthetic data, so these scores are optimistic; expect far less on
  real payment histories)

Not built (honest gaps): LightGBM quantile demand (P10/P90), pandera contracts (plain-Python checks instead),
mandi-price context, the planner reading the forecast. The UI shows none of these figures yet.
