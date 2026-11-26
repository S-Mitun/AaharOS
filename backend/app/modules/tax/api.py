"""Tax routes (MP10): read the GST rules, and add one (a new effective-dated rule, never an edit)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.db import get_session
from app.core.errors import NotFoundError
from app.modules.identity.service import Principal, require
from app.modules.tax import service

router = APIRouter(prefix="/api", tags=["tax"])
DbSession = Annotated[Session, Depends(get_session)]


class RuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hsn: Annotated[str, StringConstraints(pattern=r"^\d{4,8}$")]
    rate_pct: Annotated[str, StringConstraints(pattern=r"^\d{1,3}(\.\d{1,2})?$")]
    effective_from: date
    effective_to: date | None = None
    note: Annotated[str, StringConstraints(max_length=300)] | None = None


def _rules(session: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": str(r.id),
            "hsn": r.hsn,
            "rate_pct": str(r.rate_pct.normalize()),
            "effective_from": r.effective_from.isoformat(),
            "effective_to": None if r.effective_to is None else r.effective_to.isoformat(),
        }
        for r in service.rules(session)
    ]


@router.get("/tax/rules")
def rules(_principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession) -> dict[str, Any]:
    return {"rules": _rules(session)}


@router.post("/tax/rules", status_code=status.HTTP_201_CREATED)
def add_rule(
    body: RuleBody, principal: Annotated[Principal, Depends(require("settings.manage"))], session: DbSession
) -> dict[str, Any]:
    service.create_rule(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        hsn=body.hsn,
        rate_pct=Decimal(body.rate_pct),
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        note=body.note,
    )
    session.commit()
    return {"rules": _rules(session)}


# MP19 (live changes): the decimal settings a manager may change from the API, each effective-dated. A new value
# supersedes the open-ended one before it; batches already started keep the value frozen in their snapshot.
CHANGEABLE_SETTINGS = frozenset(
    {
        "variance_tolerance_pct",
        "freshness.alert_days",
        "fssai.ruco_threshold_l_per_day",
        "fssai.tpc_limit_pct",
        "planning.attribution_days",
        "planning.batches_per_day",
        "gst.b2cl_threshold",
        "eway.threshold_interstate",
        "eway.threshold_intrastate",
        "bank.stock_margin_pct",
        "bank.debtors_margin_pct",
        "transport.road_factor",
        "transport.fuel_inr_per_l",
        "transport.co2_kg_per_km",
        "transport.credit_cost_pct_pa",
        "transport.backhaul_detour_km",
    }
)


# What each changeable setting means, in the words the Settings screen shows (same keys as above, in screen order).
SETTING_LABELS: dict[str, tuple[str, str]] = {
    "variance_tolerance_pct": ("Variance flag above", "%"),
    "freshness.alert_days": ("Freshness alert after", "days"),
    "fssai.ruco_threshold_l_per_day": ("Used-oil (RUCO) threshold", "L/day"),
    "fssai.tpc_limit_pct": ("Frying oil TPC limit", "%"),
    "planning.attribution_days": ("Shortage look-back", "days"),
    "planning.batches_per_day": ("Batches per day", "batches"),
    "gst.b2cl_threshold": ("GSTR-1 B2CL threshold", "INR"),
    "eway.threshold_interstate": ("E-way bill threshold, interstate", "INR"),
    "eway.threshold_intrastate": ("E-way bill threshold, within the state", "INR"),
    "bank.stock_margin_pct": ("Bank margin on stock", "%"),
    "bank.debtors_margin_pct": ("Bank margin on debtors", "%"),
    "transport.road_factor": ("Road distance factor", "times straight line"),
    "transport.fuel_inr_per_l": ("Diesel price", "INR/L"),
    "transport.co2_kg_per_km": ("CO₂ per km", "kg/km"),
    "transport.credit_cost_pct_pa": ("Cost of credit", "% a year"),
    "transport.backhaul_detour_km": ("Backhaul detour allowed", "km"),
}


class SettingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Annotated[str, StringConstraints(pattern=r"^\d{1,12}(\.\d{1,6})?$")]
    effective_from: date


def _known(key: str) -> None:
    if key not in CHANGEABLE_SETTINGS:
        raise NotFoundError("setting_not_changeable", f"{key} is not a setting that can be changed here")


@router.get("/settings")
def list_settings(
    _principal: Annotated[Principal, Depends(require("report.read"))], session: DbSession
) -> dict[str, Any]:
    """Every changeable setting with the value in force today (None when the factory has not set it)."""
    today = date.today()
    return {
        "on": today.isoformat(),
        "settings": [
            {"key": key, "label": label, "unit": unit, "value": effective_settings.value_on(session, key, today)}
            for key, (label, unit) in SETTING_LABELS.items()
        ],
    }


@router.get("/settings/{key}")
def read_setting(
    key: str,
    _principal: Annotated[Principal, Depends(require("report.read"))],
    session: DbSession,
    on: date | None = None,
) -> dict[str, Any]:
    _known(key)
    day = on or date.today()
    value = effective_settings.value_on(session, key, day)
    return {"key": key, "on": day.isoformat(), "value": value}


@router.put("/settings/{key}")
def change_setting(
    key: str,
    body: SettingBody,
    principal: Annotated[Principal, Depends(require("settings.manage"))],
    session: DbSession,
) -> dict[str, Any]:
    _known(key)
    service.put_setting(
        session,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        key=key,
        value=Decimal(body.value),
        effective_from=body.effective_from,
    )
    session.commit()
    return {"key": key, "value": body.value, "effective_from": body.effective_from.isoformat()}
