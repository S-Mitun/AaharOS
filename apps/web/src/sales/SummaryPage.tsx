import { useEffect, useState } from "react";
import { Num } from "../components/Num";
import { apiGet } from "../lib/api";
import type { Explained } from "../lib/explained";
import { formatValue } from "../lib/format";

interface Summary {
  days: number;
  since: string;
  customers: {
    customer_id: string;
    customer_name: string;
    orders: number;
    packets: string;
    value_ex_tax: string;
  }[];
  total_ex_tax: Explained;
  note: string;
}

/** Per customer, last 30 days: orders, packets and value ex-tax, labelled "ordered, not invoiced". */
export function SummaryPage() {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    apiGet<Summary>("/api/sales/summary")
      .then((s) => live && setData(s))
      .catch(() => live && setError("The summary needs a connection."));
    return () => {
      live = false;
    };
  }, []);

  return (
    <section className="sales-page">
      <h1>Summary</h1>
      {error && <p className="alert">{error}</p>}
      {!data && !error && <p className="muted">Loading…</p>}
      {data && (
        <>
          <p className="muted">
            Last {data.days} days. <strong>Ordered, not invoiced:</strong> these are order values
            before GST, not sales.
          </p>
          <div className="kpi">
            <span className="muted small">Total ordered, ex-tax</span>
            <Num value={data.total_ex_tax} label="Total ordered, ex-tax" className="kpi-value" />
          </div>
          {data.customers.length === 0 ? (
            <p className="muted">No orders yet.</p>
          ) : (
            <table className="lines">
              <thead>
                <tr>
                  <th scope="col">Customer</th>
                  <th scope="col" className="num">
                    Orders
                  </th>
                  <th scope="col" className="num">
                    Packets
                  </th>
                  <th scope="col" className="num">
                    Value ex-tax
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.customers.map((c) => (
                  <tr key={c.customer_id}>
                    <td>{c.customer_name}</td>
                    <td className="num">{c.orders}</td>
                    <td className="num">{c.packets}</td>
                    <td className="num">{formatValue(c.value_ex_tax, "INR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  );
}
