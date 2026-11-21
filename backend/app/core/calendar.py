"""Business dates: the factory's day (IST) and the Indian financial year (April to March)."""

from datetime import UTC, date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def business_date() -> date:
    """Today in the factory's time zone (India has no daylight saving, so a fixed offset is exact)."""
    return datetime.now(UTC).astimezone(IST).date()


def financial_year(d: date) -> str:
    """'26-27' for any date from 1 April 2026 to 31 March 2027 (the format `number_sequences.fy` checks)."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"
