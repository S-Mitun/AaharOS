import { useEffect, useState } from "react";
import { Num } from "../components/Num";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet } from "../lib/api";
import { expiresIn, type Freshness } from "./traceTypes";

/**
 * Salesman → Freshness (MP13, T5): packets of each batch that may still be on a customer's shelf, estimated from
 * that customer's own order rhythm, with the ones close to their best-before first. An estimate, not a count.
 */
export function FreshnessPage() {
  const [data, setData] = useState<Freshness | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Freshness>("/api/trace/freshness")
      .then(setData)
      .catch((e) =>
        setError(
          e instanceof ApiError
            ? e.message
            : "The freshness radar needs the network; try again when you are online.",
        ),
      );
  }, []);

  return (
    <section className="sales-page">
      <h1>Freshness</h1>
      <p className="muted">
        Packets that may still be on your customers’ shelves, oldest best-before first. Visit the
        flagged ones before the packets expire.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p className="muted">Loading…</p>}
      {data && (
        <>
          <p>
            {data.flagged > 0 ? (
              <StatusChip tone="warn">{`${data.flagged} to visit soon`}</StatusChip>
            ) : (
              <StatusChip tone="ok">{`nothing expires within ${data.alert_days} days`}</StatusChip>
            )}{" "}
            <span className="muted small">{data.note}</span>
          </p>
          {data.rows.length === 0 && (
            <p className="muted">No packets are estimated to be on a shelf.</p>
          )}
          <ul className="plain-list fresh-list">
            {data.rows.map((r) => (
              <li key={`${r.customer_id}-${r.lot_id}`} className="customer-card">
                <div className="customer-main">
                  <strong>{r.customer_name}</strong>
                  <span className="muted small">
                    {r.item_name} · batch {r.lot_no}
                    {r.best_before && ` · best before ${r.best_before}`}
                  </span>
                  <span>
                    Up to{" "}
                    <Num value={r.high} label={`packets of ${r.lot_no} at ${r.customer_name}`} />{" "}
                    may be on the shelf
                    {r.enough_history
                      ? ` (likely ${r.central ?? "0"}, at least ${r.low})`
                      : " (not enough order history to say more)"}
                    {r.value_at_risk && (
                      <>
                        {" "}
                        ·{" "}
                        <Num
                          value={r.value_at_risk}
                          label={`value at risk at ${r.customer_name}`}
                        />
                      </>
                    )}
                  </span>
                </div>
                {r.flagged && (
                  <StatusChip tone="warn">{`${r.high.value} ${expiresIn(r.days_to_best_before)}`}</StatusChip>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
