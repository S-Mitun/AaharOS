import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { StatusChip } from "../components/StatusChip";
import { apiGet } from "../lib/api";
import { formatValue } from "../lib/format";
import { ServerStatus } from "../sales/ui";
import type { InboxRow } from "./types";

const VIEWS = [
  { id: "to_decide", label: "To decide" },
  { id: "short", label: "Short" },
  { id: "stale", label: "Stale price" },
  { id: "all", label: "All" },
] as const;

/** The admin's order inbox (MP09): orders waiting for a decision, with plain flags. */
export function InboxPage() {
  const [params, setParams] = useSearchParams();
  const view = params.get("view") ?? "to_decide";
  const [rows, setRows] = useState<InboxRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setRows(null);
    apiGet<{ orders: InboxRow[] }>(`/api/inbox?view=${encodeURIComponent(view)}`)
      .then((r) => live && setRows(r.orders))
      .catch(() => live && setError("Could not load the inbox."));
    return () => {
      live = false;
    };
  }, [view]);

  return (
    <section className="admin-page">
      <h1>Order inbox</h1>
      <p className="muted">
        Orders from the salesmen. Open one to approve it, send part now, wait for the next batch, or
        reject it. Stock is held for an order the moment you approve it.
      </p>
      <div className="filter-chips" role="tablist" aria-label="Which orders">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            role="tab"
            aria-selected={view === v.id}
            className={`filter-chip${view === v.id ? " on" : ""}`}
            onClick={() => setParams({ view: v.id })}
          >
            {v.label}
          </button>
        ))}
      </div>
      {error && <p className="alert">{error}</p>}
      {!rows && !error && <p className="muted">Loading…</p>}
      {rows && rows.length === 0 && <p className="muted">Nothing here. All caught up.</p>}
      <ul className="order-list">
        {rows?.map((o) => (
          <li key={o.id} className={`order-row${o.short ? " short" : ""}`}>
            <Link to={`/admin/orders/${o.id}`} className="order-row-main">
              <strong>{o.customer_name}</strong>
              <span className="small">
                {o.order_no} · {o.packets} packets · {formatValue(o.value_ex_tax, "INR")} ex-tax
              </span>
              <span className="chips">
                <ServerStatus status={o.status} />
                {o.short && <StatusChip tone="bad">Short of stock</StatusChip>}
                {o.stale && <StatusChip tone="warn">Stale price</StatusChip>}
                {o.waiting && <StatusChip tone="info">Waiting for a batch</StatusChip>}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
