import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet, apiPost } from "../lib/api";
import { formatValue } from "../lib/format";
import type { DispatchPreview, DispatchView, InvoiceView } from "./billingTypes";

const money = (v: string) => formatValue(v, "INR");

/** One invoice: the tax breakup, print / share, dispatch with a stock-movement preview, credit note, cancel. */
export function InvoicePage() {
  const { invoiceId = "" } = useParams();
  const [inv, setInv] = useState<InvoiceView | null>(null);
  const [dispatches, setDispatches] = useState<DispatchView[]>([]);
  const [preview, setPreview] = useState<DispatchPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [credit, setCredit] = useState({ qty: "", rate: "", reason: "" });

  const load = useCallback(async () => {
    const [v, d] = await Promise.all([
      apiGet<InvoiceView>(`/api/invoices/${encodeURIComponent(invoiceId)}`),
      apiGet<{ dispatches: DispatchView[] }>(
        `/api/invoices/${encodeURIComponent(invoiceId)}/dispatches`,
      ),
    ]);
    setInv(v);
    setDispatches(d.dispatches);
  }, [invoiceId]);

  useEffect(() => {
    load().catch((e) =>
      setError(e instanceof ApiError ? e.message : "Could not load the invoice."),
    );
  }, [load]);

  async function run(fn: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      setDone(await fn());
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The factory server did not answer. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!inv) {
    return (
      <section className="admin-page">
        <p className="muted small">
          <Link to="/admin/invoices">← Invoices</Link>
        </p>
        {error ? <p className="alert">{error}</p> : <p className="muted">Loading…</p>}
      </section>
    );
  }

  const posted = inv.status === "POSTED";
  const invoiced = inv.lines.reduce((n, l) => n + Number(l.qty), 0);
  const sent = inv.lines.reduce((n, l) => n + Number(l.dispatched), 0);
  const left = invoiced - sent;
  const share = `Invoice ${inv.invoice_no} from ${inv.supplier.name}: ${money(inv.total)}, due ${inv.due_date}. (DEMO)`;

  return (
    <section className="admin-page">
      <p className="muted small">
        <Link to="/admin/invoices">← Invoices</Link>
      </p>
      <h1>
        {inv.invoice_no} · {inv.customer.name}
      </h1>
      <p className="chips">
        {posted ? (
          <StatusChip tone="ok">Posted</StatusChip>
        ) : (
          <StatusChip tone="bad">Cancelled</StatusChip>
        )}
        {posted && left === 0 && <StatusChip tone="ok">Dispatched</StatusChip>}
        {posted && left > 0 && <StatusChip tone="todo">{`${left} packets to dispatch`}</StatusChip>}
      </p>
      <p className="muted small">
        {inv.invoice_date} · order {inv.order_no} · place of supply {inv.place_of_supply} ·{" "}
        {inv.regime === "INTRA" ? "CGST + SGST" : "IGST"} · due {inv.due_date}
      </p>
      {done && (
        <p className="banner banner-ok" role="status">
          <span aria-hidden="true">✓</span> {done}
        </p>
      )}
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <div className="table-wrap">
        <table className="lines">
          <thead>
            <tr>
              <th scope="col">Product</th>
              <th scope="col">HSN</th>
              <th scope="col" className="num">
                Packets
              </th>
              <th scope="col" className="num">
                Rate
              </th>
              <th scope="col" className="num">
                Taxable
              </th>
              <th scope="col">Tax</th>
            </tr>
          </thead>
          <tbody>
            {inv.lines.map((l) => (
              <tr key={l.line_no}>
                <td>{l.item_name}</td>
                <td>{l.hsn}</td>
                <td className="num">{l.qty}</td>
                <td className="num">{money(l.rate)}</td>
                <td className="num">{money(l.taxable)}</td>
                <td>
                  {l.taxes.map((t) => `${t.tax} ${t.rate_pct}% ${money(t.amount)}`).join(" · ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="totals-list">
        <div>
          <dt>Taxable value</dt>
          <dd>{money(inv.taxable)}</dd>
        </div>
        {Object.entries(inv.by_tax).map(([head, amount]) => (
          <div key={head}>
            <dt>{head}</dt>
            <dd>{money(amount)}</dd>
          </div>
        ))}
        <div className="grand">
          <dt>Invoice total</dt>
          <dd>{money(inv.total)}</dd>
        </div>
        <div>
          <dt>Paid / credited</dt>
          <dd>
            {money(inv.paid)} / {money(inv.credited)}
          </dd>
        </div>
        <div className="grand">
          <dt>Still owed</dt>
          <dd>{money(inv.outstanding)}</dd>
        </div>
      </dl>
      <p className="muted small">{inv.amount_in_words}</p>

      <div className="actions-row">
        <a
          className="btn btn-primary"
          href={`/api/invoices/${inv.id}/document`}
          target="_blank"
          rel="noreferrer"
        >
          Open printable invoice (PDF)
        </a>
        <a
          className="btn"
          href={`https://wa.me/?text=${encodeURIComponent(share)}`}
          target="_blank"
          rel="noreferrer"
        >
          Share on WhatsApp
        </a>
        <a
          className="btn"
          href={`mailto:?subject=${encodeURIComponent(`Invoice ${inv.invoice_no}`)}&body=${encodeURIComponent(share)}`}
        >
          Email
        </a>
      </div>
      <p className="muted small">
        The share links carry a text summary only; attach the PDF yourself.
      </p>

      {posted && left > 0 && (
        <>
          <h2>Dispatch</h2>
          <p className="muted">
            Packets leave oldest batch first (first expiry, first out). Check the stock movement
            before you post it.
          </p>
          {!preview ? (
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  setPreview(
                    await apiPost<DispatchPreview>(`/api/invoices/${inv.id}/dispatch-preview`, {}),
                  );
                  return "Preview ready: nothing has moved yet.";
                })
              }
            >
              Preview the dispatch of {left} packets
            </button>
          ) : (
            <div className="option">
              <h3>Stock movement</h3>
              <ul>
                {preview.lines.flatMap((l) =>
                  l.picks.map((p) => (
                    <li key={`${l.item_id}-${p.lot_no}`}>
                      {l.item_name}: {p.qty} packets from batch <strong>{p.lot_no}</strong> (cost{" "}
                      {money(p.value)})
                    </li>
                  )),
                )}
              </ul>
              <p className="small">
                Cost of goods leaving: {money(preview.cost_of_goods)} · consignment value with tax{" "}
                {money(preview.consignment_value)}
              </p>
              <p>
                {preview.eway.required ? (
                  <StatusChip tone="warn">e-Way Bill required</StatusChip>
                ) : (
                  <StatusChip tone="ok">e-Way Bill not required</StatusChip>
                )}{" "}
                <span className="small">{preview.eway.reason} (MOCK check, nothing is sent)</span>
              </p>
              <div className="actions-row">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      const d = await apiPost<DispatchView>(`/api/invoices/${inv.id}/dispatch`, {});
                      setPreview(null);
                      return `Dispatched as ${d.dispatch_no}.`;
                    })
                  }
                >
                  Record dispatch
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setPreview(null)}>
                  Not now
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {dispatches.length > 0 && (
        <>
          <h2>Dispatched</h2>
          <ul className="order-list">
            {dispatches.map((d) => (
              <li key={d.id} className="order-row">
                <strong>
                  {d.dispatch_no} · {d.dispatch_date}
                </strong>
                <span className="small">
                  {d.lines.map((l) => `${l.qty} from ${l.lot_no}`).join(", ")} · e-Way Bill{" "}
                  {d.eway.required ? "required" : "not required"} (mock)
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {posted && (
        <details className="more">
          <summary>Credit note (price correction, discount, short supply)</summary>
          <div className="actions-row">
            <label className="field">
              Packets
              <input
                inputMode="numeric"
                value={credit.qty}
                onChange={(e) => setCredit({ ...credit, qty: e.target.value })}
              />
            </label>
            <label className="field">
              Rupees per packet
              <input
                inputMode="decimal"
                value={credit.rate}
                onChange={(e) => setCredit({ ...credit, rate: e.target.value })}
              />
            </label>
          </div>
          <label className="field">
            Reason
            <input
              value={credit.reason}
              onChange={(e) => setCredit({ ...credit, reason: e.target.value })}
            />
          </label>
          <button
            type="button"
            className="btn"
            disabled={busy || !credit.qty || !credit.rate || credit.reason.trim().length < 3}
            onClick={() =>
              void run(async () => {
                const r = await apiPost<InvoiceView>(`/api/invoices/${inv.id}/credit-notes`, {
                  reason: credit.reason,
                  lines: [{ line_no: 1, qty: credit.qty, rate: credit.rate }],
                });
                setCredit({ qty: "", rate: "", reason: "" });
                return `Credit note ${r.credit_note_no ?? ""} posted.`;
              })
            }
          >
            Post credit note
          </button>
        </details>
      )}

      {posted && sent === 0 && (
        <details className="more">
          <summary>Cancel this invoice (only before dispatch)</summary>
          <label className="field">
            Reason
            <input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} />
          </label>
          <button
            type="button"
            className="btn btn-danger"
            disabled={busy || cancelReason.trim().length < 3}
            onClick={() =>
              void run(async () => {
                await apiPost(`/api/invoices/${inv.id}/cancel`, { reason: cancelReason });
                return "Invoice cancelled. The order is back to approved and its stock stays held.";
              })
            }
          >
            Cancel invoice
          </button>
        </details>
      )}
      {inv.credit_notes.length > 0 && (
        <>
          <h2>Credit notes</h2>
          <ul>
            {inv.credit_notes.map((n) => (
              <li key={n.id}>
                {n.credit_note_no} · {n.note_date} · {money(n.total)} · {n.reason}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
