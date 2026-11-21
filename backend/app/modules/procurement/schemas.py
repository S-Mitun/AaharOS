"""Request bodies for the purchase routes. Quantities, rates and money arrive as decimal **strings** ("60", "45.00"),
never JSON numbers, so a float can never enter a money or quantity path (CLAUDE.md golden rules)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DecimalText = Annotated[str, StringConstraints(pattern=r"^\d{1,12}(\.\d{1,6})?$")]


class ReceiptLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    qty: DecimalText
    unit: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    rate: DecimalText
    freight: DecimalText = "0"
    rejected_qty: DecimalText = "0"
    lot_no: Annotated[str, StringConstraints(max_length=64)] | None = None
    mfg_date: date | None = None
    best_before: date | None = None

    def decimals(self) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        return Decimal(self.qty), Decimal(self.rate), Decimal(self.freight), Decimal(self.rejected_qty)


class ReceiptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: uuid.UUID
    supplier_invoice_ref: Annotated[str, StringConstraints(max_length=64)] | None = None
    received_on: date
    lines: Annotated[list[ReceiptLineBody], Field(min_length=1, max_length=200)]


class ReverseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
