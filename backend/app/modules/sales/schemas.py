"""Request bodies for the sales routes (MP08). Prices arrive as decimal strings and quantities as whole-number
strings, never JSON numbers, so a float can never enter a money or quantity path (CLAUDE.md golden rules)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

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
