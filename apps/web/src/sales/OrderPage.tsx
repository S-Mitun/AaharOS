import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { packetsTimesPrice, sumRupees } from "../lib/decimal";
import { formatValue } from "../lib/format";
import { loadCatalog, loadCustomers, loadLastOrder, type Loaded } from "./api";
import { useOutbox } from "./outboxContext";
import type { Catalog, Customer, LastOrder } from "./types";
import { OfflineCopy, ProductArt, Stepper } from "./ui";

/**
 * The order screen: product pictures, a carton-aware stepper, last time's quantity, a sticky running total and
 * Save. Save always goes to the phone first (G5); the factory's acknowledgement comes later.
 * `?repeat=1` starts from the last order; `?edit=<id>` re-opens an order that needs attention (it is re-sent with a
 * new key).
 */
export function OrderPage() {
  const { customerId = "" } = useParams();
  const [params] = useSearchParams();
  const repeat = params.get("repeat") === "1";
  const editId = params.get("edit");
  const outbox = useOutbox();
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<Loaded<Catalog> | null>(null);
  const [last, setLast] = useState<LastOrder | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const editing = editId ? outbox.entries.find((e) => e.localId === editId) : undefined;

  useEffect(() => {
    let live = true;
    Promise.all([
      loadCatalog(customerId),
      loadLastOrder(customerId).catch(() => null),
      loadCustomers().catch(() => null),
    ])
      .then(([cat, lastOrder, customers]) => {
        if (!live) return;
        setCatalog(cat);
        setLast(lastOrder?.data ?? null);
        setCustomer(customers?.data.find((c) => c.id === customerId) ?? null);
      })
      .catch(
        () =>
          live &&
          setError(
            "This customer's price list is not on the phone yet. Connect once, then try again.",
          ),
      );
    return () => {
      live = false;
    };
  }, [customerId]);

  // Pre-fill: an order being edited, else the last order when repeating.
  useEffect(() => {
    if (editing) {
      setQty(Object.fromEntries(editing.lines.map((l) => [l.itemId, Number(l.qty)])));
    } else if (repeat && last) {
      setQty(Object.fromEntries(last.lines.map((l) => [l.item_id, Number(l.qty)])));
    }
  }, [editing, repeat, last]);

  const products = catalog?.data.products ?? [];
  const lastQty = useMemo(
    () => Object.fromEntries((last?.lines ?? []).map((l) => [l.item_id, l.qty])),
    [last],
  );
  const chosen = products.filter((p) => (qty[p.item_id] ?? 0) > 0);
  const packets = chosen.reduce((n, p) => n + (qty[p.item_id] ?? 0), 0);
  const total = sumRupees(
    chosen.map((p) => packetsTimesPrice(String(qty[p.item_id]), p.price_ex_tax)),
  );
  const priceList = catalog?.data.price_list;
  const customerName = customer?.name ?? editing?.customerName ?? "Customer";

  async function save() {
    if (!priceList || chosen.length === 0) return;
    setSaving(true);
    try {
      const localId = await outbox.save({
        customerId,
        customerName,
        priceListId: priceList.id,
        priceListLabel: `${priceList.code} v${priceList.version}`,
        lines: chosen.map((p) => ({
          itemId: p.item_id,
          name: p.name,
          qty: String(qty[p.item_id]),
          price: p.price_ex_tax,
        })),
      });
      if (editing) await outbox.discard(editing.localId);
      navigate(`/sales/orders/${localId}`, { replace: true });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="sales-page order-page">
      <p className="muted small">
        <Link to="/sales">← Today</Link>
      </p>
      <h1>{customerName}</h1>
      {editing && (
        <p className="banner banner-warn">
          Editing an order that needs attention. Saving sends it again as a new order.
        </p>
      )}
      {catalog?.offline && <OfflineCopy savedAt={catalog.savedAt} />}
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {!catalog && !error && <p className="muted">Loading products…</p>}
      {catalog && !priceList && <p className="alert">{catalog.data.note}</p>}
      {repeat && !last && catalog && (
        <p className="muted">No earlier order for this customer: start from zero.</p>
      )}

      <ul className="product-grid">
        {products.map((p) => {
          const n = qty[p.item_id] ?? 0;
          const avail = p.available_today;
          const short = avail !== null && n > Number(avail);
          return (
            <li key={p.item_id} className={`product-card${n > 0 ? " chosen" : ""}`}>
              <ProductArt code={p.code} name={p.name} />
              <div className="product-info">
                <strong>{p.name}</strong>
                <span>
                  {formatValue(p.price_ex_tax, "INR")}{" "}
                  <span className="muted small">/ packet ex-tax</span>
                </span>
                {lastQty[p.item_id] && (
                  <span className="muted small">Last time: {lastQty[p.item_id]} packets</span>
                )}
                {avail !== null && (
                  <span className={`small stock-hint ${short ? "warn" : "ok"}`}>
                    <span aria-hidden="true">{short ? "⚠" : "✓"}</span>{" "}
                    {short
                      ? `Only ${avail} available today (partial)`
                      : `In stock today (${avail} available)`}
                  </span>
                )}
              </div>
              <Stepper
                value={n}
                perCarton={p.units_per_carton}
                label={p.name}
                onChange={(v) => setQty((q) => ({ ...q, [p.item_id]: v }))}
              />
            </li>
          );
        })}
      </ul>

      <div className="order-bar" aria-live="polite">
        <div>
          <span className="muted small">
            {packets} packet{packets === 1 ? "" : "s"} · estimated, ex-tax
          </span>
          <strong className="order-total">{formatValue(total, "INR")}</strong>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-lg"
          disabled={saving || chosen.length === 0 || !priceList}
          onClick={() => void save()}
        >
          {saving ? "Saving…" : "Save order"}
        </button>
      </div>
      <p className="muted small">
        Prices come from the factory's price list (
        {priceList ? `${priceList.code} v${priceList.version}` : "—"}). GST is added on the invoice.
        The factory confirms the total when it receives the order.
      </p>
    </section>
  );
}
