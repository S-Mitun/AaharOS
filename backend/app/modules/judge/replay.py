"""NIT section 5, posted through the real services. Reads only the oracle's `inputs` (and its
`variance_tolerance_percent` config), never its expected results.

- `setup_section5()`: master data (items, a DEMO supplier, Retailer A and Distributor B) for an organization, plus
  (MP06) the bulk item, recipe v1 from the BOM, the 200 g pack spec v1 used by the run, the 500 g pack spec v1 as seed
  data only (never part of the benchmark run), and the variance tolerance setting. Used by the replay,
  `make seed-benchmark` and `make seed-demo`.
- `post_section5_opening()`: J0, valued at the opening rates; the opening FG lot OPEN-LOT at the **standard cost**
  computed from the inputs (A1, A2, decision D3: 5,770.00 / 200 = 28.85 per packet, never copied from the oracle).
- `replay_stock()`: a fresh BENCHMARK tenant, then
  - J0 opening (valued)
  - J1 step 1 as a real purchase receipt (procurement, ₹45/kg)
  - run B-001 created and started: recipe and pack snapshots frozen with the tolerance in force on the run date
  - J2 step 2 as a real material issue for B-001 at WAC (production -> valuation)
  - J3 step 3 as the real `complete_run` of B-001: 188 good, 194 pouches used (6 damaged), 9 cartons
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.explained import Explained
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.costing.domain import StandardCost, StandardLine, standard_cost
from app.modules.identity import service as identity
from app.modules.ledger import service as ledger
from app.modules.procurement import service as procurement
from app.modules.procurement.domain import ReceiptLineIn
from app.modules.production import service as production
from app.modules.production.domain import TOLERANCE_SETTING
from app.modules.production.service import RunAnalysis
from app.modules.recipe import service as recipes
from app.modules.recipe.domain import PackLineIn, RecipeLineIn
from app.modules.sales import service as sales
from app.modules.uom.domain import BASE_UNIT, from_base, to_base, unit
from app.modules.valuation import service as valuation
from app.modules.valuation.service import OpeningLine

POSTING_DATE: Final = date(2026, 11, 21)  # fictional benchmark day
SETTINGS_FROM: Final = date(2026, 4, 1)  # DEMO configuration in force from the start of FY 2026-27

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

# MP06 master data with no opening stock: (kind, base unit, stock unit). The 500 g items are seed data only.
EXTRA_ITEMS: Final[dict[str, tuple[str, str, str]]] = {
    "murukku_bulk": ("BULK", "g", "kg"),
    "murukku_500g": ("FG", "piece", "packet"),
    "pouch_500g": ("PACK", "piece", "piece"),
}
RECIPE: Final = ("MURUKKU", "DEMO Murukku dough and fry", "murukku_bulk")
# Pack specs: code, name, FG item, net g per unit (master data: the pack size), DEMO shelf life in days.
PACK_200G: Final = ("MURUKKU-200G", "DEMO Murukku 200 g", FINISHED, Decimal(200), 90)
PACK_500G: Final = ("MURUKKU-500G", "DEMO Murukku 500 g", "murukku_500g", Decimal(500), 90)
UNITS_PER_CARTON_500G: Final = 10  # DEMO: the same outer carton holds 10 x 500 g, so 1/10 carton per packet is exact

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
    recipe_version_id: uuid.UUID
    pack_versions: dict[str, uuid.UUID]  # pack spec code -> its ACTIVE version


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
    run_id: uuid.UUID | None = None
    run: RunAnalysis | None = None  # B-001's variances, packing and mass balance, computed from its snapshot

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
    """Locations, items, the DEMO supplier and customers, and the BOM. The session must be scoped to the org."""
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
    for code, (kind, base, stock) in EXTRA_ITEMS.items():
        ids[code] = catalog.create_item(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            code=code,
            name=f"DEMO {code.replace('_', ' ')}",
            kind=kind,
            base_uom=base,
            stock_uom=stock,
            lot_tracked=kind == "FG",
        )
        stock_units[code] = stock
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
    recipe_version, pack_versions = setup_section5_bom(session, oracle, organization_id, ids, actor_id)
    return Section5(organization_id, ids, stock_units, supplier, customers, recipe_version, pack_versions)


def _cartons_per_batch(bom: dict[str, Any]) -> Decimal:
    """Cartons per batch from the BOM (assumption A5: a carton is a packaging item and a packing unit)."""
    return Decimal(next(ln["qty"] for ln in bom["lines"] if ln["item"] == CARTON))


def setup_section5_bom(
    session: Session,
    oracle: dict[str, Any],
    organization_id: uuid.UUID,
    ids: dict[str, uuid.UUID],
    actor_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """The two-level BOM from the inputs (ADR-0003):
    - recipe v1 with the PER_BATCH lines, bulk yield = expected good packets x net weight
    - the 200 g pack spec v1: PER_GOOD_UNIT qty = BOM qty per batch / expected good packets (pouch 1, carton 0.05),
      units per carton = expected good packets / cartons per batch (20)
    - the 500 g pack spec v1 as seed data (bom.md section 4: the interview change is data, not code)
    - the variance tolerance from the oracle's config, as an effective-dated setting
    Every version is activated. Returns (recipe version, {pack spec code: version})."""
    bom = oracle["inputs"]["bom_murukku_200g_per_batch"]
    expected = Decimal(bom["expected_good_output_packets"])
    tolerance = Decimal(oracle["variance_tolerance_percent"])
    setting_id = effective_settings.put(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        key=TOLERANCE_SETTING,
        value=tolerance,
        effective_from=SETTINGS_FROM,
    )
    audit.record(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        action="settings.put",
        entity_type="setting",
        entity_id=setting_id,
        after={"key": TOLERANCE_SETTING, "value": tolerance, "effective_from": SETTINGS_FROM},
    )
    by_driver: dict[str, list[dict[str, Any]]] = {}
    for line in bom["lines"]:
        by_driver.setdefault(line["driver"], []).append(line)

    code, name, bulk_item = RECIPE
    recipe_id = recipes.create_recipe(
        session, organization_id=organization_id, actor_id=actor_id, code=code, name=name, bulk_item_id=ids[bulk_item]
    )
    pack_code, pack_name, fg, net_g, shelf = PACK_200G
    recipe_version = recipes.create_recipe_version(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        recipe_id=recipe_id,
        bulk_yield_g=expected * net_g,  # assumption: bulk yield = expected good packets x net weight per packet
        effective_from=SETTINGS_FROM,
        lines=[RecipeLineIn(ids[ln["item"]], Decimal(ln["qty"]), ln["unit"]) for ln in by_driver["PER_BATCH"]],
    )
    recipes.activate_recipe_version(
        session, organization_id=organization_id, actor_id=actor_id, version_id=recipe_version
    )

    per_good_200 = {ln["item"]: Decimal(ln["qty"]) / expected for ln in by_driver["PER_GOOD_UNIT"]}
    per_good_500 = {"pouch_500g": Decimal(1), CARTON: Decimal(1) / UNITS_PER_CARTON_500G}
    specs = (
        (pack_code, pack_name, fg, net_g, shelf, int(expected / _cartons_per_batch(bom)), per_good_200),
        (*PACK_500G, UNITS_PER_CARTON_500G, per_good_500),
    )
    versions: dict[str, uuid.UUID] = {}
    for p_code, p_name, p_fg, p_net, p_shelf, per_carton, lines in specs:
        pack_id = recipes.create_pack_spec(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            code=p_code,
            name=p_name,
            recipe_id=recipe_id,
            fg_item_id=ids[p_fg],
        )
        version = recipes.create_pack_spec_version(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            pack_spec_id=pack_id,
            net_g=p_net,
            units_per_carton=per_carton,
            shelf_life_days=p_shelf,
            effective_from=SETTINGS_FROM,
            lines=[PackLineIn(ids[item], qty) for item, qty in lines.items()],
        )
        recipes.activate_pack_spec_version(
            session, organization_id=organization_id, actor_id=actor_id, version_id=version
        )
        versions[p_code] = version
    return recipe_version, versions


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


def replay_stock(session: Session, oracle: dict[str, Any]) -> StockReplay:
    """Post J0-J3 for a fresh BENCHMARK tenant through the real services, commit, and return what the benchmark
    checks."""
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

    # Run B-001: recipe v1 and the 200 g pack spec, frozen when it starts (all the expected bulk to its one pack line)
    run_id = production.create_run(
        session,
        organization_id=org,
        actor_id=None,
        recipe_version_id=s5.recipe_version_id,
        batch_multiplier=Decimal(1),
        run_date=POSTING_DATE,
        pack_lines=[production.PackLineRequest(s5.pack_versions[PACK_200G[0]])],
    )
    production.start_run(session, organization_id=org, actor_id=None, run_id=run_id)
    replay.run_id = run_id

    # J2 step 2: the material issue for B-001, at WAC (units as in the recipe)
    issued = {code: Decimal(qty) for code, qty in steps["2_issue"].items()}
    flour_issue = to_base(issued["flour"], bom_units["flour"], units[ids["flour"]])
    replay.flour_issue_sensitivity = valuation.sensitivity(session, ids["flour"], flour_issue)
    replay.journals["J2 issue"] = production.issue_materials(
        session,
        organization_id=org,
        actor_id=None,
        run_id=run_id,
        posting_date=POSTING_DATE,
        lines=[production.MaterialLineIn(ids[code], qty, bom_units[code]) for code, qty in issued.items()],
    ).journal_id

    # J3 step 3: the completion of B-001. Pouches used = good + damaged; the damaged go to SCRAP at no value.
    out = steps["3_output"]
    good, damaged, cartons = int(out["good_packets"]), Decimal(out["damaged_pouches"]), Decimal(out["cartons_used"])
    pack_line = production.run_analysis(session, run_id).pack_lines[0].pack_line_id
    replay.journals["J3 run completion"] = production.complete_run(
        session,
        organization_id=org,
        actor_id=None,
        run_id=run_id,
        posting_date=POSTING_DATE,
        results=[
            production.PackResultIn(
                pack_line_id=pack_line,
                good_units=good,
                packaging=[
                    production.PackagingIn(ids[POUCH], good + damaged, damaged, bom_units[POUCH]),
                    production.PackagingIn(ids[CARTON], cartons, Decimal(0), bom_units[CARTON]),
                ],
            )
        ],
    ).journal_id

    session.commit()
    replay.run = production.run_analysis(session, run_id)

    by_id = {str(i): c for c, i in ids.items()}
    for row in ledger.balances(session, include_virtual=True):
        code = by_id[row["item_id"]]
        key = (code, row["location"])
        qty = from_base(Decimal(row["qty_base"]), s5.stock_units[code], units[ids[code]])
        replay.closing[key] = replay.closing.get(key, Decimal(0)) + qty
        replay.closing_value[key] = replay.closing_value.get(key, Decimal(0)) + Decimal(row["value"])
    return replay
