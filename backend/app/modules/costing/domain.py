"""Pure costing rules. MP05 pulls one piece forward from MP07: the standard cost per unit (decision D3), because the
opening finished-goods lot is valued at standard (assumption A1). MP07 adds run cost, variances and the waterfall.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.core.errors import DomainError
from app.core.money import round_unit_cost
from app.modules.valuation.domain import line_value


@dataclass(frozen=True)
class StandardLine:
    item: str
    qty_per_batch: Decimal  # in the rate's unit (kg, L, piece)
    rate: Decimal  # standard rate: the opening purchase rate (assumption A2)


@dataclass(frozen=True)
class StandardCost:
    materials_per_batch: Decimal
    conversion_per_batch: Decimal
    total_per_batch: Decimal
    expected_output: Decimal
    per_unit: Decimal  # 6 dp; shown to paise


def standard_cost(
    lines: Sequence[StandardLine], conversion_per_batch: Decimal, expected_output: Decimal
) -> StandardCost:
    """(Σ BOM qty x standard rate + conversion costs) / expected good output, at full yield (A2).

    Benchmark: (1,680 + 1,400 + 240 + 500 + 150) + (1,200 + 600) = 5,770.00 per batch / 200 = 28.85 per packet.
    """
    if expected_output <= 0:
        raise DomainError("bad_expected_output", "expected good output must be positive")
    materials = sum((line_value(line.qty_per_batch, line.rate) for line in lines), Decimal(0))
    total = materials + conversion_per_batch
    return StandardCost(
        materials_per_batch=materials,
        conversion_per_batch=conversion_per_batch,
        total_per_batch=total,
        expected_output=expected_output,
        per_unit=round_unit_cost(total / expected_output),
    )
