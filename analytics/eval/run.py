"""`make ml-eval` (MP16, Part D.3): simulate, clean, then score every method against its baseline and the planted truth.

Splits are by time only: train weeks 0-77 (months 1-18), validation 78-90 (19-21), test 91-103 (22-24), with a
rolling one-week-ahead origin over the test weeks. Prints the report and writes analytics/REPORT.md (synthetic data).
"""

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np

from analytics.models import methods as m
from analytics.pipeline import clean
from analytics.simulator import generate as sim
from analytics.simulator.festivals import festival_weeks

TRAIN_END, TEST_START = 78, 91
HERE = Path(__file__).resolve().parents[1]


def evaluate(seed: int = sim.SEED) -> dict[str, Any]:
    world = sim.simulate(seed)
    c = clean.run(world.orders, world.runs, world.invoices)
    out: dict[str, Any] = {"seed": seed, "pipeline": [vars(s) for s in c.log], "planted": sim.PLANTED}

    # data faults
    dup, unit = world.fault_ids["duplicate"], world.fault_ids["unit_error"]
    out["faults"] = {
        "duplicate_recall": len(dup & c.duplicates_removed) / max(len(dup), 1),
        "duplicate_precision": len(dup & c.duplicates_removed) / max(len(c.duplicates_removed), 1),
        "unit_recall": len(unit & c.unit_fixed) / max(len(unit), 1),
        "unit_precision": len(unit & c.unit_fixed) / max(len(c.unit_fixed), 1),
        "injected": {"duplicate": len(dup), "unit_error": len(unit)},
    }

    # festival uplift and the demand forecast, per SKU x state series
    weekly = clean.weekly(c.orders)
    fest = festival_weeks(sim.START, sim.WEEKS)
    recovered: dict[str, list[float]] = defaultdict(list)
    actual, f_sn, f_ma, f_model = [], [], [], []
    for (sku, state), by_week in weekly.items():
        series = [by_week.get(w, 0) for w in range(sim.WEEKS)]
        if sum(series[:TRAIN_END]) == 0:
            continue
        weeks = {name: ws for name, states, ws in fest if state in states}
        by_name: dict[str, set[int]] = defaultdict(set)
        for name, ws in weeks.items():
            by_name[name] |= ws
        for name, ws in fest_for(state, fest).items():
            factors = m.festival_factors(series, {name: ws}, sim.WEEKS)
            if name in factors and sku.startswith("MURUKKU-2"):
                recovered[name].append(factors[name])
        for t in range(TEST_START, sim.WEEKS):
            factors = m.festival_factors(series, dict(by_name), t)
            actual.append(series[t])
            f_sn.append(m.seasonal_naive(series, t))
            f_ma.append(m.moving_average(series, t))
            f_model.append(m.festival_model(series, t, dict(by_name), factors))
    w_sn, w_ma, w_model = m.wape(actual, f_sn), m.wape(actual, f_ma), m.wape(actual, f_model)
    out["forecast"] = {
        "wape_seasonal_naive": w_sn,
        "wape_moving_average_4w": w_ma,
        "wape_festival_model": w_model,
        "improvement_vs_seasonal_naive": 1 - w_model / w_sn,
        "ships": w_model <= 0.9 * w_sn,
    }
    out["festival_uplift"] = {k: float(np.median(v)) for k, v in recovered.items()}

    # cannibalisation: difference in differences on the 200 g SKU, TN vs KA + KL, festival weeks left out
    any_fest = set().union(*(ws for _, _, ws in fest))
    launch = next(w for w in range(sim.WEEKS) if sim._month(w) >= 13)

    def avg(states: tuple[str, ...], pre: bool) -> float:
        tot = [
            sum(weekly[("MURUKKU-200G", s)].get(w, 0) for s in states)
            for w in range(sim.WEEKS)
            if w not in any_fest and ((w < launch) if pre else (w >= launch))
        ]
        return mean(tot)

    tn = avg(("TN",), False) / avg(("TN",), True)
    ctrl = avg(("KA", "KL"), False) / avg(("KA", "KL"), True)
    out["cannibalisation"] = tn / ctrl - 1

    # SPC on oil per batch, by operator
    runs = sorted(c.runs, key=lambda r: (r.run_date, r.shift))
    ew = m.ewma_by_operator([r.oil_l for r in runs], [r.operator for r in runs])
    o3 = ew.signals.get("O-3", [])
    others = {op: n for op, n in ew.runs.items() if op != "O-3"}
    false_alarms = sum(len(ew.signals.get(op, [])) for op in others)
    baseline_hits = sum(1 for r in runs if r.operator == "O-3" and abs(r.oil_l - 10) / 10 > 0.03)
    baseline_false = sum(1 for r in runs if r.operator != "O-3" and abs(r.oil_l - 10) / 10 > 0.03)
    out["spc"] = {
        "o3_first_signal_run": o3[0] if o3 else None,
        "false_alarms_per_50_runs": 50 * false_alarms / max(sum(others.values()), 1),
        "baseline_3pct_rule_o3_recall": baseline_hits / max(ew.runs.get("O-3", 1), 1),
        "baseline_3pct_rule_false_per_50": 50 * baseline_false / max(sum(others.values()), 1),
        "o3_oil_effect": mean(r.oil_l for r in runs if r.operator == "O-3")
        / mean(r.oil_l for r in runs if r.operator != "O-3")
        - 1,
    }

    # supplier-lot quality
    s05 = [r.yield_pct for r in runs if r.flour_supplier == "S-05"]
    rest = [r.yield_pct for r in runs if r.flour_supplier != "S-05"]
    point, lo, hi = m.bootstrap_diff(s05, rest)
    out["supplier_lot"] = {"S-05_effect": point, "ci95": [lo, hi], "flagged": hi < 0}

    # payment-delay risk: late = paid after 45 days; features from each customer's history before the invoice
    history: dict[str, list[int]] = defaultdict(list)
    route_hist: dict[str, list[int]] = defaultdict(list)
    rows = []
    for inv in sorted(c.invoices, key=lambda i: i.invoice_date):
        h, rh = history[inv.customer], route_hist[inv.route]
        if h:
            month = (date.fromisoformat(inv.invoice_date) - sim.START).days // 30 + 1
            rows.append((month, mean(h), h[-1], mean(rh) if rh else 22.0, int(inv.days_to_pay > 45)))
        h.append(inv.days_to_pay)
        rh.append(inv.days_to_pay)
    arr = np.asarray(rows, float)
    train, test = arr[arr[:, 0] <= 18], arr[arr[:, 0] >= 22]
    model = m.fit_logistic(train[:, 1:4], train[:, 4])
    p = m.predict_logistic(model, test[:, 1:4])
    base = (test[:, 2] > 45).astype(float)
    r7 = [i.days_to_pay for i in c.invoices if i.route == "R-7"]
    out["payment"] = {
        "brier_model": m.brier(p, test[:, 4]),
        "brier_last_time_rule": m.brier(base, test[:, 4]),
        "auc_model": m.auc(p, test[:, 4]),
        "R-7_mean_days": mean(r7),
        "ships": m.brier(p, test[:, 4]) < m.brier(base, test[:, 4]),
    }
    return out


