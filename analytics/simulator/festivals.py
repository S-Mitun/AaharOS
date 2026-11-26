"""Festival dates for the simulator and the forecast (config, never hard-coded in a model).

Sources: Government of Tamil Nadu, Karnataka and Kerala public-holiday lists for 2023-2025 (Deepavali / Naraka
Chaturdashi, Thai Pongal, Thiruvonam). Dates are the main festival day; the uplift covers that week and the week before.
"""

from datetime import date, timedelta

FESTIVALS: tuple[tuple[str, date, tuple[str, ...]], ...] = (
    ("Deepavali", date(2023, 11, 12), ("TN", "KA")),
    ("Pongal", date(2024, 1, 15), ("TN",)),
    ("Onam", date(2024, 9, 15), ("KL",)),
    ("Deepavali", date(2024, 10, 31), ("TN", "KA")),
    ("Pongal", date(2025, 1, 14), ("TN",)),
    ("Onam", date(2025, 9, 5), ("KL",)),
    ("Deepavali", date(2025, 10, 20), ("TN", "KA")),
)


def festival_weeks(start: date, weeks: int) -> list[tuple[str, tuple[str, ...], set[int]]]:
    """(festival, states, week numbers from `start`) for every festival in range: its week and the week before."""
    out = []
    for name, day, states in FESTIVALS:
        week = (day - start).days // 7
        hit = {w for w in (week - 1, week) if 0 <= w < weeks}
        if hit:
            out.append((name, states, hit))
    return out


def week_of(start: date, day: date) -> int:
    return (day - start).days // 7


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())
