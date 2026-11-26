import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { StatusChip } from "../components/StatusChip";
import { apiGet } from "../lib/api";
import { expiresIn, type Freshness, type FreshnessRow } from "../trace/traceTypes";
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

  // MP13 (T5): the freshness chip. Online only; offline or without the setting the list simply has no chips.
  const [fresh, setFresh] = useState<Record<string, FreshnessRow>>({});
  useEffect(() => {
    let live = true;
    apiGet<Freshness>("/api/trace/freshness")
      .then((f) => {
        const first: Record<string, FreshnessRow> = {};
        for (const r of f.rows) if (r.flagged && !first[r.customer_id]) first[r.customer_id] = r;
        if (live) setFresh(first);
      })
      .catch(() => undefined);
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
              {fresh[c.id] && (
                <Link to="/sales/freshness" className="fresh-chip">
                  <StatusChip tone="warn">
                    {`up to ${fresh[c.id]!.high.value} packets ${expiresIn(fresh[c.id]!.days_to_best_before)}`}
                  </StatusChip>
                </Link>
              )}
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
