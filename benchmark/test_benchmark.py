"""The 26 benchmark assertions (MASTER_PACK Part C). 1-14 are NIT's checks, 15-26 are AaharOS extensions.

Each test is marked with its number, title, the MP that turns it green, and the oracle keys it checks.
Until that MP lands the test is a strict xfail: it must fail with NotImplementedError, and the moment it
passes the xfail marker must be removed (strict mode turns an unexpected pass into a failure).
"""

from collections.abc import Callable
from typing import Any, TypeVar

import pytest

F = TypeVar("F", bound=Callable[..., Any])


def pending(owner_mp: str) -> Callable[[F], F]:
    return pytest.mark.xfail(raises=NotImplementedError, strict=True, reason=f"not built yet ({owner_mp})")


def not_built(owner_mp: str) -> None:
    raise NotImplementedError(owner_mp)


A = pytest.mark.assertion


@A(1, "Flour closing", "MP04", "nit_expected.flour_closing_kg")
@pending("MP04")
def test_a01_flour_closing() -> None:
    not_built("MP04")


@A(2, "Oil closing", "MP04", "nit_expected.oil_closing_L")
@pending("MP04")
def test_a02_oil_closing() -> None:
    not_built("MP04")


@A(3, "Pouches closing", "MP04", "nit_expected.pouches_closing")
@pending("MP04")
def test_a03_pouches_closing() -> None:
    not_built("MP04")


@A(4, "Finished goods after run", "MP06", "nit_expected.fg_after_run_packets")
@pending("MP06")
def test_a04_fg_after_run() -> None:
    not_built("MP06")


@A(5, "Finished goods after Retailer A dispatch", "MP10", "nit_expected.fg_after_dispatch_A_packets")
@pending("MP10")
def test_a05_fg_after_dispatch_a() -> None:
    not_built("MP10")


@A(6, "Yield variance (flagged)", "MP06", "nit_expected.yield_variance_percent")
@pending("MP06")
def test_a06_yield_variance() -> None:
    not_built("MP06")


@A(7, "Oil variance (flagged)", "MP06", "nit_expected.oil_variance_percent")
@pending("MP06")
def test_a07_oil_variance() -> None:
    not_built("MP06")


@A(8, "Retailer A invoice taxable value", "MP10", "nit_expected.invoice_A.taxable")
@pending("MP10")
def test_a08_invoice_a_taxable() -> None:
    not_built("MP10")


@A(9, "Retailer A CGST", "MP10", "nit_expected.invoice_A.cgst")
@pending("MP10")
def test_a09_invoice_a_cgst() -> None:
    not_built("MP10")


@A(10, "Retailer A SGST", "MP10", "nit_expected.invoice_A.sgst")
@pending("MP10")
def test_a10_invoice_a_sgst() -> None:
    not_built("MP10")


@A(11, "Retailer A invoice total", "MP10", "nit_expected.invoice_A.total")
@pending("MP10")
def test_a11_invoice_a_total() -> None:
    not_built("MP10")


@A(12, "Retailer A outstanding", "MP10", "nit_expected.outstanding_A")
@pending("MP10")
def test_a12_outstanding_a() -> None:
    not_built("MP10")


@A(
    13,
    "Distributor B shortage flagged, no negative stock, not invoiced",
    "MP09",
    "nit_expected.distributor_B.requested",
    "nit_expected.distributor_B.available",
    "nit_expected.distributor_B.shortage",
)
@pending("MP09")
def test_a13_distributor_b_shortage() -> None:
    not_built("MP09")


@A(
    14,
    "Distributor B tax regime",
    "MP10",
    "nit_expected.distributor_B.tax_regime",
    "aaharos_expected.distributor_B_options.full_120.igst",
    "aaharos_expected.distributor_B_options.partial_88.igst",
)
@pending("MP10")
def test_a14_distributor_b_igst() -> None:
    not_built("MP10")


@A(
    15,
    "Spice closing / cartons closing",
    "MP06",
    "aaharos_expected.spice_closing_kg",
    "aaharos_expected.cartons_closing",
)
@pending("MP06")
def test_a15_spice_and_cartons_closing() -> None:
    not_built("MP06")


@A(16, "Flour WAC after purchase", "MP05", "aaharos_expected.flour_wac_after_purchase")
@pending("MP05")
def test_a16_flour_wac() -> None:
    not_built("MP05")


@A(
    17,
    "Run cost",
    "MP07",
    "aaharos_expected.run_cost.total",
    "aaharos_expected.run_cost.materials_total",
)
@pending("MP07")
def test_a17_run_cost() -> None:
    not_built("MP07")


@A(
    18,
    "Cost per good packet + sensitivity",
    "MP07",
    "aaharos_expected.run_cost.cost_per_good_packet",
    "aaharos_expected.valuation_sensitivity.FIFO.per_packet",
    "aaharos_expected.valuation_sensitivity.LAST.per_packet",
)
@pending("MP07")
def test_a18_cost_per_packet() -> None:
    not_built("MP07")


@A(19, "Variance waterfall sums exactly", "MP07", "aaharos_expected.variance_waterfall.total_unfavourable")
@pending("MP07")
def test_a19_waterfall() -> None:
    not_built("MP07")


@A(
    20,
    "Pouch flexible variance (flagged)",
    "MP06",
    "aaharos_expected.flexible_standard_variances.pouch_vs_good_output_percent",
)
@pending("MP06")
def test_a20_pouch_flexible_variance() -> None:
    not_built("MP06")


@A(
    21,
    "FEFO dispatch to Retailer A",
    "MP10",
    "aaharos_expected.fefo_dispatch_A.from_opening_lot",
    "aaharos_expected.fefo_dispatch_A.from_batch_B001",
)
@pending("MP10")
def test_a21_fefo_dispatch() -> None:
    not_built("MP10")


@A(
    22,
    "Value conservation of the run",
    "MP10",
    "aaharos_expected.fg_value_split_of_run.dispatched_100",
    "aaharos_expected.fg_value_split_of_run.remaining_88",
)
@pending("MP10")
def test_a22_value_conservation() -> None:
    not_built("MP10")


@A(
    23,
    "Shortage attribution",
    "MP12",
    "aaharos_expected.shortage_attribution_B.caused_by_this_runs_yield_loss",
)
@pending("MP12")
def test_a23_shortage_attribution() -> None:
    not_built("MP12")


@A(24, "Material runway", "MP12", "aaharos_expected.material_runway_after_run.max_full_batches")
@pending("MP12")
def test_a24_material_runway() -> None:
    not_built("MP12")


@A(
    25,
    "e-Way Bill for B not required",
    "MP10",
    "aaharos_expected.distributor_B_options.full_120.eway_bill_required",
)
@pending("MP10")
def test_a25_eway_bill() -> None:
    not_built("MP10")


@A(26, "Integrity: 4 conservation laws, balance rebuild, audit chain", "MP11")
@pending("MP11")
def test_a26_integrity() -> None:
    not_built("MP11")
