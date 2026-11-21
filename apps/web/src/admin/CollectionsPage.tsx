import { useEffect, useState } from "react";
import { Num } from "../components/Num";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet, apiPost } from "../lib/api";
import { formatValue } from "../lib/format";
import type { CollectionRow, Statement } from "./billingTypes";

const money = (v: string) => formatValue(v, "INR");
/** Zero by value, not by text ("0", "0.00" and "-0.00" are all zero). */
const isZero = (v: string) => /^-?0*(\.0*)?$/.test(v);

/** Collections (MP10): what each customer owes and what is overdue; record a payment (oldest invoice first). */
export function CollectionsPage() {
  const [rows, setRows] = useState<CollectionRow[] | null>(null);
  const [total, setTotal] = useState("0.00");
  const [selected, setSelected] = useState<string | null>(null);
  const [statement, setStatement] = useState<Statement | null>(null);
  const [form, setForm] = useState({ amount: "", mode: "UPI", reference: "" });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh(customer: string | null) {
    const o = await apiGet<{ customers: CollectionRow[]; total_outstanding: string }>(
      "/api/collections",
    );
    setRows(o.customers);
    setTotal(o.total_outstanding);
    if (customer) setStatement(await apiGet<Statement>(`/api/customers/${customer}/statement`));
  }

  useEffect(() => {
    refresh(null).catch(() => setError("Could not load collections."));
  }, []);

  async function open(customer: string) {
    setSelected(customer);
    setDone(null);
    setError(null);
    setStatement(await apiGet<Statement>(`/api/customers/${customer}/statement`));
  }

  async function pay() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const r = await apiPost<Statement>("/api/payments", {
        customer_id: selected,
        amount: form.amount,
        mode: form.mode,
        reference: form.reference || null,
      });
      setDone(`Payment ${r.payment_no ?? ""} recorded and allocated, oldest invoice first.`);
      setForm({ amount: "", mode: "UPI", reference: "" });
      await refresh(selected);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The factory server did not answer.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="admin-page">
      <h1>Collections</h1>
      <p className="muted">
        What each customer owes: invoice totals minus payments and credit notes. Total owed:{" "}
        <strong>{money(total)}</strong>.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {!rows && !error && <p className="muted">Loading…</p>}
      <ul className="order-list">
        {rows?.map((c) => (
          <li key={c.customer_id} className={`order-row${!isZero(c.overdue) ? " short" : ""}`}>
            <button
              type="button"
              className="order-row-main as-button"
              onClick={() => void open(c.customer_id)}
            >
              <strong>{c.customer_name}</strong>
              <span className="small">
                owes {money(c.outstanding)}
                {!isZero(c.advance) ? ` · advance ${money(c.advance)}` : ""}
              </span>
              <span className="chips">
                {!isZero(c.overdue) ? (
                  <StatusChip tone="bad">{`Overdue ${money(c.overdue)}`}</StatusChip>
                ) : !isZero(c.outstanding) ? (
                  <StatusChip tone="todo">Not yet due</StatusChip>
                ) : (
                  <StatusChip tone="ok">Nothing owed</StatusChip>
                )}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {statement && (
        <>
          <h2>{statement.customer.name}</h2>
          <p>
            Outstanding <Num value={statement.outstanding} label="Outstanding" />
            {!isZero(statement.advance) && <> · advance held {money(statement.advance)}</>} · terms{" "}
            {statement.customer.payment_terms_days} days
            {statement.customer.msme_terms ? " (MSME: at most 45 days)" : ""}
          </p>
          {done && (
            <p className="banner banner-ok" role="status">
              <span aria-hidden="true">✓</span> {done}
            </p>
          )}
          <div className="table-wrap">
            <table className="lines">
              <thead>
                <tr>
                  <th scope="col">Invoice</th>
                  <th scope="col">Due</th>
                  <th scope="col" className="num">
                    Total
                  </th>
                  <th scope="col" className="num">
                    Paid
                  </th>
                  <th scope="col" className="num">
                    Owed
                  </th>
                </tr>
              </thead>
              <tbody>
                {statement.invoices.map((i) => (
                  <tr key={i.invoice_id}>
                    <td>{i.invoice_no}</td>
                    <td>
                      {i.due_date}
                      {i.overdue && (
                        <span className="bad small"> · {i.days_overdue} days overdue</span>
                      )}
                    </td>
                    <td className="num">{money(i.total)}</td>
                    <td className="num">{money(i.paid)}</td>
                    <td className="num">{money(i.outstanding)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>Record a payment</h3>
          <div className="actions-row">
            <label className="field">
              Amount (₹)
              <input
                inputMode="decimal"
                value={form.amount}
                onChange={(e) => setForm({ ...form, amount: e.target.value })}
              />
            </label>
            <label className="field">
              Mode
              <select
                value={form.mode}
                onChange={(e) => setForm({ ...form, mode: e.target.value })}
              >
                <option>UPI</option>
                <option>CASH</option>
                <option>BANK</option>
                <option>CHEQUE</option>
              </select>
            </label>
            <label className="field">
              Reference
              <input
                value={form.reference}
                onChange={(e) => setForm({ ...form, reference: e.target.value })}
              />
            </label>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !/^\d+(\.\d{1,2})?$/.test(form.amount)}
            onClick={() => void pay()}
          >
            Record payment
          </button>
          <p className="muted small">
            It is applied to the oldest unpaid invoice first; anything left is kept as an advance.
          </p>
        </>
      )}
    </section>
  );
}
