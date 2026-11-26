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
  - J8 step 8: labour 1,200 and gas/power 600 as run costs (value-only true-ups), then the costs finalised
  - (MP08) steps 4 and 6 as SUBMITTED orders priced from the DEMO general price list v1 (Retailer A 150, Distributor
    B 120), ready for approval in MP09. BENCHMARK tenants have no logins, so the orders carry no salesman.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core import effective_settings
from app.core.errors import DomainError
from app.core.explained import Explained
from app.modules.audit import service as audit
from app.modules.billing import service as billing
from app.modules.catalog import service as catalog
from app.modules.collections import service as collections
from app.modules.costing import service as costing
from app.modules.costing.domain import StandardCost, StandardLine, standard_cost
from app.modules.costing.service import RunCosting
from app.modules.dispatch import service as dispatch
from app.modules.identity import service as identity
from app.modules.ledger import service as ledger
from app.modules.planning import service as planning
from app.modules.procurement import service as procurement
from app.modules.procurement.domain import ReceiptLineIn
from app.modules.production import service as production
from app.modules.production.domain import TOLERANCE_SETTING
from app.modules.production.service import RunAnalysis
from app.modules.recipe import service as recipes
from app.modules.recipe.domain import PackLineIn, RecipeLineIn
from app.modules.reports import close
from app.modules.sales import service as sales
from app.modules.sales.domain import OrderLineIn
from app.modules.tax import service as tax
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
# MP09 (H7): fictional DEMO credit limits in rupees; NIT gives none. 0 would mean "no limit set".
CREDIT_LIMITS: Final[dict[str, Decimal]] = {"RET-A": Decimal("25000.00"), "DIST-B": Decimal("100000.00")}
PAYMENT_TERMS_DAYS: Final = 30  # MP10 (J8): fictional DEMO terms; MSME terms cap them at 45 days

# MP10 (J1, J5): DEMO tax and business identity as effective-dated settings. The HSN and rate must be verified with a
# chartered accountant; the rate itself comes from the oracle's config (gst_rate_percent), never from code.
HSN_NAMKEEN: Final = "21069099"
GST_RATE_FROM: Final = date(2025, 9, 22)
DEMO_PROFILE: Final[dict[str, str]] = {
    "org.gstin": "33DEMOX0000X1Z0",
    "org.fssai_no": "10000000000000 (DEMO)",
    "org.udyam_no": "UDYAM-TN-00-0000000 (DEMO)",
    "org.address": "DEMO address, Tiruchirappalli, Tamil Nadu 620001",
    "org.upi_vpa": "demo-not-real@aaharos",
}
B2CL_THRESHOLD_DEMO: Final = Decimal("100000.00")  # MP11: GSTR-1 table 5 cut-off (verify the current figure)
EWAY_THRESHOLD_DEMO: Final = Decimal("50000.00")  # Rule 138; the intra-state figure varies by state: verify


@dataclass
class Section5:
    organization_id: uuid.UUID
    item_ids: dict[str, uuid.UUID]
    stock_units: dict[str, str]
    supplier_id: uuid.UUID
    customer_ids: dict[str, uuid.UUID]
    recipe_version_id: uuid.UUID
    pack_versions: dict[str, uuid.UUID]  # pack spec code -> its ACTIVE version
    price_list_id: uuid.UUID | None = None  # MP08: the DEMO general price list v1


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
    orders: dict[str, str] = field(default_factory=dict)  # step -> SO number (MP08)
    order_ids: dict[str, uuid.UUID] = field(default_factory=dict)  # step -> sales order id
    b_card: dict[str, Any] | None = None  # MP09: Distributor B's inbox card after Retailer A's approval
    b_full_refusal: str | None = None  # MP09: the code a full approval of B is refused with
    fg_after_run: Decimal | None = None  # FG on hand right after B-001 completes (row 4; the replay goes on)
    invoice_a_id: uuid.UUID | None = None  # MP10
    dispatch_a_id: uuid.UUID | None = None
    invoice_a: dict[str, Any] | None = None  # the invoice view (rows 8-11)
    dispatch_a: dict[str, Any] | None = None  # the dispatch view (row 21: lots)
    statement_a: dict[str, Any] | None = None  # Retailer A's statement after the payment (row 12)
    b001_lot: dict[str, tuple[Decimal, Decimal]] = field(default_factory=dict)  # location -> (qty, value) (row 22)
    integrity: list[dict[str, Any]] = field(default_factory=list)  # MP11: the tenant's 8 integrity checks (row 26)
    runway: list[dict[str, Any]] = field(default_factory=list)  # MP12: material runway per pack (row 24)
    b_attribution: dict[str, Any] | None = None  # MP12: Distributor B's shortage attribution (row 23)
    closing: dict[tuple[str, str], Decimal] = field(default_factory=dict)  # (item, store) -> qty in stock unit
    closing_value: dict[tuple[str, str], Decimal] = field(default_factory=dict)  # (item, location) -> rupees
    run_id: uuid.UUID | None = None
    run: RunAnalysis | None = None  # B-001's variances, packing and mass balance, computed from its snapshot
    costing: RunCosting | None = None  # B-001's run cost, cost per packet, waterfall and sensitivity (MP07)

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
            credit_limit=CREDIT_LIMITS[code],
            payment_terms_days=PAYMENT_TERMS_DAYS,
            msme_terms=True,
        )
        for code, name, kind, state, gstin in CUSTOMERS
    }
    recipe_version, pack_versions = setup_section5_bom(session, oracle, organization_id, ids, actor_id)
    price_list = setup_section5_price_list(session, oracle, organization_id, ids, actor_id)
    setup_section5_tax(session, oracle, organization_id, ids, actor_id)
    return Section5(organization_id, ids, stock_units, supplier, customers, recipe_version, pack_versions, price_list)


