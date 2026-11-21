"""Request bodies for the sales routes (MP08). Prices arrive as decimal strings and quantities as whole-number
strings, never JSON numbers, so a float can never enter a money or quantity path (CLAUDE.md golden rules)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

PriceText = Annotated[str, StringConstraints(pattern=r"^\d{1,10}(\.\d{1,2})?$")]
PacketsText = Annotated[str, StringConstraints(pattern=r"^[1-9]\d{0,6}$")]


class OrderLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    qty: PacketsText  # whole packets
    price_ex_tax: PriceText  # as the phone showed it; checked against the price list version


class OrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    price_list_id: uuid.UUID
    captured_at: datetime | None = None  # when the order was saved on the phone
    lines: Annotated[list[OrderLineBody], Field(min_length=1, max_length=100)]


class PriceListItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    price_ex_tax: PriceText


class PriceListBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
    customer_id: uuid.UUID | None = None
    effective_from: date
    items: Annotated[list[PriceListItemBody], Field(min_length=1, max_length=500)]

    def prices(self) -> dict[uuid.UUID, Decimal]:
        return {i.item_id: Decimal(i.price_ex_tax) for i in self.items}


class AgreedLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_no: Annotated[int, Field(ge=1, le=100)]
    qty: Annotated[str, StringConstraints(pattern=r"^\d{1,7}$")]  # whole packets, may be 0 for a line


class ApproveBody(BaseModel):
    """MP09: approve in full (default) or partially; optional lower agreed quantities (with a reason), the price
    choice for a stale order, and a reason to approve over the credit limit."""

    model_config = ConfigDict(extra="forbid")

    partial: bool = False
    agreed: Annotated[list[AgreedLineBody], Field(max_length=100)] = []
    amend_reason: Annotated[str, StringConstraints(max_length=500)] | None = None
    stale_price: Literal["captured", "current"] | None = None
    credit_override_reason: Annotated[str, StringConstraints(max_length=500)] | None = None


class ReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class AmendBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_no: Annotated[int, Field(ge=1, le=100)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
    price_ex_tax: PriceText | None = None
    qty: Annotated[str, StringConstraints(pattern=r"^\d{1,7}$")] | None = None
