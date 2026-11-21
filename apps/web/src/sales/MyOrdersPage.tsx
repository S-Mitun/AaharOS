import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { formatValue } from "../lib/format";
import { loadMyOrders, type Loaded } from "./api";
import { useOutbox } from "./outboxContext";
import { entryPackets, entryTotal } from "./totals";
import type { ServerOrderRow } from "./types";
import { OfflineCopy, PhoneStatus, ServerStatus, StaleChip } from "./ui";

/** My orders: what needs attention first, then what is still on the phone, then what the factory has (G5). */
export function MyOrdersPage() {
  const outbox = useOutbox();
  const [server, setServer] = useState<Loaded<ServerOrderRow[]> | null>(null);
  const received = outbox.entries.filter((e) => e.state === "received").length;

  useEffect(() => {
    let live = true;
    loadMyOrders()
      .then((r) => live && setServer(r))
      .catch(() => live && setServer({ data: [], offline: true, savedAt: null }));
    return () => {
      live = false;
    };
  }, [received]);

  const attention = outbox.entries.filter((e) => e.state === "attention");
  const onPhone = outbox.entries.filter((e) => e.state === "saved" || e.state === "sending");
  const localFor = new Map(
    outbox.entries.filter((e) => e.serverOrder).map((e) => [e.serverOrder!.id, e.localId]),
  );

  return (
    <section className="sales-page">
      <h1>My orders</h1>

      {attention.length > 0 && (
        <>
          <h2 className="section-bad">Needs attention ({attention.length})</h2>
          <p className="muted small">
            The factory refused these. Read the reason, then edit and send again, or discard.
          </p>
          <ul className="order-list">
            {attention.map((e) => (
              <li key={e.localId} className="order-row attention">
                <Link to={`/sales/orders/${e.localId}`} className="order-row-main">
                  <strong>{e.customerName}</strong>
                  <span className="small">
                    {entryPackets(e)} packets · {formatValue(entryTotal(e), "INR")}
                  </span>
                  <PhoneStatus state={e.state} />
                  <span className="reason">{e.lastError?.message}</span>
                </Link>
                <div className="row-actions">
                  <Link className="btn" to={`/sales/order/${e.customerId}?edit=${e.localId}`}>
                    Edit and send again
                  </Link>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => void outbox.discard(e.localId)}
                  >
                    Discard
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {onPhone.length > 0 && (
        <>
          <h2>On this phone ({onPhone.length})</h2>
          <p className="muted small">
            Saved safely. They send by themselves when there is a connection.
          </p>
          <ul className="order-list">
            {onPhone.map((e) => (
              <li key={e.localId} className="order-row">
                <Link to={`/sales/orders/${e.localId}`} className="order-row-main">
                  <strong>{e.customerName}</strong>
                  <span className="small">
                    {entryPackets(e)} packets · {formatValue(entryTotal(e), "INR")}
                  </span>
                  <PhoneStatus state={e.state} />
                </Link>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="btn"
            disabled={!outbox.online}
            onClick={() => void outbox.sendNow()}
          >
            Send now
          </button>
        </>
      )}

      <h2>With the factory</h2>
      {server?.offline && <OfflineCopy savedAt={server.savedAt} />}
      {!server && <p className="muted">Loading…</p>}
      {server && server.data.length === 0 && (
        <p className="muted">No orders received in the last 30 days.</p>
      )}
      <ul className="order-list">
        {server?.data.map((o) => (
          <li key={o.id} className="order-row">
            <Link to={`/sales/orders/${localFor.get(o.id) ?? o.id}`} className="order-row-main">
              <strong>{o.customer_name}</strong>
              <span className="small">
                {o.order_no} · {o.packets} packets · {formatValue(o.value_ex_tax, "INR")}
              </span>
              <span className="chips">
                <ServerStatus status={o.status} />
                {o.stale && <StaleChip />}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