PRICE_LIST_CODE: Final = "GENERAL"


def setup_section5_price_list(
    session: Session,
    oracle: dict[str, Any],
    organization_id: uuid.UUID,
    ids: dict[str, uuid.UUID],
    actor_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """MP08 (G1): the DEMO general price list v1 with the 200 g pack at the inputs' `selling_price_ex_tax`. The
    inputs give no 500 g price, so the 500 g pack is not on it."""
    return sales.create_price_list(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        code=PRICE_LIST_CODE,
        effective_from=SETTINGS_FROM,
        items={ids[FINISHED]: Decimal(str(oracle["inputs"]["selling_price_ex_tax"])).quantize(Decimal("0.01"))},
    )


def setup_section5_tax(
    session: Session,
    oracle: dict[str, Any],
    organization_id: uuid.UUID,
    ids: dict[str, uuid.UUID],
    actor_id: uuid.UUID | None = None,
) -> None:
    """MP10: HSN on the finished goods, the GST rule at the oracle's `gst_rate_percent`, the DEMO business profile,
    e-way bill thresholds and no rupee round-off, all effective-dated."""
    for code in (FINISHED, "murukku_500g"):
        if code in ids:
            catalog.set_hsn(
                session, organization_id=organization_id, actor_id=actor_id, item_id=ids[code], hsn=HSN_NAMKEEN
            )
    tax.create_rule(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        hsn=HSN_NAMKEEN,
        rate_pct=Decimal(str(oracle["gst_rate_percent"])),
        effective_from=GST_RATE_FROM,
        note="DEMO: pre-packaged namkeen; verify HSN and rate with a chartered accountant",
    )
    settings: dict[str, Any] = {
        **DEMO_PROFILE,
        tax.EWAY_THRESHOLDS["INTER"]: EWAY_THRESHOLD_DEMO,
        tax.EWAY_THRESHOLDS["INTRA"]: EWAY_THRESHOLD_DEMO,
        tax.ROUND_TO_RUPEE: "false",
        "gst.b2cl_threshold": B2CL_THRESHOLD_DEMO,
        "bank.stock_margin_pct": Decimal("25"),  # MP11: DEMO drawing-power margins
        "bank.debtors_margin_pct": Decimal("40"),
        "planning.attribution_days": Decimal("30"),  # MP12: yield losses this recent explain a shortage
    }
    for key, value in settings.items():
        tax.put_setting(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            key=key,
            value=value,
            effective_from=SETTINGS_FROM,
        )


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

    # the 200 g standard cost card (decision F4): opening rates (A2), step 8's labour and gas as the conversion standard
    opening = oracle["inputs"]["opening_stock"]
    run_costs = oracle["inputs"]["steps"]["8_run_costs"]
    costing.create_card(
        session,
        organization_id=organization_id,
        actor_id=actor_id,
        pack_spec_version_id=versions[pack_code],
        effective_from=SETTINGS_FROM,
        rates={ids[ln["item"]]: Decimal(opening[ln["item"]]["rate"]) for ln in bom["lines"]},
        conversion={kind: Decimal(run_costs[kind]) for kind in ("labour", "gas_power")},
    )
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

    replay.fg_after_run = ledger.balance(session, ids[FINISHED], "FG_STORE")[0]

    # NIT's order from here (MP10): step 4 order A; step 5 approve (150 of 238 reserved), invoice and dispatch A
    # (J5, FEFO at lot value; B-001 still at its materials cost); step 6 order B; step 7 payment; step 8 run costs.
    assert s5.price_list_id is not None
    price_list_id = s5.price_list_id
    price = Decimal(str(inputs["selling_price_ex_tax"])).quantize(Decimal("0.01"))

    def place(step: str, customer: str) -> uuid.UUID:
        placed = sales.receive_order(
            session,
            organization_id=org,
            actor_id=None,
            customer_id=s5.customer_ids[customer],
            price_list_id=price_list_id,
            lines=[OrderLineIn(ids[FINISHED], int(steps[step]["qty"]), price)],
            order_date=POSTING_DATE,
        )
        replay.orders[step], replay.order_ids[step] = placed.order_no, placed.order_id
        return placed.order_id

    order_a = place("4_order_A", "RET-A")
    sales.approve_order(session, organization_id=org, actor_id=None, order_id=order_a)
    invoice_a = billing.create_invoice(
        session, organization_id=org, actor_id=None, order_id=order_a, invoice_date=POSTING_DATE
    )
    dispatched = dispatch.dispatch_invoice(
        session,
        organization_id=org,
        actor_id=None,
        invoice_id=invoice_a.invoice_id,
        qty={ids[FINISHED]: int(steps["5_invoice_A"]["dispatch_qty"])},
        dispatch_date=POSTING_DATE,
    )
    replay.journals["J5 dispatch A"] = dispatched.journal_id
    replay.invoice_a_id, replay.dispatch_a_id = invoice_a.invoice_id, dispatched.dispatch_id

    # step 6, the admin's view: B's card shows the shortage, and a full approval is refused with nothing written
    place("6_order_B", "DIST-B")
    try:
        with session.begin_nested():
            sales.approve_order(session, organization_id=org, actor_id=None, order_id=replay.order_ids["6_order_B"])
    except DomainError as exc:
        replay.b_full_refusal = exc.code

    # step 7: Retailer A pays, allocated to invoice A (oldest due first)
    collections.record_payment(
        session,
        organization_id=org,
        actor_id=None,
        customer_id=s5.customer_ids["RET-A"],
        amount=Decimal(str(steps["7_payment_A"]["amount"])),
        received_on=POSTING_DATE,
        mode="UPI",
        reference="DEMO-UPI-0001",
    )

    # J8 step 8: labour and gas/power for B-001, each a value-only COST_TRUE_UP spread over wherever the lot is now
    # (100 packets with the customer, 88 on hand), then FINAL (F1-F3)
    for kind, step_key in (("LABOUR", "labour"), ("GAS_POWER", "gas_power")):
        replay.journals[f"J8 {step_key}"] = production.record_run_cost(
            session,
            organization_id=org,
            actor_id=None,
            run_id=run_id,
            kind=kind,
            amount=Decimal(steps["8_run_costs"][step_key]),
            incurred_on=POSTING_DATE,
        ).journal_id
    production.finalise_costs(session, organization_id=org, actor_id=None, run_id=run_id)

    session.commit()
    replay.run = production.run_analysis(session, run_id)
    replay.costing = costing.run_costing(session, run_id)
    replay.b_card = sales.inbox_card(session, replay.order_ids["6_order_B"])
    replay.integrity = close.integrity_checks(session, org)  # row 26 (MP11)
    replay.runway = planning.runway(session)  # row 24 (MP12): after the run, before the next batch
    replay.b_attribution = planning.shortage_attribution(session, replay.order_ids["6_order_B"], POSTING_DATE)  # 23
    replay.invoice_a = billing.invoice_view(session, invoice_a.invoice_id)
    replay.dispatch_a = dispatch.dispatch_view(session, dispatched.dispatch_id)
    replay.statement_a = collections.statement(session, s5.customer_ids["RET-A"], on=POSTING_DATE)
    b001_no = replay.run.pack_lines[0].lot_no
    b001 = None if b001_no is None else ledger.lot_id_by_no(session, ids[FINISHED], b001_no)
    if b001 is not None:
        replay.b001_lot = {loc: (qty, value) for loc, qty, value in ledger.lot_positions(session, ids[FINISHED], b001)}

    by_id = {str(i): c for c, i in ids.items()}
    for row in ledger.balances(session, include_virtual=True):
        code = by_id[row["item_id"]]
        key = (code, row["location"])
        qty = from_base(Decimal(row["qty_base"]), s5.stock_units[code], units[ids[code]])
        replay.closing[key] = replay.closing.get(key, Decimal(0)) + qty
        replay.closing_value[key] = replay.closing_value.get(key, Decimal(0)) + Decimal(row["value"])
    return replay
