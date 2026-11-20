"""Explained values: every computed figure the UI shows carries its formula and sources (MASTER_PACK B.6).

MP07 builds the services that return these; MP00 only fixes the shape.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class SourceRef:
    type: str  # e.g. "production_run", "purchase_receipt", "oracle"
    id: str


@dataclass(frozen=True)
class ExplainedInput:
    label: str
    value: Decimal
    unit: str
    source: SourceRef | None = None


@dataclass(frozen=True)
class Explained:
    value: Decimal
    unit: str  # "INR", "INR/packet", "kg", "%"
    formula: str  # "run_cost / good_packets"
    inputs: tuple[ExplainedInput, ...] = field(default_factory=tuple)
    method: str | None = None  # "WAC", "flexible standard", ...

    def to_json(self) -> dict[str, Any]:
        """Serialise with Decimals as strings so no float ever reaches the client."""
        return {
            "value": str(self.value),
            "unit": self.unit,
            "formula": self.formula,
            "method": self.method,
            "inputs": [
                {
                    "label": i.label,
                    "value": str(i.value),
                    "unit": i.unit,
                    "source": None if i.source is None else {"type": i.source.type, "id": i.source.id},
                }
                for i in self.inputs
            ],
        }
