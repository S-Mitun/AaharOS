"""NIT section 5, posted through the real services. Reads only the oracle's `inputs`, never its expected results.

- `setup_section5()`: master data (items, a DEMO supplier, Retailer A and Distributor B) for an organization.
  Used by the replay, `make seed-benchmark` and `make seed-demo`.
- `post_section5_opening()`: J0, valued at the opening rates; the opening FG lot OPEN-LOT at the **standard cost**
  computed from the inputs (A1, A2, decision D3: 5,770.00 / 200 = 28.85 per packet, never copied from the oracle).
- `replay_stock()`: a fresh BENCHMARK tenant, then
  - J0 opening (valued)
  - J1 step 1 as a real purchase receipt (procurement, ₹45/kg)
  - J2 step 2 issue at WAC (valuation)
  - J3 step 3 run output: every input consumed at its book value, the batch lot B-001 at their sum.
    **J3 is still a labelled stand-in** for the MP06 production run (frozen recipe snapshot, variances).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core.explained import Explained
from app.modules.catalog import service as catalog
from app.modules.costing.domain import StandardCost, StandardLine, standard_cost
from app.modules.identity import service as identity
from app.modules.ledger import service as ledger
from app.modules.ledger.domain import LineSpec
from app.modules.procurement import service as procurement
from app.modules.procurement.domain import ReceiptLineIn
from app.modules.sales import service as sales
from app.modules.uom.domain import BASE_UNIT, from_base, to_base, unit
from app.modules.valuation import service as valuation
from app.modules.valuation.service import OpeningLine

STAND_IN_NOTE: Final = "J3 is a stand-in for the MP06 production run: inputs consumed at book value, no variances yet"
POSTING_DATE: Final = date(2026, 11, 21)  # fictional benchmark day

# Section 5 master data: item kind and home store. Units come from the oracle inputs.
ITEMS: Final[dict[str, tuple[str, str]]] = {
    "flour": ("RAW", "RAW_STORE"),
    "cooking_oil": ("RAW", "RAW_STORE"),
    "spice_mix": ("RAW", "RAW_STORE"),
    "pouch_200g": ("PACK", "PACK_STORE"),
    "carton_20": ("PACK", "PACK_STORE"),
    "murukku_200g": ("FG", "FG_STORE"),
}
FINISHED: Final = "murukku_200g"
POUCH: Final = "pouch_200g"
CARTON: Final = "carton_20"

# Fictional parties, labelled DEMO (CLAUDE.md). GSTINs follow the 15-character shape with an obviously fake PAN part.
SUPPLIER: Final = ("SUP-DEMO", "DEMO Flour Mills", "33", "33DEMOS0000S1Z0")
CUSTOMERS: Final = (
    ("RET-A", "DEMO Retailer A", "RETAILER", "33", "33DEMOA0000A1Z0"),  # Tamil Nadu: CGST + SGST
    ("DIST-B", "DEMO Distributor B", "DISTRIBUTOR", "29", "29DEMOB0000B1Z0"),  # Karnataka: IGST
)


@dataclass
class Section5:
    organization_id: uuid.UUID
    item_ids: dict[str, uuid.UUID]
    stock_units: dict[str, str]
    supplier_id: uuid.UUID
    customer_ids: dict[str, uuid.UUID]


@dataclass
class StockReplay:
    organization_id: uuid.UUID
    item_ids: dict[str, uuid.UUID]
    stock_units: dict[str, str]
    standard: StandardCost
    journals: dict[str, uuid.UUID] = field(default_factory=dict)
    receipt_no: str = ""
    flour_wac_after_purchase: Explained | None = None
    flour_issue_sensitivity: dict[str, dict[str, Any]] = field(default_factory=dict)
    closing: dict[tuple[str, str], Decimal] = field(default_factory=dict)  # (item, store) -> qty in stock unit
    closing_value: dict[tuple[str, str], Decimal] = field(default_factory=dict)  # (item, location) -> rupees
    note: str = STAND_IN_NOTE

    def closing_in(self, item: str, store: str) -> Decimal:
        return self.closing.get((item, store), Decimal(0))


def section5_standard_cost(oracle: dict[str, Any]) -> StandardCost:
    """Standard cost card from the inputs: BOM quantities at opening rates, plus this run's labour and gas (A2)."""
    inputs = oracle["inputs"]
    bom = inputs["bom_murukku_200g_per_batch"]
    opening = inputs["opening_stock"]
    run_costs = inputs["steps"]["8_run_costs"]
    lines = [StandardLine(ln["item"], Decimal(ln["qty"]), Decimal(opening[ln["item"]]["rate"])) for ln in bom["lines"]]
    conversion = Decimal(run_costs["labour"]) + Decimal(run_costs["gas_power"])
    return standard_cost(lines, conversion, Decimal(bom["expected_good_output_packets"]))


