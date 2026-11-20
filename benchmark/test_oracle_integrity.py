"""Checks on the oracle itself. These pass from day one.

1. The sacred sections (inputs, nit_expected) have not been edited (sha256 guard).
2. Every derived figure in the oracle follows from its inputs with plain Decimal arithmetic.
   This verifies the fixture, not the application: the application is tested in test_benchmark.py.
"""

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any

import pytest

from app.core.oracle import sacred_digest

# Recorded when the oracle was placed in the repo (MP00). Changing it requires a written reason in an ADR.
SACRED_SHA256 = "bc750483bb41ad5c299b6ae2d738894faa749510036d4b9adddfea01656edfbd"

D = Decimal
HUNDRED = D(100)


def q2(x: Decimal) -> Decimal:
    return x.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def q6(x: Decimal) -> Decimal:
    return x.quantize(D("0.000001"), rounding=ROUND_HALF_UP)


@pytest.fixture(scope="module")
def o(oracle: dict[str, Any]) -> dict[str, Any]:
    inp = oracle["inputs"]
    bom = {line["item"]: line for line in inp["bom_murukku_200g_per_batch"]["lines"]}
    s = inp["steps"]
    wac = (
        inp["opening_stock"]["flour"]["qty"] * inp["opening_stock"]["flour"]["rate"]
        + s["1_purchase"]["qty"] * s["1_purchase"]["rate"]
    ) / (inp["opening_stock"]["flour"]["qty"] + s["1_purchase"]["qty"])
    return {
        "inp": inp,
        "nit": oracle["nit_expected"],
        "ext": oracle["aaharos_expected"],
        "bom": bom,
        "open": inp["opening_stock"],
        "s": s,
        "expected_out": D(inp["bom_murukku_200g_per_batch"]["expected_good_output_packets"]),
        "good": D(s["3_output"]["good_packets"]),
        "damaged": D(s["3_output"]["damaged_pouches"]),
        "cartons_used": D(s["3_output"]["cartons_used"]),
        "price": inp["selling_price_ex_tax"],
        "gst": D(oracle["gst_rate_percent"]),
        "tol": D(oracle["variance_tolerance_percent"]),
        "factory_state": oracle["factory_state"],
        "wac": wac,
        "run_costs": s["8_run_costs"]["labour"] + s["8_run_costs"]["gas_power"],
    }


def test_sacred_sections_unchanged(oracle: dict[str, Any]) -> None:
    assert (
        sacred_digest(oracle) == SACRED_SHA256
    ), "inputs or nit_expected changed. These are sacred (CLAUDE.md). Revert the edit."


def test_no_float_in_oracle(oracle: dict[str, Any]) -> None:
    def walk(v: object) -> None:
        assert not isinstance(v, float), v
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        if isinstance(v, list):
            for x in v:
                walk(x)

    walk(oracle)


def test_stock_closings(o: dict[str, Any]) -> None:
    op, s, nit, ext = o["open"], o["s"], o["nit"], o["ext"]
    assert op["flour"]["qty"] + s["1_purchase"]["qty"] - s["2_issue"]["flour"] == nit["flour_closing_kg"]
    assert op["cooking_oil"]["qty"] - s["2_issue"]["cooking_oil"] == nit["oil_closing_L"]
    assert op["pouch_200g"]["qty"] - (o["good"] + o["damaged"]) == nit["pouches_closing"]
    assert op["spice_mix"]["qty"] - s["2_issue"]["spice_mix"] == ext["spice_closing_kg"]
    assert op["carton_20"]["qty"] - o["cartons_used"] == ext["cartons_closing"]
    assert op["murukku_200g"]["qty"] + o["good"] == nit["fg_after_run_packets"]
    assert nit["fg_after_run_packets"] - s["5_invoice_A"]["dispatch_qty"] == nit["fg_after_dispatch_A_packets"]


