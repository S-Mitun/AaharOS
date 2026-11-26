"""Analytics methods (MP16, Part D.3). They advise only: nothing here writes to the books.

- forecast: seasonal-naive and 4-week-average baselines vs a festival-aware level model (rolling origin, 1 week ahead)
- spc: EWMA chart per operator with limits from the first 20 runs (Phase I)
- lot_effect: supplier-lot yield difference with a bootstrap confidence interval
- payment risk: logistic regression on payment history vs the "pays like last time" rule
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

# ---------- demand forecast ----------


def wape(actual: Sequence[float], forecast: Sequence[float]) -> float:
    a, f = np.asarray(actual, float), np.asarray(forecast, float)
    return float(np.abs(a - f).sum() / max(a.sum(), 1e-9))


def seasonal_naive(series: Sequence[float], t: int) -> float:
    return float(series[t - 52])


def moving_average(series: Sequence[float], t: int, k: int = 4) -> float:
    return float(np.mean(series[t - k : t]))


def festival_factors(series: Sequence[float], weeks: dict[str, set[int]], until: int) -> dict[str, float]:
    """For each festival: mean of (festival week / level of the 8 non-festival weeks before), on weeks < `until`."""
    any_fest = set().union(*weeks.values()) if weeks else set()
    out = {}
    for name, ws in weeks.items():
        ratios = []
        for w in sorted(x for x in ws if x < until):
            base = [series[x] for x in range(max(0, w - 12), w) if x not in any_fest][-8:]
            if len(base) >= 4 and np.mean(base) > 0:
                ratios.append(series[w] / np.mean(base))
        if ratios:
            out[name] = float(np.mean(ratios))
    return out


def festival_model(series: Sequence[float], t: int, weeks: dict[str, set[int]], factors: dict[str, float]) -> float:
    any_fest = set().union(*weeks.values()) if weeks else set()
    base = [series[x] for x in range(max(0, t - 12), t) if x not in any_fest][-8:]
    level = float(np.mean(base)) if base else float(series[t - 1])
    factor = max((factors.get(name, 1.0) for name, ws in weeks.items() if t in ws), default=1.0)
    return level * factor


# ---------- SPC ----------


@dataclass
class EwmaResult:
    centre: float
    sigma: float
    signals: dict[str, list[int]]  # operator -> the operator's run numbers (1-based) that signalled
    runs: dict[str, int]  # operator -> runs charted


def ewma_by_operator(
    values: Sequence[float], operators: Sequence[str], lam: float = 0.2, width: float = 3.0
) -> EwmaResult:
    """Phase I limits from the first 20 runs (moving-range sigma), then one EWMA per operator."""
    first = np.asarray(values[:20], float)
    centre = float(first.mean())
    sigma = float(np.mean(np.abs(np.diff(first))) / 1.128)
    limit = width * sigma * np.sqrt(lam / (2 - lam))
    state: dict[str, float] = {}
    count: dict[str, int] = {}
    signals: dict[str, list[int]] = {}
    for v, op in zip(values, operators, strict=True):
        z = lam * v + (1 - lam) * state.get(op, centre)
        state[op] = z
        count[op] = count.get(op, 0) + 1
        if abs(z - centre) > limit:
            signals.setdefault(op, []).append(count[op])
    return EwmaResult(centre, sigma, signals, count)


# ---------- supplier-lot quality ----------


def bootstrap_diff(
    group: Sequence[float], rest: Sequence[float], n: int = 2000, seed: int = 7
) -> tuple[float, float, float]:
    """Relative difference of means (group / rest - 1) with a 95% percentile bootstrap interval."""
    rng = np.random.default_rng(seed)
    g, r = np.asarray(group, float), np.asarray(rest, float)
    point = g.mean() / r.mean() - 1
    sims = [rng.choice(g, g.size).mean() / rng.choice(r, r.size).mean() - 1 for _ in range(n)]
    lo, hi = np.percentile(sims, [2.5, 97.5])
    return float(point), float(lo), float(hi)


# ---------- payment-delay risk ----------


def fit_logistic(
    x: np.ndarray, y: np.ndarray, steps: int = 3000, lr: float = 0.1
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu, sd = x.mean(0), x.std(0) + 1e-9
    z = np.c_[np.ones(len(x)), (x - mu) / sd]
    w = np.zeros(z.shape[1])
    for _ in range(steps):
        p = 1 / (1 + np.exp(-z @ w))
        w -= lr * z.T @ (p - y) / len(y)
    return w, mu, sd


def predict_logistic(model: tuple[np.ndarray, np.ndarray, np.ndarray], x: np.ndarray) -> np.ndarray:
    w, mu, sd = model
    z = np.c_[np.ones(len(x)), (x - mu) / sd]
    return 1 / (1 + np.exp(-z @ w))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def auc(p: np.ndarray, y: np.ndarray) -> float:
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    order = np.argsort(np.r_[pos, neg])
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))