def setup_section5(
    session: Session, oracle: dict[str, Any], organization_id: uuid.UUID, actor_id: uuid.UUID | None = None
) -> Section5:
    """Locations, items, the DEMO supplier and the two DEMO customers. The session must be scoped to the org."""
    opening = oracle["inputs"]["opening_stock"]
    ledger.ensure_locations(session, organization_id)
    stock_units = {code: opening[code]["unit"] for code in ITEMS}
    ids = {
        code: catalog.create_item(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            code=code,
            name=f"DEMO {code.replace('_', ' ')}",
            kind=kind,
            base_uom=BASE_UNIT[unit(stock_units[code]).dimension],
            stock_uom=stock_units[code],
            lot_tracked=kind == "FG",
        )
        for code, (kind, _) in ITEMS.items()
    }
    code, name, state, gstin = SUPPLIER
    supplier = procurement.create_supplier(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        code=code,
        name=name,
        state_code=state,
        gstin=gstin,
    )
    customers = {
        code: sales.create_customer(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            code=code,
            name=name,
            kind=kind,
            state_code=state,
            gstin=gstin,
        )
        for code, name, kind, state, gstin in CUSTOMERS
    }
    return Section5(organization_id, ids, stock_units, supplier, customers)


def post_section5_opening(
    session: Session, oracle: dict[str, Any], s5: Section5, actor_id: uuid.UUID | None = None
) -> uuid.UUID:
    """J0: opening stock at the input rates; the 50 opening packets (lot OPEN-LOT) at standard cost (A1)."""
    opening = oracle["inputs"]["opening_stock"]
    std = section5_standard_cost(oracle)
    open_lot = ledger.create_lot(
        session,
        organization_id=s5.organization_id,
        actor_id=actor_id,
        item_id=s5.item_ids[FINISHED],
        lot_no="OPEN-LOT",
        source_type="opening",
    )
    lines = []
    for code, (_, store) in ITEMS.items():
        rate = opening[code]["rate"]
        lines.append(
            OpeningLine(
                item_id=s5.item_ids[code],
                location=store,
                qty=Decimal(opening[code]["qty"]),
                unit=opening[code]["unit"],
                rate=std.per_unit if rate is None else Decimal(rate),  # A1: no NIT cost for FG -> standard
                lot_id=open_lot if code == FINISHED else None,
            )
        )
    return valuation.post_opening(
        session, organization_id=s5.organization_id, actor_id=actor_id, posting_date=POSTING_DATE, lines=lines
    ).journal_id


def _move(
    item_id: uuid.UUID, src: str, dst: str, qty: Decimal, unit_code: str, value: Decimal, lot: uuid.UUID | None = None
) -> list[LineSpec]:
    return [LineSpec(item_id, dst, qty, unit_code, value, lot), LineSpec(item_id, src, -qty, unit_code, -value, lot)]