def test_variances(o: dict[str, Any]) -> None:
    yield_pct = (o["good"] - o["expected_out"]) / o["expected_out"] * HUNDRED
    oil_std = o["bom"]["cooking_oil"]["qty"]
    oil_pct = (o["s"]["2_issue"]["cooking_oil"] - oil_std) / oil_std * HUNDRED
    assert q2(yield_pct) == o["nit"]["yield_variance_percent"]
    assert q2(oil_pct) == o["nit"]["oil_variance_percent"]
    assert abs(yield_pct) > o["tol"] and abs(oil_pct) > o["tol"]

    per_good = o["bom"]["pouch_200g"]["qty"] / o["expected_out"]
    pouch_std = per_good * o["good"]
    pouch_pct = (o["good"] + o["damaged"] - pouch_std) / pouch_std * HUNDRED
    carton_std = o["bom"]["carton_20"]["qty"] / o["expected_out"] * o["good"]
    carton_pct = (o["cartons_used"] - carton_std) / carton_std * HUNDRED
    flex = o["ext"]["flexible_standard_variances"]
    assert q2(pouch_pct) == flex["pouch_vs_good_output_percent"]
    assert abs(pouch_pct) > o["tol"]
    assert q2(carton_pct) == flex["carton_vs_good_output_percent"]
    # Batch view hides the damage: 194 vs 200 is -3.00%, inside tolerance.
    batch_pct = (o["good"] + o["damaged"] - o["bom"]["pouch_200g"]["qty"]) / o["bom"]["pouch_200g"]["qty"] * HUNDRED
    assert q2(batch_pct) == D("-3.00") and abs(batch_pct) <= o["tol"]


def test_invoice_and_outstanding(o: dict[str, Any]) -> None:
    s, inv = o["s"], o["nit"]["invoice_A"]
    assert s["4_order_A"]["state"] == o["factory_state"]  # intra-state -> CGST + SGST
    taxable = s["5_invoice_A"]["dispatch_qty"] * o["price"]
    half = q2(taxable * o["gst"] / 2 / HUNDRED)
    assert (taxable, half, half, taxable + half + half) == (
        inv["taxable"],
        inv["cgst"],
        inv["sgst"],
        inv["total"],
    )
    assert inv["total"] - s["7_payment_A"]["amount"] == o["nit"]["outstanding_A"]


def test_distributor_b(o: dict[str, Any]) -> None:
    b, s = o["nit"]["distributor_B"], o["s"]
    assert b["requested"] == s["6_order_B"]["qty"]
    assert b["available"] == o["nit"]["fg_after_dispatch_A_packets"]
    assert b["shortage"] == b["requested"] - b["available"]
    assert s["6_order_B"]["state"] != o["factory_state"] and b["tax_regime"] == "IGST"
    opts = o["ext"]["distributor_B_options"]
    for key, qty in (("full_120", b["requested"]), ("partial_88", b["available"])):
        taxable = qty * o["price"]
        igst = q2(taxable * o["gst"] / HUNDRED)
        assert (opts[key]["taxable"], opts[key]["igst"], opts[key]["total"]) == (
            taxable,
            igst,
            taxable + igst,
        )
    assert opts["partial_88"]["backorder"] == b["shortage"]
    # Inter-state e-way bill threshold (MASTER_PACK A.4, config in the app): Rs 50,000.
    assert opts["full_120"]["eway_bill_required"] is (opts["full_120"]["total"] > D(50000))


def _run_cost(o: dict[str, Any], flour_rate: Decimal) -> Decimal:
    op, iss = o["open"], o["s"]["2_issue"]
    return (
        iss["flour"] * flour_rate
        + iss["cooking_oil"] * op["cooking_oil"]["rate"]
        + iss["spice_mix"] * op["spice_mix"]["rate"]
        + (o["good"] + o["damaged"]) * op["pouch_200g"]["rate"]
        + o["cartons_used"] * op["carton_20"]["rate"]
        + o["run_costs"]
    )


def test_costing_and_sensitivity(o: dict[str, Any]) -> None:
    ext, rc = o["ext"], o["ext"]["run_cost"]
    assert o["wac"] == ext["flour_wac_after_purchase"]
    total = _run_cost(o, o["wac"])
    assert total == rc["total"]
    assert total - o["run_costs"] == rc["materials_total"]
    assert q2(total / o["good"]) == rc["cost_per_good_packet"]
    fifo = _run_cost(o, o["open"]["flour"]["rate"])  # 40 kg fits inside the 100 kg opening layer
    last = _run_cost(o, o["s"]["1_purchase"]["rate"])
    sens = ext["valuation_sensitivity"]
    assert (fifo, q2(fifo / o["good"])) == (sens["FIFO"]["total"], sens["FIFO"]["per_packet"])
    assert (last, q2(last / o["good"])) == (sens["LAST"]["total"], sens["LAST"]["per_packet"])


