"""Pure planning rules (MP12, ADR-0019). No database. Planning recommends; it never posts.

- L1 Material runway: for each material of a recipe and pack, batches left = available / needed per standard batch
  (recipe lines per batch; pack lines per good unit x the expected good units of one batch). The smallest is binding;
  full batches = that ratio rounded down.
- L2 Shortage attribution: the part of a shortage explained by recent yield losses = min(shortage, Σ max(0, expected
  - good) over recent completed batches of that product).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any, Final

from app.core.errors import DomainError
from app.core.explained import Explained, ExplainedInput, SourceRef

TWO_PLACES: Final = Decimal("0.01")


class PlanningError(DomainError):
    """A plan that cannot be made."""


@dataclass(frozen=True)
class MaterialNeed:
    item_code: str
    unit: str  # the stock unit shown (kg, L, piece)
    available: Decimal  # in `unit`
    per_batch: Decimal  # in `unit`, for one standard batch


@dataclass(frozen=True)
class RunwayLine:
    item_code: str
    unit: str
    available: Decimal
    per_batch: Decimal
    batches: Decimal  # exact
    explained: Explained

    @property
    def batches_display(self) -> Decimal:
        return self.batches.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Runway:
    lines: tuple[RunwayLine, ...]
    binding: tuple[str, ...]  # item codes whose runway is the smallest (shown to 2 places)
    full_batches: int
    explained: Explained


def runway(needs: Sequence[MaterialNeed], source: SourceRef | None = None) -> Runway:
    if not needs:
        raise PlanningError("no_materials", "this recipe and pack need no materials")
    lines = []
    for n in needs:
        if n.per_batch <= 0:
            raise PlanningError("bad_standard", f"{n.item_code}: the standard per batch must be positive")
        ratio = max(n.available, Decimal(0)) / n.per_batch
        lines.append(
            RunwayLine(
                n.item_code,
                n.unit,
                n.available,
                n.per_batch,
                ratio,
                Explained(
                    value=ratio.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
                    unit="batches",
                    formula="available / needed per standard batch",
                    inputs=(
                        ExplainedInput(f"{n.item_code} available", n.available, n.unit, source),
                        ExplainedInput(f"{n.item_code} per standard batch", n.per_batch, n.unit, source),
                    ),
                    method="Material runway",
                ),
            )
        )
    smallest = min(ln.batches_display for ln in lines)
    binding = tuple(ln.item_code for ln in lines if ln.batches_display == smallest)
    least = min(ln.batches for ln in lines)
    full = int(least.to_integral_value(rounding=ROUND_FLOOR))
    return Runway(
        tuple(lines),
        binding,
        full,
        Explained(
            value=Decimal(full),
            unit="batches",
            formula="floor(min over materials of available / needed per batch)",
            inputs=tuple(ExplainedInput(f"{ln.item_code} runway", ln.batches_display, "batches") for ln in lines),
            method="Full batches possible",
        ),
    )


@dataclass(frozen=True)
class YieldLoss:
    run_no: str
    expected: Decimal  # good units the batch should have made
    good: int


def shortage_attribution(shortage: int, losses: Sequence[YieldLoss], source: SourceRef | None = None) -> Explained:
    """How much of a shortage the recent yield losses explain: had each batch made its expected good units, the
    shortage would have been that much smaller (never more than the shortage itself)."""
    lost = sum((max(Decimal(0), loss.expected - loss.good) for loss in losses), Decimal(0))
    attributed = min(Decimal(max(shortage, 0)), lost).to_integral_value(rounding=ROUND_FLOOR)
    return Explained(
        value=attributed,
        unit="packets",
        formula="min(shortage, Σ max(0, expected good - good) over recent batches)",
        inputs=(
            ExplainedInput("Shortage", Decimal(shortage), "packets", source),
            *(
                ExplainedInput(
                    f"{loss.run_no} lost (expected {loss.expected.normalize()} - good {loss.good})",
                    max(Decimal(0), loss.expected - loss.good),
                    "packets",
                )
                for loss in losses
            ),
        ),
        method="Shortage attribution",
    )


@dataclass(frozen=True)
class Action:
    """One of "Today's 3 actions" on the Morning Brief: what to do, the rupees at stake and where to do it."""

    kind: str  # decide, make, buy, collect, leak
    title: str
    impact: Decimal  # rupees
    link: str
    explained: Explained

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "impact": self.explained.to_json(),
            "link": self.link,
        }


def rank_actions(candidates: Sequence[Action], limit: int = 3) -> list[Action]:
    """The largest rupee impact first; ties in a fixed order so the brief never reshuffles itself. Nothing at zero."""
    order = {"decide": 0, "make": 1, "buy": 2, "collect": 3, "leak": 4}
    kept = [a for a in candidates if a.impact > 0]
    return sorted(kept, key=lambda a: (-a.impact, order.get(a.kind, 9), a.title))[:limit]
