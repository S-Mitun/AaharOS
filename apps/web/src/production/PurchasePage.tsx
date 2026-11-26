import { useEffect, useState, type FormEvent } from "react";
import { Num } from "../components/Num";
import { ApiError, apiGet, apiPost } from "../lib/api";
import type { Explained } from "../lib/explained";
import { words } from "../owner/planningTypes";

interface Supplier {
  id: string;
  code: string;
  name: string;
}
interface Balance {
  item_id: string;
  item_code: string;
  location: string;
  uom: string;
}
interface Valued {
  item_id: string;
  item_code: string;
  average_cost: Explained | null;
}
interface Line {
  item_id: string;
  qty: string;
  rate: string;
  lot_no: string;
}

const blank: Line = { item_id: "", qty: "", rate: "", lot_no: "" };

/**
 * Purchases → New receipt (MP15, NIT step 1): a delivery from a supplier, posted to stock at accepted qty x rate.
 * The supplier's lot number is recorded for traceability. After posting, the new average cost is shown with ⓘ.
 */
export function PurchasePage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [items, setItems] = useState<Balance[]>([]);
  const [supplier, setSupplier] = useState("");
  const [received, setReceived] = useState(() => new Date().toLocaleDateString("en-CA"));
  const [ref, setRef] = useState("");
  const [lines, setLines] = useState<Line[]>([blank]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [posted, setPosted] = useState<{ no: string; costs: Valued[] } | null>(null);

  useEffect(() => {
    apiGet<{ suppliers: Supplier[] }>("/api/suppliers")
      .then((r) => {
        setSuppliers(r.suppliers);
        setSupplier((s) => s || r.suppliers[0]?.id || "");
      })
      .catch(() => setError("Could not load the suppliers."));
    apiGet<{ balances: Balance[] }>("/api/stock/balances?include_zero=true")
      .then((r) => {
        const seen = new Map<string, Balance>();
        for (const b of r.balances)
          if ((b.location === "RAW_STORE" || b.location === "PACK_STORE") && !seen.has(b.item_id))
            seen.set(b.item_id, b);
        setItems([...seen.values()].sort((a, b) => a.item_code.localeCompare(b.item_code)));
      })
      .catch(() => setError("Could not load the materials."));
  }, []);

  const unitOf = (id: string) => items.find((i) => i.item_id === id)?.uom ?? "";
  const set = (n: number, patch: Partial<Line>) =>
    setLines(lines.map((l, i) => (i === n ? { ...l, ...patch } : l)));

  async function post(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await apiPost<{ receipt_no: string; lines: { item_id: string }[] }>(
        "/api/purchases/receipts",
        {
          supplier_id: supplier,
          supplier_invoice_ref: ref.trim() || null,
          received_on: received,
          lines: lines.map((l) => ({
            item_id: l.item_id,
            qty: l.qty,
            unit: unitOf(l.item_id),
            rate: l.rate,
            lot_no: l.lot_no.trim() || null,
          })),
        },
      );
      const ids = new Set(r.lines.map((l) => l.item_id));
      const v = await apiGet<{ items: Valued[] }>("/api/stock/valuation");
      setPosted({ no: r.receipt_no, costs: v.items.filter((i) => ids.has(i.item_id)) });
      setLines([blank]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The factory server did not answer.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="admin-page floor">
      <h1>New purchase receipt</h1>
      <p className="muted">
        What arrived from the supplier. It is added to stock at quantity × rate, and the average
        cost updates by itself. Record the supplier&apos;s lot number so a recall can find it.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {posted && (
        <div className="done" role="status">
          <p>
            Receipt <strong>{posted.no}</strong> posted.
          </p>
          {posted.costs.map((c) =>
            c.average_cost ? (
              <p key={c.item_id}>
                {words(c.item_code)} average cost now{" "}
                <Num value={c.average_cost} label={`average cost of ${words(c.item_code)}`} />
              </p>
            ) : null,
          )}
        </div>
      )}
      <form className="form floor-form" onSubmit={(e) => void post(e)}>
        <label>
          Supplier
          <select value={supplier} onChange={(e) => setSupplier(e.target.value)} required>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <div className="floor-row">
          <label>
            Received on
            <input type="date" value={received} onChange={(e) => setReceived(e.target.value)} />
          </label>
          <label>
            Supplier bill no. (optional)
            <input value={ref} maxLength={64} onChange={(e) => setRef(e.target.value)} />
          </label>
        </div>
        {lines.map((l, n) => (
          <fieldset key={n} className="floor-line">
            <legend>Item {n + 1}</legend>
            <label>
              Item
              <select
                required
                value={l.item_id}
                onChange={(e) => set(n, { item_id: e.target.value })}
              >
                <option value="">Choose…</option>
                {items.map((i) => (
                  <option key={i.item_id} value={i.item_id}>
                    {words(i.item_code)} ({i.uom})
                  </option>
                ))}
              </select>
            </label>
            <div className="floor-row">
              <label>
                Quantity {l.item_id && `(${unitOf(l.item_id)})`}
                <input
                  required
                  inputMode="decimal"
                  pattern="\d+(\.\d+)?"
                  value={l.qty}
                  onChange={(e) => set(n, { qty: e.target.value })}
                />
              </label>
              <label>
                Rate ₹ per {unitOf(l.item_id) || "unit"}
                <input
                  required
                  inputMode="decimal"
                  pattern="\d+(\.\d+)?"
                  value={l.rate}
                  onChange={(e) => set(n, { rate: e.target.value })}
                />
              </label>
              <label>
                Supplier lot no.
                <input
                  maxLength={64}
                  value={l.lot_no}
                  onChange={(e) => set(n, { lot_no: e.target.value })}
                />
              </label>
            </div>
          </fieldset>
        ))}
        <p className="actions-row">
          <button type="button" className="btn" onClick={() => setLines([...lines, blank])}>
            + Add item
          </button>
          {lines.length > 1 && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setLines(lines.slice(0, -1))}
            >
              Remove last item
            </button>
          )}
        </p>
        <div className="floor-bar">
          <button type="submit" className="btn btn-primary btn-lg" disabled={busy || !supplier}>
            {busy ? "Posting…" : "Post receipt"}
          </button>
        </div>
      </form>
    </section>
  );
}