def test_standard_cost_and_waterfall(o: dict[str, Any]) -> None:
    op, bom, ext = o["open"], o["bom"], o["ext"]
    rate = {k: op[k]["rate"] for k in bom}
    materials = sum((line["qty"] * rate[k] for k, line in bom.items()), D(0))
    std = ext["standard_cost"]
    assert materials == std["materials_per_batch"]
    assert materials + o["run_costs"] == std["total_per_batch"]
    per_packet = (materials + o["run_costs"]) / o["expected_out"]
    assert per_packet == std["per_packet"]
    assert per_packet * o["good"] == std["standard_cost_of_188"]

    wf = ext["variance_waterfall"]
    batch_inputs = (
        sum((line["qty"] * rate[k] for k, line in bom.items() if line["driver"] == "PER_BATCH"), D(0)) + o["run_costs"]
    )
    iss = o["s"]["2_issue"]
    parts = {
        "yield_loss": (o["expected_out"] - o["good"]) * (batch_inputs / o["expected_out"]),
        "oil_usage": (iss["cooking_oil"] - bom["cooking_oil"]["qty"]) * rate["cooking_oil"],
        "flour_price": (o["wac"] - rate["flour"]) * iss["flour"],
        "pouch_damage": o["damaged"] * rate["pouch_200g"],
        "carton_usage": (o["cartons_used"] - bom["carton_20"]["qty"] / o["expected_out"] * o["good"])
        * rate["carton_20"],
    }
    for name, value in parts.items():
        assert value == wf[name], name
    total = ext["run_cost"]["total"] - std["standard_cost_of_188"]
    assert total == wf["total_unfavourable"] == sum(parts.values(), D(0))


def test_packing_fefo_and_value_split(o: dict[str, Any]) -> None:
    ext = o["ext"]
    per_carton = o["expected_out"] / o["bom"]["carton_20"]["qty"]
    sent = o["s"]["5_invoice_A"]["dispatch_qty"]
    remaining_batch = o["good"] - (sent - o["open"]["murukku_200g"]["qty"])
    for key, n in (
        ("run_output", o["good"]),
        ("dispatch_A", sent),
        ("remaining", o["nit"]["fg_after_dispatch_A_packets"]),
    ):
        full, loose = divmod(n, per_carton)
        assert (full, loose) == (
            ext["packing"][key]["full_cartons"],
            ext["packing"][key]["loose_packets"],
        ), key

    fefo = ext["fefo_dispatch_A"]
    assert fefo["from_opening_lot"] == o["open"]["murukku_200g"]["qty"]
    assert fefo["from_opening_lot"] + fefo["from_batch_B001"] == sent
    assert fefo["remaining_batch_B001"] == remaining_batch

    total = ext["run_cost"]["total"]
    unit = q6(total / o["good"])
    dispatched = q2(fefo["from_batch_B001"] * unit)
    split = ext["fg_value_split_of_run"]
    assert dispatched == split["dispatched_100"]
    assert total - dispatched == split["remaining_88"]  # last unit absorbs rounding

    gm = ext["gross_margin_invoice_A"]
    cogs = fefo["from_opening_lot"] * ext["standard_cost"]["per_packet"] + dispatched  # A1: opening lot at standard
    taxable = o["nit"]["invoice_A"]["taxable"]
    assert cogs == gm["cogs"]
    assert taxable - cogs == gm["gross_margin"]
    assert q2((taxable - cogs) / taxable * HUNDRED) == gm["gross_margin_percent"]


def test_shortage_attribution_runway_and_mass(o: dict[str, Any]) -> None:
    ext, nit = o["ext"], o["nit"]
    fg_if_full_yield = o["open"]["murukku_200g"]["qty"] + o["expected_out"] - o["s"]["5_invoice_A"]["dispatch_qty"]
    shortage_if_full = max(D(0), o["s"]["6_order_B"]["qty"] - fg_if_full_yield)
    attr = ext["shortage_attribution_B"]
    assert attr["shortage"] == nit["distributor_B"]["shortage"]
    assert nit["distributor_B"]["shortage"] - shortage_if_full == attr["caused_by_this_runs_yield_loss"]

    after = {
        "flour": nit["flour_closing_kg"],
        "cooking_oil": nit["oil_closing_L"],
        "spice_mix": ext["spice_closing_kg"],
        "pouch_200g": nit["pouches_closing"],
        "carton_20": ext["cartons_closing"],
    }
    runway = ext["material_runway_after_run"]
    batches = {k: D(v) / o["bom"][k]["qty"] for k, v in after.items()}
    for k, b in batches.items():
        assert q2(b) == runway[k], k
    assert min(batches.values()).quantize(D(1), rounding=ROUND_FLOOR) == runway["max_full_batches"]

    net_kg = D("0.200")  # 200 g pack (SKU name); becomes pack_spec data in MP06
    mb = ext["mass_balance"]
    assert o["expected_out"] * net_kg == mb["expected_packed_kg"]
    assert o["good"] * net_kg == mb["good_packed_kg"]
    assert mb["expected_packed_kg"] - mb["good_packed_kg"] == mb["unexplained_gap_kg"]
