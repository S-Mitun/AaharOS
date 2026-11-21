import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { loadCustomers, type Loaded } from "./api";
import { useOutbox } from "./outboxContext";
import type { Customer } from "./types";
import { OfflineCopy } from "./ui";

/** Today: the assigned customers in route order, each with New order and Repeat last order (G7).
 * `/sales/order` without a customer shows the same list, asking who the order is for. */
export function TodayPage({ picking = false }: { picking?: boolean }) {
  const outbox = useOutbox();
  const [loaded, setLoaded] = useState<Loaded<Customer[]> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    loadCustomers()
      .then((r) => live && setLoaded(r))
      .catch(
        () =>
          live && setError("Could not load your customers, and none are saved on this phone yet."),
      );
    return () => {
      live = false;
    };
  }, []);

  const waiting = outbox.entries.filter((e) => e.state !== "received").length;

  return (
    <section className="sales-page">
      <h1>{picking ? "Who is this order for?" : "Today's customers"}</h1>
      {!picking && (
        <p className="muted">
          In route order. Tap <strong>New order</strong>, or <strong>Repeat last order</strong> to
          start from what they took last time.
        </p>
      )}
      {waiting > 0 && (
        <p className="banner banner-info">
          <Link to="/sales/orders">
            {waiting} order{waiting === 1 ? " is" : "s are"} not with the factory yet → see My
            orders
          </Link>
        </p>
      )}
      {loaded?.offline && <OfflineCopy savedAt={loaded.savedAt} />}
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {!loaded && !error && <p className="muted">Loading…</p>}
      {loaded && loaded.data.length === 0 && (
        <p className="muted">No customers are assigned to you yet. Ask the factory admin.</p>
      )}
      <ol className="customer-list">
        {loaded?.data.map((c, i) => (
          <li key={c.id} className="customer-card">
            <span className="route-no" aria-label={`Stop ${c.route_order ?? i + 1}`}>
              {c.route_order ?? i + 1}
            </span>
            <div className="customer-main">
              <strong>{c.name}</strong>
              <span className="muted small">
                {c.kind === "DISTRIBUTOR" ? "Distributor" : "Retailer"} · state {c.state_code}
              </span>
            </div>
            <div className="customer-actions">
              <Link className="btn btn-primary" to={`/sales/order/${c.id}`}>
                New order
              </Link>
              <Link className="btn" to={`/sales/order/${c.id}?repeat=1`}>
                Repeat last order
              </Link>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
