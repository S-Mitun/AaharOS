"""Pure billing rules (MP10, ADR-0017). No database.

- J2 An invoice covers approved packets not yet invoiced, at the order line's price (amended if it was).
  Numbers: `AHR/26-27/000001` (16 characters at most, the GST limit), gapless per financial year.
- J3 A credit note reduces an invoice line's taxable value (price errors, discounts, short supply); its tax is
  reversed at the invoice line's own tax heads and rates, rounded half up per head. It never exceeds what is left of
  the line. Numbers: `CN/26-27/000001`.
- J8 Due date: invoice date + the customer's payment terms; under MSME terms at most 45 days (15 when no term is
  agreed), MSMED Act s.15.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Final

from app.core.errors import DomainError
from app.core.money import round_money

INVOICE_DOC: Final = "INV"
CREDIT_NOTE_DOC: Final = "CN"
MSME_MAX_DAYS: Final = 45
MSME_DEFAULT_DAYS: Final = 15


class BillingError(DomainError):
    """An invoice or credit note the books refuse."""


def invoice_no(fy: str, number: int) -> str:
    if number < 1:
        raise ValueError("document numbers start at 1")
    no = f"AHR/{fy}/{number:06d}"
    if len(no) > 16:
        raise BillingError("invoice_no_too_long", "invoice numbers are at most 16 characters")
    return no


def credit_note_no(fy: str, number: int) -> str:
    if number < 1:
        raise ValueError("document numbers start at 1")
    return f"CN/{fy}/{number:06d}"


def to_invoice(approved: Mapping[uuid.UUID, int], invoiced: Mapping[uuid.UUID, int]) -> dict[uuid.UUID, int]:
    """Packets per item still to invoice: approved - already invoiced (never negative). Refused when none."""
    out = {item: qty - invoiced.get(item, 0) for item, qty in approved.items() if qty - invoiced.get(item, 0) > 0}
    if not out:
        raise BillingError("nothing_to_invoice", "every approved packet of this order is already invoiced")
    return out


def due_date(invoice_date: date, terms_days: int, msme: bool) -> date:
    days = max(0, terms_days)
    if msme:
        days = min(days, MSME_MAX_DAYS) if days else MSME_DEFAULT_DAYS
    return invoice_date + timedelta(days=days)


@dataclass(frozen=True)
class InvoiceLineTaxes:
    line_no: int
    taxable: Decimal
    credited_taxable: Decimal  # by earlier credit notes
    taxes: tuple[tuple[str, Decimal], ...]  # (tax head, rate %)


@dataclass(frozen=True)
class CreditLineIn:
    line_no: int  # the invoice line it reduces
    qty: int
    rate: Decimal  # rupees per packet credited, ex-tax


@dataclass(frozen=True)
class CreditLinePlan:
    line_no: int
    invoice_line_no: int
    qty: int
    rate: Decimal
    taxable: Decimal
    taxes: tuple[tuple[str, Decimal, Decimal], ...]  # (head, rate %, amount)


def plan_credit_note(
    lines: Sequence[CreditLineIn], invoice_lines: Mapping[int, InvoiceLineTaxes]
) -> list[CreditLinePlan]:
    if not lines:
        raise BillingError("empty_credit_note", "a credit note needs at least one line")
    plan = []
    seen: set[int] = set()
    for n, ln in enumerate(lines, start=1):
        inv = invoice_lines.get(ln.line_no)
        if inv is None:
            raise BillingError("unknown_invoice_line", "no such line on the invoice", {"line_no": ln.line_no})
        if ln.line_no in seen:
            raise BillingError("duplicate_line", "each invoice line once per credit note")
        seen.add(ln.line_no)
        if isinstance(ln.qty, bool) or not isinstance(ln.qty, int) or ln.qty <= 0:
            raise BillingError("qty_not_positive", "a credit note line needs a positive whole quantity")
        if not isinstance(ln.rate, Decimal) or ln.rate <= 0 or ln.rate != round_money(ln.rate):
            raise BillingError("bad_rate", "a credit rate is a positive rupee amount with at most two decimals")
        taxable = round_money(ln.rate * ln.qty)
        left = inv.taxable - inv.credited_taxable
        if taxable > left:
            raise BillingError(
                "credit_exceeds_invoice_line",
                f"only {left} of this line's taxable value is left to credit",
                {"line_no": ln.line_no, "left": str(left), "asked": str(taxable)},
            )
        taxes = tuple((head, rate, round_money(taxable * rate / Decimal(100))) for head, rate in inv.taxes)
        plan.append(CreditLinePlan(n, ln.line_no, ln.qty, ln.rate, taxable, taxes))
    return plan
