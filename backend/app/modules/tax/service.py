"""Tax use cases (MP10, ADR-0017): effective-dated GST rules by HSN, invoice tax computation, and the business
profile (GSTIN, FSSAI, Udyam, address, e-way threshold) as effective-dated settings. Other modules call only this
file. Functions run in the caller's transaction and never commit."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import insert, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.errors import DomainError
from app.core.pg_errors import domain_error_from_db
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.tax import domain
from app.modules.tax.domain import LineTax, Rule, Totals
from app.modules.tax.models import TaxRule

# J5: the business identity printed on invoices, and tax thresholds, are effective-dated settings (never hard-coded).
PROFILE_KEYS: Final = {
    "gstin": "org.gstin",
    "fssai_no": "org.fssai_no",
    "udyam_no": "org.udyam_no",
    "address": "org.address",
    "upi_vpa": "org.upi_vpa",
}
EWAY_THRESHOLDS: Final = {"INTER": "eway.threshold_interstate", "INTRA": "eway.threshold_intrastate"}
ROUND_TO_RUPEE: Final = "invoice.round_to_rupee"


def create_rule(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    hsn: str,
    rate_pct: Decimal,
    effective_from: date,
    effective_to: date | None = None,
    note: str | None = None,
) -> uuid.UUID:
    rule_id = uuid.uuid4()
    try:
        with session.begin_nested():
            session.execute(
                insert(TaxRule).values(
                    id=rule_id,
                    organization_id=organization_id,
                    hsn=hsn,
                    rate_pct=rate_pct,
                    effective_from=effective_from,
                    effective_to=effective_to,
                    note=note,
                    created_by=actor_id,
                )
            )
    except DBAPIError as exc:
        err = domain_error_from_db(exc)
        if err is None:
            raise
        raise DomainError("tax_rule_overlaps", "a GST rule for this HSN already covers part of those dates") from exc
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="tax_rule.create",
        entity_type="tax_rule",
        entity_id=rule_id,
        after={"hsn": hsn, "rate_pct": rate_pct, "effective_from": effective_from, "effective_to": effective_to},
        note=note,
    )
    return rule_id


def rules(session: Session) -> list[Rule]:
    return [
        Rule(r.id, r.hsn, r.rate_pct, r.effective_from, r.effective_to)
        for r in session.execute(select(TaxRule).order_by(TaxRule.hsn, TaxRule.effective_from)).scalars()
    ]


@dataclass(frozen=True)
class TaxedLineIn:
    line_no: int
    item_id: uuid.UUID
    qty: int
    rate: Decimal


@dataclass(frozen=True)
class Computed:
    regime: str
    lines: list[LineTax]
    hsn: dict[int, str]
    totals: Totals


def compute(
    session: Session,
    *,
    supplier_state: str,
    place_of_supply: str,
    on: date,
    lines: Sequence[TaxedLineIn],
) -> Computed:
    """Tax for a set of lines on a date: the rule in force for each item's HSN, per-line rounding, the header."""
    kind = domain.regime(supplier_state, place_of_supply)
    hsn = catalog.hsn_for(session, {ln.item_id for ln in lines})
    all_rules = rules(session)
    out: list[LineTax] = []
    for ln in lines:
        rule = domain.rule_on(all_rules, hsn.get(ln.item_id), on)
        out.append(domain.tax_line(ln.line_no, ln.qty, ln.rate, rule.rate_pct, kind, rule.id))
    round_flag = effective_settings.value_on(session, ROUND_TO_RUPEE, on)
    return Computed(
        regime=kind,
        lines=out,
        hsn={ln.line_no: hsn[ln.item_id] or "" for ln in lines},
        totals=domain.totals(out, round_to_rupee=str(round_flag).lower() == "true"),
    )


def profile(session: Session, on: date) -> dict[str, Any]:
    """The business identity in force on a date (DEMO values in the seeds). Missing keys are None, never invented."""
    return {name: effective_settings.value_on(session, key, on) for name, key in PROFILE_KEYS.items()}


def eway_verdict(session: Session, kind: str, consignment_value: Decimal, on: date) -> domain.EwayVerdict:
    value = effective_settings.decimal_on(session, EWAY_THRESHOLDS[kind], on)
    if value is None:
        raise DomainError("eway_threshold_missing", "the e-way bill threshold is not configured for this date")
    return domain.eway_check(kind, consignment_value, value)


def put_setting(
    session: Session,
    *,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    key: str,
    value: Any,
    effective_from: date,
) -> uuid.UUID:
    setting_id = effective_settings.put(
        session, organization_id=organization_id, actor_id=actor_id, key=key, value=value, effective_from=effective_from
    )
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="settings.put",
        entity_type="setting",
        entity_id=setting_id,
        after={"key": key, "value": value, "effective_from": effective_from},
    )
    return setting_id
