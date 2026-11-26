import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Num } from "../components/Num";
import { apiGet } from "../lib/api";
import type { Explained } from "../lib/explained";
import { formatValue } from "../lib/format";
import { useOutbox } from "./outboxContext";
import { entryPackets, entryTotal } from "./totals";
import { PhoneStatus, ServerStatus, StaleChip } from "./ui";

interface ServerOrder {
  id: string;
  order_no: string;
  status: string;
  captured_at: string | null;
  received_at: string;
  customer: { name: string };
  price_list: { code: string; version: number } | null;
  lines: { item_name: string; qty: string; price_ex_tax: string; value_ex_tax: string }[];
  total_ex_tax: Explained;
  stale: boolean;
  stale_detail: { in_force_price_list: { code: string; version: number } | null } | null;
  timeline: { to_status: string; at: string; reason: string | null }[];
}

const when = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—";

/** One order and its timeline: saved on phone → sending → received by factory → approved (MP09). The screen never
 * says "Received" before the server's acknowledgement. */
export function OrderDetailPage() {
  const { orderId = "" } = useParams();
  const outbox = useOutbox();
  const entry = outbox.entries.find((e) => e.localId === orderId);
  const serverId = entry ? entry.serverOrder?.id : orderId;
  const [order, setOrder] = useState<ServerOrder | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (!serverId) return;
    let live = true;
    apiGet<ServerOrder>(`/api/orders/${encodeURIComponent(serverId)}`)
      .then((o) => live && setOrder(o))
      .catch(() => live && setMissing(!entry));
    return () => {
      live = false;
    };
  }, [serverId, entry]);

  if (!entry && missing) {
    return (
      <section className="sales-page">
        <h1>Order not found</h1>
        <Link to="/sales/orders">← My orders</Link>
      </section>
    );
  }

  return (
    <section className="sales-page">
      <p className="muted small">
        <Link to="/sales/orders">← My orders</Link>
      </p>
      <h1>{order?.customer.name ?? entry?.customerName ?? "Order"}</h1>
      <p className="chips">
        {order ? (
          <ServerStatus status={order.status} />
        ) : (
          entry && <PhoneStatus state={entry.state} />
        )}
        {(order?.stale || entry?.serverOrder?.stale) && <StaleChip />}
      </p>
      {order && <p className="order-no">{order.order_no}</p>}

      {entry?.state === "attention" && (
        <div className="alert" role="alert">
          <p>
            <strong>The factory refused this order:</strong> {entry.lastError?.message}
          </p>
          <p className="actions-row">
            <Link className="btn" to={`/sales/order/${entry.customerId}?edit=${entry.localId}`}>
              Edit and send again
            </Link>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => void outbox.discard(entry.localId)}
            >
              Discard
            </button>
          </p>
        </div>
      )}

      <h2>Timeline</h2>
      <ol className="timeline">
        <li className="done">
          Saved on phone{" "}
          <span className="muted small">{when(order?.captured_at ?? entry?.capturedAt)}</span>
        </li>
        {entry && entry.state !== "received" && !order && (
          <li className={entry.state === "sending" ? "now" : "todo"}>
            {entry.state === "saved"
              ? `Waiting to send${entry.attempts ? ` (tried ${entry.attempts}×: ${entry.lastError?.message ?? ""})` : ""}`
              : entry.state === "sending"
                ? "Sending…"
                : "Not sent: needs attention"}
          </li>
        )}
        {order && (
          <li className="done">
            Received by factory as <strong>{order.order_no}</strong>{" "}
            <span className="muted small">{when(order.received_at)}</span>
          </li>
        )}
        {order?.timeline
          .filter((t) => t.to_status !== "SUBMITTED")
          .map((t) => (
            <li key={t.at} className="done">
              {t.to_status} <span className="muted small">{when(t.at)}</span>
            </li>
          ))}
        {(!order || order.status === "SUBMITTED") && (
          <li className="todo">Approval by the factory admin</li>
        )}
      </ol>

      <h2>Products</h2>
      <table className="lines">
        <thead>
          <tr>
            <th scope="col">Product</th>
            <th scope="col" className="num">
              Packets
            </th>
            <th scope="col" className="num">
              Price ex-tax
            </th>
          </tr>
        </thead>
        <tbody>
          {(
            order?.lines ??
            entry?.lines.map((l) => ({
              item_name: l.name,
              qty: l.qty,
              price_ex_tax: l.price,
              value_ex_tax: "",
            })) ??
            []
          ).map((l) => (
            <tr key={l.item_name}>
              <td>{l.item_name}</td>
              <td className="num">{l.qty}</td>
              <td className="num">{formatValue(l.price_ex_tax, "INR")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="order-sum">
        {order ? (
          <>
            Order value ex-tax: <Num value={order.total_ex_tax} label="Order value ex-tax" />
          </>
        ) : (
          entry && (
            <>
              {entryPackets(entry)} packets · estimated {formatValue(entryTotal(entry), "INR")}{" "}
              ex-tax (the factory confirms it on receipt)
            </>
          )
        )}
      </p>
      {order?.stale && order.stale_detail && (
        <p className="banner banner-warn">
          The phone showed price list {order.price_list?.code} v{order.price_list?.version}, but{" "}
          {order.stale_detail.in_force_price_list
            ? `${order.stale_detail.in_force_price_list.code} v${order.stale_detail.in_force_price_list.version}`
            : "no list"}{" "}
          was in force when the factory received it. The admin decides which price applies.
        </p>
      )}
    </section>
  );
}
