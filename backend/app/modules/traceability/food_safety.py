"""Oil log (RUCO) and fill weights (MP13, T6, ADR-0020). Reads what batch completion recorded; writes nothing.

The thresholds are effective-dated DEMO settings, never hard-coded: `fssai.ruco_threshold_l_per_day` (daily records
are required above it), `fssai.tpc_limit_pct` (oil above it must be discarded) and
`legal_metrology.short_fill_tolerance_g` (declared net in grams -> the tolerated shortfall in grams). The tolerance
values must be verified with a Legal Metrology officer before real use.
"""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.calendar import business_date
from app.core.errors import DomainError
from app.modules.production import service as production
from app.modules.traceability import domain
from app.modules.traceability.domain import OilUse
from app.modules.uom.domain import normalise

RUCO_THRESHOLD: Final = "fssai.ruco_threshold_l_per_day"
TPC_LIMIT: Final = "fssai.tpc_limit_pct"
SHORT_FILL_TOLERANCE: Final = "legal_metrology.short_fill_tolerance_g"
VERIFY_NOTE: Final = "DEMO values: verify the tolerance table with a Legal Metrology officer before real use."


class FoodSafetyError(DomainError):
    pass


def _range(days: int, on: date | None) -> tuple[date, date]:
    if days < 1 or days > 366:
        raise FoodSafetyError("bad_days", "days must be between 1 and 366")
    to = on or business_date()
    return to - timedelta(days=days - 1), to


def _required_decimal(session: Session, key: str, on: date) -> Decimal:
    value = effective_settings.decimal_on(session, key, on)
    if value is None:
        raise FoodSafetyError("setting_missing", f"the setting {key} is not configured", {"key": key})
    return value


def tolerance_table(session: Session, on: date) -> dict[Decimal, Decimal]:
    """Declared net (g) -> tolerated shortfall (g), from the effective-dated setting (empty when not set)."""
    raw = effective_settings.value_on(session, SHORT_FILL_TOLERANCE, on)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise FoodSafetyError("setting_not_a_table", f"{SHORT_FILL_TOLERANCE} must map net grams to grams")
    try:
        return {Decimal(k): Decimal(v) for k, v in raw.items() if k != "note"}
    except (InvalidOperation, TypeError) as exc:
        raise FoodSafetyError(
            "setting_not_a_table", f"{SHORT_FILL_TOLERANCE} holds a value that is not a decimal"
        ) from exc


def oil_log(session: Session, days: int = 30, on: date | None = None) -> dict[str, Any]:
    """Oil used per day (fresh + top-ups) against the RUCO threshold, and every session's TPC against the limit."""
    frm, to = _range(days, on)
    threshold = _required_decimal(session, RUCO_THRESHOLD, to)
    tpc_limit = _required_decimal(session, TPC_LIMIT, to)
    by_day: dict[date, list[production.OilRecord]] = {}
    for r in production.oil_records(session, frm, to):
        by_day.setdefault(r.run_date, []).append(r)
    out_days = []
    for day in sorted(by_day, reverse=True):
        recs = by_day[day]
        d = domain.oil_day(day, [OilUse(str(r.run_id), r.run_no, r.fresh_ml, r.topup_ml) for r in recs], threshold)
        out_days.append(
            {
                "date": day.isoformat(),
                "litres": d.litres.to_json(),
                "above_threshold": d.above_threshold,
                "sessions": [
                    {
                        "run_id": str(r.run_id),
                        "run_no": r.run_no,
                        "fresh_l": str(normalise(r.fresh_ml / domain.ML_PER_L)),
                        "topup_l": str(normalise(r.topup_ml / domain.ML_PER_L)),
                        "discard_l": str(normalise(r.discard_ml / domain.ML_PER_L)),
                        "tpc_pct": None if r.tpc_pct is None else str(normalise(r.tpc_pct)),
                        "discard_oil": domain.tpc_discard(r.tpc_pct, tpc_limit),
                    }
                    for r in recs
                ],
            }
        )
    return {
        "date_from": frm.isoformat(),
        "date_to": to.isoformat(),
        "threshold_l_per_day": str(normalise(threshold)),
        "tpc_limit_pct": str(normalise(tpc_limit)),
        "records_required": any(d["above_threshold"] for d in out_days),
        "days": out_days,
        "note": (
            f"DEMO settings: daily used-oil records are required above {normalise(threshold)} L a day; oil with total"
            f" polar compounds above {normalise(tpc_limit)}% must be discarded."
        ),
    }


def fill_weights(session: Session, days: int = 30, on: date | None = None) -> dict[str, Any]:
    """Per batch with samples: mean net, grams over declared, the giveaway in rupees, and short-filled samples."""
    frm, to = _range(days, on)
    table = tolerance_table(session, to)
    runs = []
    for r in production.fill_records(session, frm, to):
        tol = table.get(r.declared_net_g)
        c = domain.fill_check(
            run_id=str(r.run_id),
            run_no=r.run_no,
            declared_g=r.declared_net_g,
            nets=r.sample_nets,
            good_units=r.good_units,
            ingredient_value=r.ingredient_value,
            expected_bulk_g=r.expected_bulk_g,
            tolerance_g=tol,
        )
        runs.append(
            {
                "run_id": str(r.run_id),
                "run_no": r.run_no,
                "run_date": r.run_date.isoformat(),
                "pack_code": r.pack_code,
                "declared_g": str(normalise(r.declared_net_g)),
                "good_units": str(r.good_units),
                "samples": [str(normalise(n)) for n in r.sample_nets],
                "mean_net": c.mean_net.to_json(),
                "over_per_packet": c.over_per_packet.to_json(),
                "cost_per_kg": c.cost_per_kg.to_json(),
                "giveaway": c.giveaway.to_json(),
                "tolerance_g": None if tol is None else str(normalise(tol)),
                "short_limit_g": None if c.short_limit_g is None else str(normalise(c.short_limit_g)),
                "short_samples": [str(normalise(n)) for n in c.short],
                "short_fill_alert": bool(c.short),
            }
        )
    runs.reverse()  # newest first
    return {
        "date_from": frm.isoformat(),
        "date_to": to.isoformat(),
        "tolerances": [
            {"declared_g": str(normalise(k)), "tolerance_g": str(normalise(v))} for k, v in sorted(table.items())
        ],
        "runs": runs,
        "note": VERIFY_NOTE,
    }