def fest_for(state: str, fest: list[tuple[str, tuple[str, ...], set[int]]]) -> dict[str, set[int]]:
    out: dict[str, set[int]] = defaultdict(set)
    for name, states, ws in fest:
        if state in states:
            out[name] |= ws
    return out


def report(r: dict[str, Any]) -> str:
    pl = r["planted"]
    f, sp, lot, pay, fa = r["forecast"], r["spc"], r["supplier_lot"], r["payment"], r["faults"]
    lines = [
        "# AaharOS analytics report (SYNTHETIC data: `make ml-eval`)",
        "",
        f"Simulator seed {r['seed']}. Every figure below comes from the run that wrote this file. Synthetic-only "
        "performance: it shows the methods recover known truths, not how they would do on a real factory.",
        "",
        "## Pipeline (rows in -> out, and why rows left)",
        *[f"- {s['stage']}: {s['rows_in']} -> {s['rows_out']} {s['reasons']}" for s in r["pipeline"]],
        "",
        "## Planted truths recovered",
        *[
            f"- {name} uplift: recovered x{val:.2f} (planted x{pl['festival_uplift'][name]})"
            for name, val in sorted(r["festival_uplift"].items())
        ],
        f"- S-05 flour lots yield: recovered {lot['S-05_effect']:+.1%} (95% CI {lot['ci95'][0]:+.1%} to "
        f"{lot['ci95'][1]:+.1%}; planted -5.0%) -> {'flagged' if lot['flagged'] else 'NOT flagged'}",
        f"- O-3 oil use: recovered {sp['o3_oil_effect']:+.1%} (planted +4.0%); EWMA first signal on O-3's run "
        f"{sp['o3_first_signal_run']} (gate: within 30), false alarms {sp['false_alarms_per_50_runs']:.2f} per 50 runs "
        "(gate: < 1)",
        f"- Route R-7 pays in {pay['R-7_mean_days']:.1f} days on average (planted 60)",
        f"- 500 g cannibalises 200 g in TN: recovered {r['cannibalisation']:+.1%} (planted -15%)",
        f"- Duplicate syncs caught: {fa['duplicate_recall']:.1%} recall, {fa['duplicate_precision']:.1%} precision "
        f"({fa['injected']['duplicate']} injected; gate >= 99%)",
        f"- Unit slips flagged: {fa['unit_recall']:.1%} recall, {fa['unit_precision']:.1%} precision "
        f"({fa['injected']['unit_error']} injected; gate >= 95%)",
        "",
        "## Methods vs baselines (test months 22-24, rolling one week ahead)",
        f"- Weekly demand WAPE: seasonal-naive {f['wape_seasonal_naive']:.1%}, 4-week average "
        f"{f['wape_moving_average_4w']:.1%}, festival-aware model {f['wape_festival_model']:.1%} "
        f"({f['improvement_vs_seasonal_naive']:.0%} better than seasonal-naive; gate 10%) -> "
        f"{'SHIPS' if f['ships'] else 'does NOT ship: the baseline stays'}",
        f"- Oil drift: EWMA catches O-3 at run {sp['o3_first_signal_run']}; the fixed 3% rule catches "
        f"{sp['baseline_3pct_rule_o3_recall']:.0%} of O-3's runs with "
        f"{sp['baseline_3pct_rule_false_per_50']:.2f} false "
        "alarms per 50 runs of others",
        f"- Late payment (> 45 days): logistic Brier {pay['brier_model']:.3f} vs 'pays like last time' "
        f"{pay['brier_last_time_rule']:.3f}, AUC {pay['auc_model']:.2f} -> "
        f"{'SHIPS as a reminder priority' if pay['ships'] else 'does NOT ship'}",
        "  (route R-7 is cleanly separable in this synthetic data, so these scores are optimistic; expect far less on",
        "  real payment histories)",
        "",
        "Not built (honest gaps): LightGBM quantile demand (P10/P90), pandera contracts (plain-Python checks instead),",
        "mandi-price context, the planner reading the forecast. The UI shows none of these figures yet.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    r = evaluate()
    text = report(r)
    print(text)
    (HERE / "REPORT.md").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
