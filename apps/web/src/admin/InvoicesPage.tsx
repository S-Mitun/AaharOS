import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet, apiPost } from "../lib/api";
import { formatValue } from "../lib/format";
import type { InvoiceRow, InvoiceView, ReadyOrder } from "./billingTypes";

/** Invoices and dispatch (MP10): approved orders ready to invoice, and every invoice with how much has left. */
export function InvoicesPage() {
  const navigate = useNavigate();
  const [ready, setReady] = useState<ReadyOrder[] | null>(null);
  const [rows, setRows] = useState<InvoiceRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      apiGet<{ orders: ReadyOrder[] }>("/api/invoices/ready"),
      apiGet<{ invoices: InvoiceRow[] }>("/api/invoices"),
    ])
      .then(([r, i]) => {
        if (!live) return;
        setReady(r.orders);
        setRows(i.invoices);
      })
      .catch(() => live && setError("Could not load invoices."));
    return () => {
      live = false;
    };
  }, []);

  async function invoice(orderId: string) {
    setBusy(orderId);
    setError(null);
    try {
      const inv = await apiPost<InvoiceView>(`/api/orders/${orderId}/invoice`, {});
      navigate(`/admin/invoices/${inv.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The factory server did not answer.");
      setBusy(null);
    }
  }

  return (
    <section className="admin-page">
      <h1>Invoices and dispatch</h1>
      <p className="muted">
        Approved orders become GST invoices here (CGST + SGST inside Tamil Nadu, IGST outside). Open
        an invoice to print it and to send the goods, oldest batch first.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <h2>Ready to invoice</h2>
      {!ready && !error && <p className="muted">Loading…</p>}
      {ready && ready.length === 0 && <p className="muted">No approved orders are waiting.</p>}
      <ul className="order-list">
        {ready?.map((o) => (
          <li key={o.order_id} className="order-row">
            <div className="order-row-main">
              <strong>{o.customer_name}</strong>
              <span className="small">
                {o.order_no} · {o.packets_to_invoice} packets · {formatValue(o.value_ex_tax, "INR")}{" "}
                ex-tax
              </span>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy !== null}
              onClick={() => void invoice(o.order_id)}
            >
              {busy === o.order_id ? "Creating…" : "Create invoice"}
            </button>
          </li>
        ))}
      </ul>

      <h2>Invoices</h2>
      {rows && rows.length === 0 && <p className="muted">No invoices yet.</p>}
      <ul className="order-list">
        {rows?.map((r) => (
          <li key={r.id} className="order-row">
            <Link to={`/admin/invoices/${r.id}`} className="order-row-main">
              <strong>
                {r.invoice_no} · {r.customer_name}
              </strong>
              <span className="small">
                {r.invoice_date} · {formatValue(r.total, "INR")} · due {r.due_date}
              </span>
              <span className="chips">
                {r.status === "CANCELLED" ? (
                  <StatusChip tone="bad">Cancelled</StatusChip>
                ) : r.dispatched === r.packets ? (
                  <StatusChip tone="ok">Dispatched</StatusChip>
                ) : r.dispatched === "0" ? (
                  <StatusChip tone="todo">To dispatch</StatusChip>
                ) : (
                  <StatusChip tone="warn">{`Part dispatched (${r.dispatched}/${r.packets})`}</StatusChip>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