def replay_stock(session: Session, oracle: dict[str, Any]) -> StockReplay:
    """Post J0-J3 for a fresh BENCHMARK tenant, commit, and return what the benchmark checks."""
    inputs = oracle["inputs"]
    steps = inputs["steps"]
    bom_units = {line["item"]: line["unit"] for line in inputs["bom_murukku_200g_per_batch"]["lines"]}

    org = identity.create_scratch_tenant(session, kind="BENCHMARK", label="NIT")
    s5 = setup_section5(session, oracle, org)
    ids = s5.item_ids
    units = catalog.units_for(session, ids.values())
    replay = StockReplay(org, ids, s5.stock_units, section5_standard_cost(oracle))
    replay.journals["J0 opening"] = post_section5_opening(session, oracle, s5)

    # J1 step 1: purchase, as a purchase receipt document
    buy = steps["1_purchase"]
    receipt = procurement.post_receipt(
        session,
        organization_id=org,
        actor_id=None,
        supplier_id=s5.supplier_id,
        supplier_invoice_ref="DEMO-INV-0001",
        received_on=POSTING_DATE,
        lines=[ReceiptLineIn(ids[buy["item"]], Decimal(buy["qty"]), buy["unit"], Decimal(buy["rate"]))],
    )
    replay.journals["J1 purchase"] = receipt.journal_id
    replay.receipt_no = receipt.receipt_no
    replay.flour_wac_after_purchase = valuation.wac(session, ids["flour"])

    # J2 step 2: issue to batch B-001 at WAC (units as in the recipe)
    issued = {code: Decimal(qty) for code, qty in steps["2_issue"].items()}
    flour_issue = to_base(issued["flour"], bom_units["flour"], units[ids["flour"]])
    replay.flour_issue_sensitivity = valuation.sensitivity(session, ids["flour"], flour_issue)
    j2: list[LineSpec] = []
    for code, qty in issued.items():
        value = valuation.issue_value(
            session,
            organization_id=org,
            item_id=ids[code],
            qty_base=to_base(qty, bom_units[code], units[ids[code]]),
            from_location=ITEMS[code][1],
        )
        j2 += _move(ids[code], ITEMS[code][1], "WIP", qty, bom_units[code], value)
    replay.journals["J2 issue"] = ledger.post(
        session,
        organization_id=org,
        actor_id=None,
        kind="ISSUE",
        source_type="material_issue",
        source_id=uuid.uuid4(),
        posting_date=POSTING_DATE,
        lines=j2,
    ).journal_id

    # J3 step 3 (stand-in for MP06): inputs consumed at book value; pouches used = good + damaged (damaged to SCRAP
    # at no value, ADR-0002); the batch lot B-001 carries the sum.
    out = steps["3_output"]
    good, damaged, cartons = Decimal(out["good_packets"]), Decimal(out["damaged_pouches"]), Decimal(out["cartons_used"])
    batch = ledger.create_lot(
        session,
        organization_id=org,
        actor_id=None,
        item_id=ids[FINISHED],
        lot_no="B-001",
        source_type="production_run",
        source_id=uuid.uuid4(),
    )
    j3: list[LineSpec] = []
    total = Decimal(0)
    for code, qty in issued.items():
        value = valuation.issue_value(
            session,
            organization_id=org,
            item_id=ids[code],
            qty_base=to_base(qty, bom_units[code], units[ids[code]]),
            from_location="WIP",
        )
        total += value
        j3 += _move(ids[code], "WIP", "PRODUCTION", qty, bom_units[code], value)
    pouch_value = valuation.issue_value(
        session, organization_id=org, item_id=ids[POUCH], qty_base=good + damaged, from_location="PACK_STORE"
    )
    carton_value = valuation.issue_value(
        session, organization_id=org, item_id=ids[CARTON], qty_base=cartons, from_location="PACK_STORE"
    )
    total += pouch_value + carton_value
    j3 += [
        LineSpec(ids[POUCH], "PRODUCTION", good, "piece", pouch_value),
        LineSpec(ids[POUCH], "SCRAP", damaged, "piece"),
        LineSpec(ids[POUCH], "PACK_STORE", -(good + damaged), "piece", -pouch_value),
    ]
    j3 += _move(ids[CARTON], "PACK_STORE", "PRODUCTION", cartons, "piece", carton_value)
    j3 += _move(ids[FINISHED], "PRODUCTION", "FG_STORE", good, "packet", total, batch)
    replay.journals["J3 run output (stand-in)"] = ledger.post(
        session,
        organization_id=org,
        actor_id=None,
        kind="RUN_COMPLETION",
        source_type="production_run",
        source_id=uuid.uuid4(),
        posting_date=POSTING_DATE,
        lines=j3,
    ).journal_id

    session.commit()

    by_id = {str(i): c for c, i in ids.items()}
    for row in ledger.balances(session, include_virtual=True):
        code = by_id[row["item_id"]]
        key = (code, row["location"])
        qty = from_base(Decimal(row["qty_base"]), s5.stock_units[code], units[ids[code]])
        replay.closing[key] = replay.closing.get(key, Decimal(0)) + qty
        replay.closing_value[key] = replay.closing_value.get(key, Decimal(0)) + Decimal(row["value"])
    return replay
