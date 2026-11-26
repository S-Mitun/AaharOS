"""Pure GST rules (MP10, ADR-0017). No database.

- J1 Regime: supplier state = place of supply -> CGST + SGST (each half the rate), else IGST (the whole rate).
- Tax is computed per invoice line, ROUND_HALF_UP to paise, per tax head. CGST and SGST are each
  round(taxable x rate/2 / 100), so the two halves are always equal. The header is the sum of the lines.
- An optional round-off line takes the total to the nearest rupee (a setting, off by default).
- The rate comes from an effective-dated rule for the line's HSN on the invoice date; no rate is hard-coded here.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from app.core.errors import DomainError
from app.core.money import round_money

HUNDRED: Final = Decimal(100)
TWO: Final = Decimal(2)

# GST state codes (reference data of the GST system, not tax rates). Used for the place of supply on documents.
STATE_NAMES: Final[dict[str, str]] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
}


class TaxError(DomainError):
    """A tax computation the rules refuse."""


def state_label(code: str) -> str:
    return f"{code}-{STATE_NAMES.get(code, 'Unknown state')}"


def regime(supplier_state: str, place_of_supply: str) -> str:
    """INTRA (CGST + SGST) when the supply stays in the supplier's state, else INTER (IGST)."""
    return "INTRA" if supplier_state == place_of_supply else "INTER"


@dataclass(frozen=True)
class Rule:
    id: uuid.UUID
    hsn: str
    rate_pct: Decimal
    effective_from: date
    effective_to: date | None

    def in_force_on(self, on: date) -> bool:
        return self.effective_from <= on and (self.effective_to is None or on <= self.effective_to)


def rule_on(rules: Sequence[Rule], hsn: str | None, on: date) -> Rule:
    if not hsn:
        raise TaxError("hsn_missing", "this product has no HSN code: set it before invoicing")
    found = [r for r in rules if r.hsn == hsn and r.in_force_on(on)]
    if not found:
        raise TaxError("no_tax_rule", f"no GST rule is in force for HSN {hsn} on {on.isoformat()}", {"hsn": hsn})
    return max(found, key=lambda r: r.effective_from)


@dataclass(frozen=True)
class TaxAmount:
    tax: str  # CGST, SGST or IGST
    rate_pct: Decimal
    amount: Decimal


@dataclass(frozen=True)
class LineTax:
    line_no: int
    qty: int
    rate: Decimal  # rupees per unit, ex-tax
    taxable: Decimal
    gst_rate_pct: Decimal
    taxes: tuple[TaxAmount, ...]
    rule_id: uuid.UUID | None = None

    @property
    def tax_total(self) -> Decimal:
        return sum((t.amount for t in self.taxes), Decimal(0))


def line_taxable(qty: int, rate: Decimal) -> Decimal:
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        raise TaxError("qty_not_positive", "an invoice line needs a positive whole quantity")
    if not isinstance(rate, Decimal) or rate < 0:
        raise TaxError("bad_rate", "a rate is a non-negative Decimal")
    return round_money(rate * qty)


def tax_line(
    line_no: int, qty: int, rate: Decimal, gst_rate_pct: Decimal, kind: str, rule_id: uuid.UUID | None = None
) -> LineTax:
    """One line's taxable value and its tax heads, each rounded half up to paise."""
    if not isinstance(gst_rate_pct, Decimal) or gst_rate_pct < 0 or gst_rate_pct > HUNDRED:
        raise TaxError("bad_gst_rate", "a GST rate is a Decimal percentage from 0 to 100")
    taxable = line_taxable(qty, rate)
    if kind == "INTRA":
        half = gst_rate_pct / TWO
        amount = round_money(taxable * half / HUNDRED)
        taxes: tuple[TaxAmount, ...] = (TaxAmount("CGST", half, amount), TaxAmount("SGST", half, amount))
    elif kind == "INTER":
        taxes = (TaxAmount("IGST", gst_rate_pct, round_money(taxable * gst_rate_pct / HUNDRED)),)
    else:
        raise TaxError("bad_regime", "regime is INTRA or INTER")
    return LineTax(line_no, qty, rate, taxable, gst_rate_pct, taxes, rule_id)


@dataclass(frozen=True)
class Totals:
    taxable: Decimal
    tax_total: Decimal
    round_off: Decimal
    total: Decimal
    by_tax: dict[str, Decimal]


def totals(lines: Sequence[LineTax], round_to_rupee: bool = False) -> Totals:
    """Header = Σ lines (exactly). With round_to_rupee the total goes to the nearest rupee, half up, and the
    difference is an explicit round-off line (never silent)."""
    if not lines:
        raise TaxError("empty_invoice", "an invoice needs at least one line")
    taxable = sum((ln.taxable for ln in lines), Decimal(0))
    by_tax: dict[str, Decimal] = {}
    for ln in lines:
        for t in ln.taxes:
            by_tax[t.tax] = by_tax.get(t.tax, Decimal(0)) + t.amount
    tax_total = sum(by_tax.values(), Decimal(0))
    raw = taxable + tax_total
    rounded = raw.quantize(Decimal(1), rounding=ROUND_HALF_UP) if round_to_rupee else raw
    round_off = round_money(rounded - raw)
    return Totals(taxable, tax_total, round_off, raw + round_off, by_tax)


_ONES = (
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
)
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _below_thousand(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(f"{_ONES[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        parts.append(_TENS[n // 10] + (f" {_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        parts.append(_ONES[n])
    return " ".join(parts)


def _indian_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    for size, name in ((10_000_000, "Crore"), (100_000, "Lakh"), (1_000, "Thousand")):
        if n >= size:
            head = n // size
            parts.append(f"{_indian_words(head) if head >= 1000 else _below_thousand(head)} {name}")
            n %= size
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def amount_in_words(amount: Decimal) -> str:
    """Indian numbering: 7875.00 -> 'Rupees Seven Thousand Eight Hundred Seventy Five Only';
    1,23,456.50 -> 'Rupees One Lakh Twenty Three Thousand Four Hundred Fifty Six and Fifty Paise Only'."""
    value = round_money(amount)
    if value < 0:
        raise TaxError("negative_amount", "an amount in words is for non-negative amounts")
    rupees = int(value)
    paise = int((value - rupees) * 100)
    words = f"Rupees {_indian_words(rupees)}"
    if paise:
        words += f" and {_indian_words(paise)} Paise"
    return words + " Only"


@dataclass(frozen=True)
class EwayVerdict:
    required: bool
    reason: str
    consignment_value: Decimal
    threshold: Decimal


def eway_check(kind: str, consignment_value: Decimal, threshold: Decimal) -> EwayVerdict:
    """J7 (Rule 138, mock only): an e-way bill is required when the consignment value, tax included, is above the
    threshold in force for the movement (inter- or intra-state, both effective-dated settings)."""
    where = "to another state" if kind == "INTER" else "within the state"
    value = round_money(consignment_value)
    if value > threshold:
        reason = f"Needed: a delivery {where} worth ₹{value:,.2f} is above the ₹{threshold:,.2f} limit (Rule 138)"
        return EwayVerdict(True, reason, value, threshold)
    reason = f"Not needed: a delivery {where} worth ₹{value:,.2f} is not above the ₹{threshold:,.2f} limit (Rule 138)"
    return EwayVerdict(False, reason, value, threshold)
