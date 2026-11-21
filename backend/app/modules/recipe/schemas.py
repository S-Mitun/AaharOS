"""Request bodies for the recipe and pack-spec routes. Quantities arrive as decimal **strings** ("40", "0.05"), never
JSON numbers, so a float can never enter a quantity path (CLAUDE.md golden rules)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DecimalText = Annotated[str, StringConstraints(pattern=r"^\d{1,12}(\.\d{1,6})?$")]
PctText = Annotated[str, StringConstraints(pattern=r"^\d{1,3}(\.\d{1,4})?$")]
WholeText = Annotated[str, StringConstraints(pattern=r"^[1-9]\d{0,5}$")]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


def _pct(text: str | None) -> Decimal | None:
    return None if text is None else Decimal(text)


class RecipeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Code
    name: Name
    bulk_item_id: uuid.UUID


class RecipeLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    qty: DecimalText
    unit: Annotated[str, StringConstraints(min_length=1, max_length=16)]
    tolerance_pct: PctText | None = None

    def tolerance(self) -> Decimal | None:
        return _pct(self.tolerance_pct)


class RecipeVersionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bulk_yield_g: DecimalText
    effective_from: date
    lines: Annotated[list[RecipeLineBody], Field(min_length=1, max_length=100)]


class PackSpecBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Code
    name: Name
    recipe_id: uuid.UUID
    fg_item_id: uuid.UUID


class PackLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    qty_per_good_unit: DecimalText
    tolerance_pct: PctText | None = None

    def tolerance(self) -> Decimal | None:
        return _pct(self.tolerance_pct)


class PackSpecVersionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    net_g: DecimalText
    units_per_carton: WholeText
    shelf_life_days: WholeText
    effective_from: date
    lines: Annotated[list[PackLineBody], Field(min_length=1, max_length=50)]
