import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Attribution } from "../owner/planningTypes";
import { Num } from "../components/Num";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet, apiPost } from "../lib/api";
import { formatValue } from "../lib/format";
import { ServerStatus } from "../sales/ui";
import type { OrderCard } from "./types";
import { stateName } from "../lib/states";

/** One product: show its price in the label. Several: the table above lists each price (review fix, MP09). */
function priceChoiceLabel(card: OrderCard, choice: "captured" | "current"): string {
  const one = card.card_lines.length === 1 ? card.card_lines[0] : undefined;
  if (choice === "captured") {
    return one
      ? `The phone's price (${formatValue(one.price_captured, "INR")})`
      : "The phone's prices";
  }
  return one
    ? `Today's list price (${formatValue(one.price_current ?? "", "INR")})`
    : "Today's list prices";
}

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—";

/**
 * One order and every option, in plain words (MP09, H10). Each decision is sent to the server, which holds the
 * stock; the card then shows what the server now has. Numbers with ⓘ come from the backend with their formula.
 */
export function OrderCardPage() {
  const { orderId = "" } = useParams();
  const [card, setCard] = useState<OrderCard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stalePrice, setStalePrice] = useState<"captured" | "current" | null>(null);
  const [creditReason, setCreditReason] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [cancelReason, setCancelReason] = useState("");

  useEffect(() => {
    let live = true;
    apiGet<OrderCard>(`/api/inbox/${encodeURIComponent(orderId)}`)
      .then((c) => live && setCard(c))
      .catch(
        (e) => live && setError(e instanceof ApiError ? e.message : "Could not load the order."),
      );
    return () => {
      live = false;
    };
  }, [orderId]);

  async function act(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const next = await apiPost<OrderCard>(`/api/orders/${orderId}/${path}`, body ?? {});
      setCard(next);
      setDone(next.decision?.summary ?? "Done.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The factory server did not answer. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!card) {
    return (
      <section className="admin-page">
        <p className="muted small">
          <Link to="/admin/orders">← Order inbox</Link>
        </p>
        {error ? <p className="alert">{error}</p> : <p className="muted">Loading…</p>}
      </section>
    );
  }

  const can = (a: string) => card.actions.includes(a);
  const short = card.shortage_total !== "0";
  const sendNow = card.card_lines.reduce((n, l) => n + Number(l.can_send_now), 0);
  const owed = card.card_lines.reduce((n, l) => n + Number(l.shortage.value), 0);
  const openPackets = card.card_lines.reduce((n, l) => n + Number(l.open), 0);
  const staleOk = !card.stale_choice_needed || stalePrice !== null;
  const creditOk = !card.credit.over_limit || creditReason.trim().length >= 3;
  const approveBody = {
    ...(card.stale_choice_needed && stalePrice ? { stale_price: stalePrice } : {}),
    ...(card.credit.over_limit ? { credit_override_reason: creditReason } : {}),
  };
  const ready = staleOk && creditOk && !busy;

  return (
    <section className="admin-page">
      <p className="muted small">
        <Link to="/admin/orders">← Order inbox</Link>
      </p>
      <h1>{card.customer.name}</h1>
      <p className="chips">
        <ServerStatus status={card.status} />
        {short && card.status === "SUBMITTED" && <StatusChip tone="bad">Short of stock</StatusChip>}
        {card.stale && <StatusChip tone="warn">Stale price</StatusChip>}
        {card.waiting && <StatusChip tone="info">Waiting for a batch</StatusChip>}
      </p>
      <p className="muted small">
        <strong className="order-no">{card.order_no}</strong> · from{" "}
        {card.salesman?.name ?? "the factory"} · saved on phone {when(card.captured_at)} · received{" "}
        {when(card.received_at)} ·{" "}
        {card.customer.kind === "DISTRIBUTOR" ? "Distributor" : "Retailer"},{" "}
        {stateName(card.customer.state_code)}
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

      <h2>Products and stock</h2>
      <div className="table-wrap" tabIndex={0}>
        <table className="lines">
          <thead>
            <tr>
              <th scope="col">Product</th>
              <th scope="col" className="num">
                Ordered
              </th>
              <th scope="col" className="num">
                Price ex-tax
              </th>
              <th scope="col" className="num">
                Available to promise
              </th>
              <th scope="col" className="num">
                Shortage
              </th>
            </tr>
          </thead>
          <tbody>
            {card.card_lines.map((l) => (
              <tr key={l.line_no}>
                <td>
                  {l.item_name}
                  {(l.approved !== "0" || l.backordered !== "0") && (
                    <span className="muted small">
                      <br />
                      held {l.approved}
                      {l.backordered !== "0" ? ` · backordered ${l.backordered}` : ""}
                    </span>
                  )}
                </td>
                <td className="num">{l.requested}</td>
                <td className="num">
                  {formatValue(l.price_final ?? l.price_captured, "INR")}
                  {l.price_final && (
                    <span className="muted small">
                      <br />
                      phone: {formatValue(l.price_captured, "INR")}
                    </span>
                  )}
                  {l.price_current && l.price_current !== (l.price_final ?? l.price_captured) && (
                    <span className="muted small">
                      <br />
                      list today: {formatValue(l.price_current, "INR")}
                    </span>
                  )}
                </td>
                <td className="num">
                  <Num value={l.available} label={`Available to promise: ${l.item_name}`} />
                </td>
                <td className={`num${l.shortage.value !== "0" ? " bad" : ""}`}>
                  <Num value={l.shortage} label={`Shortage: ${l.item_name}`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {card.tax_preview && (card.tax_preview.full || card.tax_preview.partial) && (
        <>
          <h2>If invoiced</h2>
          <p className="muted small">
            Place of supply {card.tax_preview.place_of_supply}. A preview: the invoice works it out
            again on its own date.
          </p>
          <ul className="tax-options">
            {(["full", "partial"] as const).map((k) => {
              const o = card.tax_preview?.[k];
              if (!o) return null;
              if (o.error) return <li key={k}>{o.error}</li>;
              const label =
                k === "full" ? `All ${o.packets} packets` : `The ${o.packets} available now`;
              if (k === "partial" && o.packets === card.tax_preview?.full?.packets) return null;
              return (
                <li key={k}>
                  <strong>{label}:</strong> taxable {formatValue(o.taxable ?? "", "INR")} +{" "}
                  {Object.entries(o.by_tax ?? {})
                    .map(([h, a]) => `${h} ${formatValue(a, "INR")}`)
                    .join(" + ")}{" "}
                  = <strong>{formatValue(o.total ?? "", "INR")}</strong> ·{" "}
                  {o.eway_required ? "e-Way Bill required" : "no e-Way Bill needed"}
                  <div className="muted small">{o.eway_reason} (DEMO check, nothing is filed)</div>
                </li>
              );
            })}
          </ul>
        </>
      )}

      <h2>Credit</h2>
      <p>
        Outstanding <Num value={card.credit.outstanding} label="Outstanding" /> + this order ={" "}
        <Num value={card.credit.exposure} label="Credit exposure" />{" "}
        {card.credit.limit ? (
          <>against a limit of {formatValue(card.credit.limit, "INR")}.</>
        ) : (
          <>(no credit limit set).</>
        )}{" "}
        {card.credit.over_limit ? (
          <StatusChip tone="warn">Over the limit</StatusChip>
        ) : (
          <StatusChip tone="ok">Within limit</StatusChip>
        )}
      </p>
      <p className="muted small">Outstanding = invoices minus payments and credit notes.</p>

      {card.status === "SUBMITTED" && (
        <>
          {card.stale_choice_needed && (
            <div className="banner banner-warn">
              <p>
                <strong>The price list changed while the phone was offline.</strong> Which price
                applies to this order?
              </p>
              <div className="actions-row">
                {(["captured", "current"] as const).map((c) => (
                  <label key={c} className={`choice${stalePrice === c ? " on" : ""}`}>
                    <input
                      type="radio"
                      name="stale"
                      checked={stalePrice === c}
                      onChange={() => setStalePrice(c)}
                    />
                    {priceChoiceLabel(card, c)}
                  </label>
                ))}
              </div>
            </div>
          )}
          {card.credit.over_limit && (
            <label className="field">
              Reason to approve over the credit limit
              <input value={creditReason} onChange={(e) => setCreditReason(e.target.value)} />
            </label>
          )}

          <h2>Decide</h2>
          {!short ? (
            <div className="options">
              <button
                type="button"
                className="btn btn-primary btn-lg"
                disabled={!ready}
                onClick={() => void act("approve", approveBody)}
              >
                Approve all {openPackets} packets
              </button>
              <p className="muted small">The packets are held for this customer at once.</p>
            </div>
          ) : (
            <div className="options">
              <div className="option">
                <h3>1. Send what is available now</h3>
                <p>
                  Hold {sendNow} packets now and backorder {owed}. The backorder is filled when
                  stock arrives.
                </p>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!ready || sendNow === 0}
                  onClick={() => void act("approve", { ...approveBody, partial: true })}
                >
                  Send {sendNow} now, backorder {owed}
                </button>
              </div>
              <div className="option">
                <h3>2. Wait for the next batch</h3>
                <p>
                  {card.card_lines.map((l) =>
                    l.next_batch
                      ? `${l.next_batch.run_no} is planned for ${l.next_batch.run_date} (about ${l.next_batch.planned_packets} packets). `
                      : "No batch is planned yet, so the arrival date is unknown. ",
                  )}
                </p>
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() => void act("wait")}
                >
                  Wait for the next batch
                </button>
              </div>
              <div className="option">
                <h3>3. Reject</h3>
                <label className="field">
                  Reason
                  <input value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
                </label>
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={busy || rejectReason.trim().length < 3}
                  onClick={() => void act("reject", { reason: rejectReason })}
                >
                  Reject the order
                </button>
              </div>
              <p className="muted small">
                Stock never goes below zero: the factory cannot promise or invoice packets it does
                not have.
              </p>
            </div>
          )}
        </>
      )}

      {card.status === "PART_APPROVED" && (
        <>
          <h2>Backorder</h2>
          <p>
            {card.card_lines.reduce((n, l) => n + Number(l.backordered), 0)} packets are still owed.
          </p>
          <ShortageWhy orderId={orderId} />
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => void act("approve-backorder")}
          >
            Fill the backorder from stock now
          </button>
        </>
      )}

      {(can("cancel") || (can("reject") && card.status !== "SUBMITTED")) && (
        <details className="more">
          <summary>{can("cancel") ? "Cancel this order" : "Reject this order"}</summary>
          <label className="field">
            Reason
            <input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} />
          </label>
          <button
            type="button"
            className="btn btn-danger"
            disabled={busy || cancelReason.trim().length < 3}
            onClick={() => void act(can("cancel") ? "cancel" : "reject", { reason: cancelReason })}
          >
            {can("cancel") ? "Cancel and release the stock" : "Reject and release the stock"}
          </button>
        </details>
      )}

      <h2>History</h2>
      <ol className="timeline">
        {card.timeline.map((t, i) => (
          <li key={`${t.at}-${i}`} className="done">
            <strong>
              {t.to_status === "SUBMITTED" && !t.from_status ? "Received" : t.to_status}
            </strong>{" "}
            <span className="muted small">{when(t.at)}</span>
            {t.reason && <div className="small">{t.reason}</div>}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** MP12 (row 23): how much of the shortage recent batches' yield losses explain. Shown only when they explain some. */
function ShortageWhy({ orderId }: { orderId: string }) {
  const [why, setWhy] = useState<Attribution | null>(null);
  useEffect(() => {
    let live = true;
    apiGet<Attribution>(`/api/planning/shortage/${encodeURIComponent(orderId)}`)
      .then((a) => live && setWhy(a))
      .catch(() => undefined); // an explanation, not a decision: the card works without it
    return () => {
      live = false;
    };
  }, [orderId]);
  const lines = (why?.lines ?? []).filter((l) => l.attributed_to_yield_loss.value !== "0");
  if (lines.length === 0) return null;
  return (
    <div className="why-short">
      {lines.map((l) => (
        <p key={l.item_id}>
          <strong>Why short?</strong>{" "}
          <Num
            value={l.attributed_to_yield_loss}
            label={`packets of ${l.item_name} lost to yield`}
          />{" "}
          of the {l.shortage} short packets of {l.item_name} are explained by recent batches making
          fewer good packets than expected. At the expected yield the shortage would have been{" "}
          {l.would_have_been}.
        </p>
      ))}
    </div>
  );
}
