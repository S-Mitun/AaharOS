"""The 26 benchmark assertions (MASTER_PACK Part C). 1-14 are NIT's checks, 15-26 are AaharOS extensions.

Each test is marked with its number, title, the MP that turns it green, and the oracle keys it checks.
Until that MP lands the test is a strict xfail: it must fail with NotImplementedError, and the moment it
passes the xfail marker must be removed (strict mode turns an unexpected pass into a failure).
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Any, TypeVar

import pytest

F = TypeVar("F", bound=Callable[..., Any])


def pending(owner_mp: str) -> Callable[[F], F]:
    return pytest.mark.xfail(raises=NotImplementedError, strict=True, reason=f"not built yet ({owner_mp})")


def not_built(owner_mp: str) -> None:
    raise NotImplementedError(owner_mp)


A = pytest.mark.assertion


# Assertions 1-3 and 15 (MP04): closing stock after the NIT movements, replayed through the services
# (app/modules/judge/replay.py). Valued since MP05; since MP06 J2 is a real material issue and J3 the real
# completion of run B-001.


@A(1, "Flour closing", "MP04", "nit_expected.flour_closing_kg")
def test_a01_flour_closing(stock_replay: Any, oracle: dict[str, Any]) -> None:
    assert stock_replay.stock_units["flour"] == "kg"
    assert stock_replay.closing_in("flour", "RAW_STORE") == oracle["nit_expected"]["flour_closing_kg"]


@A(2, "Oil closing", "MP04", "nit_expected.oil_closing_L")
def test_a02_oil_closing(stock_replay: Any, oracle: dict[str, Any]) -> None:
    assert stock_replay.stock_units["cooking_oil"] == "L"
    assert stock_replay.closing_in("cooking_oil", "RAW_STORE") == oracle["nit_expected"]["oil_closing_L"]


@A(3, "Pouches closing", "MP04", "nit_expected.pouches_closing")
def test_a03_pouches_closing(stock_replay: Any, oracle: dict[str, Any]) -> None:
    assert stock_replay.closing_in("pouch_200g", "PACK_STORE") == oracle["nit_expected"]["pouches_closing"]


@A(4, "Finished goods after run", "MP06", "nit_expected.fg_after_run_packets")
def test_a04_fg_after_run(stock_replay: Any, oracle: dict[str, Any]) -> None:
    assert stock_replay.stock_units["murukku_200g"] == "packet"
    # the replay continues to step 8 (MP10), so this reads FG at the moment B-001 completed
    assert stock_replay.fg_after_run == oracle["nit_expected"]["fg_after_run_packets"]


@A(5, "Finished goods after Retailer A dispatch", "MP10", "nit_expected.fg_after_dispatch_A_packets")
def test_a05_fg_after_dispatch_a(stock_replay: Any, oracle: dict[str, Any]) -> None:
    assert stock_replay.closing_in("murukku_200g", "FG_STORE") == oracle["nit_expected"]["fg_after_dispatch_A_packets"]


# Assertions 6, 7 and 20 (MP06): variances of run B-001, computed on read from its frozen snapshot (ADR-0013).


@A(6, "Yield variance (flagged)", "MP06", "nit_expected.yield_variance_percent")
def test_a06_yield_variance(stock_replay: Any, oracle: dict[str, Any]) -> None:
    v = stock_replay.run.pack_lines[0].yield_variance
    assert v.pct_display == oracle["nit_expected"]["yield_variance_percent"]
    assert v.flagged and v.direction == "UNFAVOURABLE"
    assert v.explained.unit == "%" and v.explained.value == v.pct_display


@A(7, "Oil variance (flagged)", "MP06", "nit_expected.oil_variance_percent")
def test_a07_oil_variance(stock_replay: Any, oracle: dict[str, Any]) -> None:
    v = stock_replay.run.ingredient("cooking_oil")
    assert v.pct_display == oracle["nit_expected"]["oil_variance_percent"]
    assert v.flagged and v.view == "PER_BATCH"


@A(8, "Retailer A invoice taxable value", "MP10", "nit_expected.invoice_A.taxable")
def test_a08_invoice_a_taxable(stock_replay: Any, oracle: dict[str, Any]) -> None:
    inv = stock_replay.invoice_a
    assert (inv["regime"], inv["status"]) == ("INTRA", "POSTED")
    assert Decimal(inv["taxable"]) == oracle["nit_expected"]["invoice_A"]["taxable"]


@A(9, "Retailer A CGST", "MP10", "nit_expected.invoice_A.cgst")
def test_a09_invoice_a_cgst(stock_replay: Any, oracle: dict[str, Any]) -> None:
    assert Decimal(stock_replay.invoice_a["by_tax"]["CGST"]) == oracle["nit_expected"]["invoice_A"]["cgst"]


@A(10, "Retailer A SGST", "MP10", "nit_expected.invoice_A.sgst")
def test_a10_invoice_a_sgst(stock_replay: Any, oracle: dict[str, Any]) -> None:
    assert Decimal(stock_replay.invoice_a["by_tax"]["SGST"]) == oracle["nit_expected"]["invoice_A"]["sgst"]


@A(11, "Retailer A invoice total", "MP10", "nit_expected.invoice_A.total")
def test_a11_invoice_a_total(stock_replay: Any, oracle: dict[str, Any]) -> None:
    inv = stock_replay.invoice_a
    assert Decimal(inv["total"]) == oracle["nit_expected"]["invoice_A"]["total"]
    assert Decimal(inv["round_off"]) == 0 and "IGST" not in inv["by_tax"]


@A(12, "Retailer A outstanding", "MP10", "nit_expected.outstanding_A")
def test_a12_outstanding_a(stock_replay: Any, oracle: dict[str, Any]) -> None:
    statement = stock_replay.statement_a
    assert Decimal(statement["outstanding"]["value"]) == oracle["nit_expected"]["outstanding_A"]
    assert Decimal(statement["invoices"][0]["paid"]) == oracle["inputs"]["steps"]["7_payment_A"]["amount"]


@A(
    13,
    "Distributor B shortage flagged, no negative stock, not invoiced",
    "MP09",
    "nit_expected.distributor_B.requested",
    "nit_expected.distributor_B.available",
    "nit_expected.distributor_B.shortage",
)
def test_a13_distributor_b_shortage(stock_replay: Any, oracle: dict[str, Any]) -> None:
    """MP09: after Retailer A's approval reserves 150 of the 238 packets, Distributor B's inbox card shows the
    shortage; a full approval is refused with nothing written; stock never goes negative; B is not invoiced."""
    expected = oracle["nit_expected"]["distributor_B"]
    card = stock_replay.b_card
    (line,) = card["card_lines"]
    assert Decimal(line["requested"]) == expected["requested"]
    assert Decimal(line["available"]["value"]) == expected["available"]
    assert Decimal(line["shortage"]["value"]) == expected["shortage"] > 0  # flagged
    assert stock_replay.b_full_refusal == "insufficient_available"
    assert card["status"] == "SUBMITTED" and card["status"] != "INVOICED"
    assert line["approved"] == "0" and line["can_send_now"] == str(expected["available"])
    assert stock_replay.closing_in("murukku_200g", "FG_STORE") >= 0  # no negative stock (238 on hand)


@A(
    14,
    "Distributor B tax regime",
    "MP10",
    "nit_expected.distributor_B.tax_regime",
    "aaharos_expected.distributor_B_options.full_120.igst",
    "aaharos_expected.distributor_B_options.partial_88.igst",
)
def test_a14_distributor_b_igst(stock_replay: Any, oracle: dict[str, Any]) -> None:
    preview = stock_replay.b_card["tax_preview"]
    opts = oracle["aaharos_expected"]["distributor_B_options"]
    assert oracle["nit_expected"]["distributor_B"]["tax_regime"] == "IGST"
    assert preview["full"]["regime"] == preview["partial"]["regime"] == "INTER"
    assert set(preview["full"]["by_tax"]) == {"IGST"}
    assert Decimal(preview["full"]["by_tax"]["IGST"]) == opts["full_120"]["igst"]
    assert Decimal(preview["partial"]["by_tax"]["IGST"]) == opts["partial_88"]["igst"]


@A(
    15,
    "Spice closing / cartons closing",
    "MP04",
    "aaharos_expected.spice_closing_kg",
    "aaharos_expected.cartons_closing",
)
def test_a15_spice_and_cartons_closing(stock_replay: Any, oracle: dict[str, Any]) -> None:
    ext = oracle["aaharos_expected"]
    assert stock_replay.closing_in("spice_mix", "RAW_STORE") == ext["spice_closing_kg"]
    assert stock_replay.closing_in("carton_20", "PACK_STORE") == ext["cartons_closing"]


@A(16, "Flour WAC after purchase", "MP05", "aaharos_expected.flour_wac_after_purchase")
def test_a16_flour_wac(stock_replay: Any, oracle: dict[str, Any]) -> None:
    wac = stock_replay.flour_wac_after_purchase  # an Explained value from valuation.wac, read from the ledger
    assert (wac.unit, wac.method) == ("INR/kg", "WAC")
    assert wac.value == oracle["aaharos_expected"]["flour_wac_after_purchase"]


@A(
    17,
    "Run cost",
    "MP07",
    "aaharos_expected.run_cost.total",
    "aaharos_expected.run_cost.materials_total",
)
def test_a17_run_cost(stock_replay: Any, oracle: dict[str, Any]) -> None:
    rc = oracle["aaharos_expected"]["run_cost"]
    cost = stock_replay.costing.cost  # Explained values from costing.run_costing, read from the ledger (MP07)
    assert cost.total.value == rc["total"] and cost.materials.value == rc["materials_total"]
    assert cost.conversion.value == rc["labour"] + rc["gas_power"]
    by_item = {i.label.split()[0]: i.value for i in cost.materials.inputs}
    assert (by_item["flour"], by_item["cooking_oil"], by_item["spice_mix"]) == (rc["flour"], rc["oil"], rc["spice"])
    assert (by_item["pouch_200g"], by_item["carton_20"]) == (rc["pouches"], rc["cartons"])
    assert stock_replay.costing.facts.cost_status == "FINAL"


@A(
    18,
    "Cost per good packet + sensitivity",
    "MP07",
    "aaharos_expected.run_cost.cost_per_good_packet",
    "aaharos_expected.valuation_sensitivity.FIFO.per_packet",
    "aaharos_expected.valuation_sensitivity.LAST.per_packet",
)
def test_a18_cost_per_packet(stock_replay: Any, oracle: dict[str, Any]) -> None:
    ext = oracle["aaharos_expected"]
    c = stock_replay.costing
    assert c.cost.per_good_unit.unit == "INR/packet"
    assert c.cost.per_good_unit.value.quantize(Decimal("0.01")) == ext["run_cost"]["cost_per_good_packet"]
    for method in ("WAC", "FIFO", "LAST"):
        s = c.sensitivity[method]
        assert Decimal(s["total"]["value"]) == ext["valuation_sensitivity"][method]["total"]
        assert Decimal(s["per_good_unit_display"]) == ext["valuation_sensitivity"][method]["per_packet"]
    assert [m for m, s in c.sensitivity.items() if s["posts"]] == ["WAC"]


@A(19, "Variance waterfall sums exactly", "MP07", "aaharos_expected.variance_waterfall.total_unfavourable")
def test_a19_waterfall(stock_replay: Any, oracle: dict[str, Any]) -> None:
    w = oracle["aaharos_expected"]["variance_waterfall"]
    wf = stock_replay.costing.waterfall
    assert wf.total.value == w["total_unfavourable"]
    assert wf.standard.value == oracle["aaharos_expected"]["standard_cost"]["standard_cost_of_188"]
    assert wf.component("YIELD").value == w["yield_loss"]
    assert wf.component("USAGE", "cooking_oil").value == w["oil_usage"]
    assert wf.component("PRICE", "flour").value == w["flour_price"]
    assert wf.component("USAGE", "pouch_200g").value == w["pouch_damage"]
    assert wf.component("USAGE", "carton_20").value == w["carton_usage"]
    assert sum(c.value for c in wf.components) == wf.total.value  # nothing left as silent residue
    assert {c.kind for c in wf.components} <= {"YIELD", "USAGE", "PRICE", "CONVERSION"}  # no rounding part needed


@A(
    20,
    "Pouch flexible variance (flagged)",
    "MP06",
    "aaharos_expected.flexible_standard_variances.pouch_vs_good_output_percent",
)
def test_a20_pouch_flexible_variance(stock_replay: Any, oracle: dict[str, Any]) -> None:
    line = stock_replay.run.pack_lines[0]
    flexible, batch = line.flexible("pouch_200g"), line.batch_view("pouch_200g")
    expected = oracle["aaharos_expected"]["flexible_standard_variances"]["pouch_vs_good_output_percent"]
    assert flexible.pct_display == expected and flexible.flagged and flexible.view == "PER_GOOD_UNIT"
    assert batch.pct_display == -3 and not batch.flagged  # the batch view hides the damage (bom.md section 1)


@A(
    21,
    "FEFO dispatch to Retailer A",
    "MP10",
    "aaharos_expected.fefo_dispatch_A.from_opening_lot",
    "aaharos_expected.fefo_dispatch_A.from_batch_B001",
)
def test_a21_fefo_dispatch(stock_replay: Any, oracle: dict[str, Any]) -> None:
    fefo = oracle["aaharos_expected"]["fefo_dispatch_A"]
    taken = {ln["lot_no"]: Decimal(ln["qty"]) for ln in stock_replay.dispatch_a["lines"]}
    assert taken.pop("OPEN-LOT") == fefo["from_opening_lot"]
    ((b001_no, b001_qty),) = taken.items()
    assert b001_qty == fefo["from_batch_B001"]
    assert stock_replay.b001_lot["FG_STORE"][0] == fefo["remaining_batch_B001"]


@A(
    22,
    "Value conservation of the run",
    "MP10",
    "aaharos_expected.fg_value_split_of_run.dispatched_100",
    "aaharos_expected.fg_value_split_of_run.remaining_88",
)
def test_a22_value_conservation(stock_replay: Any, oracle: dict[str, Any]) -> None:
    split = oracle["aaharos_expected"]["fg_value_split_of_run"]
    lot = stock_replay.b001_lot
    assert lot["CUSTOMER"][1] == split["dispatched_100"]
    assert lot["FG_STORE"][1] == split["remaining_88"]
    assert lot["CUSTOMER"][1] + lot["FG_STORE"][1] == oracle["aaharos_expected"]["run_cost"]["total"]


@A(
    23,
    "Shortage attribution",
    "MP12",
    "aaharos_expected.shortage_attribution_B.caused_by_this_runs_yield_loss",
)
def test_a23_shortage_attribution(stock_replay: Any, oracle: dict[str, Any]) -> None:
    """MP12: of Distributor B's shortage, the part B-001's yield loss explains (expected 200 good, made 188)."""
    expected = oracle["aaharos_expected"]["shortage_attribution_B"]
    (line,) = stock_replay.b_attribution["lines"]
    assert Decimal(line["shortage"]) == expected["shortage"]
    assert Decimal(line["attributed_to_yield_loss"]["value"]) == expected["caused_by_this_runs_yield_loss"]
    assert Decimal(line["would_have_been"]) == expected["shortage"] - expected["caused_by_this_runs_yield_loss"]


@A(24, "Material runway", "MP12", "aaharos_expected.material_runway_after_run.max_full_batches")
def test_a24_material_runway(stock_replay: Any, oracle: dict[str, Any]) -> None:
    """MP12: batches each material allows after the run, the binding items and the full batches possible."""
    expected = oracle["aaharos_expected"]["material_runway_after_run"]
    pack = next(p for p in stock_replay.runway if p["pack_code"] == "MURUKKU-200G")
    got = {m["item_code"]: Decimal(m["batches"]["value"]) for m in pack["materials"]}
    for item in ("flour", "cooking_oil", "spice_mix", "pouch_200g", "carton_20"):
        assert got[item] == expected[item], item
    assert Decimal(pack["full_batches"]["value"]) == expected["max_full_batches"]
    assert sorted(pack["binding"]) == ["pouch_200g"]  # the smallest runway; oil (1.95) also stops a second batch
    assert all(got[i] < 2 for i in ("cooking_oil", "pouch_200g"))


@A(
    25,
    "e-Way Bill for B not required",
    "MP10",
    "aaharos_expected.distributor_B_options.full_120.eway_bill_required",
)
def test_a25_eway_bill(stock_replay: Any, oracle: dict[str, Any]) -> None:
    full = stock_replay.b_card["tax_preview"]["full"]
    expected = oracle["aaharos_expected"]["distributor_B_options"]["full_120"]
    assert full["eway_required"] is expected["eway_bill_required"]
    assert Decimal(full["total"]) == expected["total"]
    # the reason is shown, not just a flag
    assert full["eway_reason"].startswith("Not needed: a delivery to another state")


@A(26, "Integrity: 4 conservation laws, balance rebuild, audit chain", "MP11")
def test_a26_integrity(stock_replay: Any) -> None:
    """MP11: on the NIT tenant, the audit chain is intact, the four conservation laws hold (quantity per journal,
    value per run, mass per run with the gap disclosed, tax lines = GST summary = export), balances rebuild
    identically from the ledger, every invoice adds up and no store promises more than it holds."""
    checks = {c["check"]: c["ok"] for c in stock_replay.integrity}
    assert len(checks) == 8
    assert all(checks.values()), [name for name, ok in checks.items() if not ok]
    assert any(name.startswith("Law 3") for name in checks) and any(name.startswith("Law 4") for name in checks)
