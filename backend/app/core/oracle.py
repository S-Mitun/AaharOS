"""Loads benchmark/expected_results.yaml without ever creating a float.

YAML floats (40.0, 43.125, -6.00) are parsed straight from their source text into Decimal,
so "187.50" stays Decimal("187.50"). Used by the benchmark tests and the public guide API.
"""

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml


class _DecimalLoader(yaml.SafeLoader):
    """SafeLoader whose float constructor returns Decimal."""


def _construct_decimal(loader: yaml.SafeLoader, node: yaml.Node) -> Decimal:
    text = str(loader.construct_scalar(node))  # type: ignore[arg-type]
    return Decimal(text.replace("_", ""))


_DecimalLoader.add_constructor("tag:yaml.org,2002:float", _construct_decimal)

SACRED_SECTIONS = ("inputs", "nit_expected")


def load_oracle(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.load(fh, Loader=_DecimalLoader)  # noqa: S506 - SafeLoader subclass
    if not isinstance(data, dict):
        raise ValueError(f"oracle at {path} is not a mapping")
    return data


def to_jsonable(value: Any) -> Any:
    """Numbers become strings (exact), everything else keeps its JSON shape."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, Decimal | int):
        return str(value)
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    return value


def sacred_digest(oracle: dict[str, Any]) -> str:
    """sha256 over the canonical JSON of the sections that must never change."""
    sacred = {name: to_jsonable(oracle[name]) for name in SACRED_SECTIONS}
    canonical = json.dumps(sacred, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
