"""Request bodies for the run routes. Quantities and masses arrive as decimal **strings** ("10.5", "40000"), never JSON
numbers, so a float can never enter a quantity path (CLAUDE.md golden rules). Good units are whole-number strings."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DecimalText = Annotated[str, StringConstraints(pattern=r"^\d{1,12}(\.\d{1,6})?$")]
PctText = Annotated[str, StringConstraints(pattern=r"^\d{1,3}(\.\d{1,4})?$")]
CountText = Annotated[str, StringConstraints(pattern=r"^\d{1,9}$")]
Unit = Annotated[str, StringConstraints(min_length=1, max_length=16)]


class RunPackLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_spec_version_id: uuid.UUID
    bulk_allocated_g: DecimalText | None = None  # optional with a single pack line: all the expected bulk


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_version_id: uuid.UUID
    batch_multiplier: DecimalText = "1"
    run_date: date
    pack_lines: Annotated[list[RunPackLineBody], Field(min_length=1, max_length=26)]


class IssueLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    qty: DecimalText
    unit: Unit


class IssueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Literal["ISSUE", "RETURN"] = "ISSUE"
    posting_date: date | None = None
    lines: Annotated[list[IssueLineBody], Field(min_length=1, max_length=100)]


class PackagingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    used: DecimalText  # taken from the packaging store, damaged included
    damaged: DecimalText = "0"
    unit: Unit = "piece"


class PackResultBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_line_id: uuid.UUID
    good_units: CountText
    packaging: Annotated[list[PackagingBody], Field(max_length=50)] = []


class SampleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gross_g: DecimalText
    net_g: DecimalText
    sampled_at: datetime | None = None


class OilBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fresh_ml: DecimalText
    topup_ml: DecimalText = "0"
    discard_ml: DecimalText = "0"
    tpc_pct: PctText | None = None


class CompleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    posting_date: date | None = None
    pack_lines: Annotated[list[PackResultBody], Field(min_length=1, max_length=26)]
    scrap_g: DecimalText = "0"
    loss_g: DecimalText = "0"
    scrap_reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    fill_weight_samples: Annotated[list[SampleBody], Field(max_length=200)] = []
    oil_session: OilBody | None = None

    def masses(self) -> tuple[Decimal, Decimal]:
        return Decimal(self.scrap_g), Decimal(self.loss_g)
