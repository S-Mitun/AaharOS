"""Request bodies for billing (MP10). Amounts arrive as decimal strings, quantities as whole-number strings."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

RupeesText = Annotated[str, StringConstraints(pattern=r"^\d{1,10}(\.\d{1,2})?$")]
PacketsText = Annotated[str, StringConstraints(pattern=r"^[1-9]\d{0,6}$")]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class InvoiceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_date: date | None = None


class ReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class CreditLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_no: Annotated[int, Field(ge=1, le=200)]
    qty: PacketsText
    rate: RupeesText  # rupees per packet credited, ex-tax


class CreditNoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason
    note_date: date | None = None
    lines: Annotated[list[CreditLineBody], Field(min_length=1, max_length=200)]
