import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Num } from "../components/Num";
import { ApiError, apiGet } from "../lib/api";
import { formatValue } from "../lib/format";
import { words, type Brief } from "./planningTypes";

const money = (v: string) => formatValue(v, "INR");

/** Owner → Morning brief (MP12): five cards, then the three things worth the most rupees today. Read-only. */
export function BriefPage() {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Brief>("/api/planning/brief")
      .then((b) => (b?.cards ? setBrief(b) : setError("Could not load the morning brief.")))
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load the morning brief."),
      );
  }, []);

  if (error)
    return (
      <section className="admin-page">
        <h1>Morning brief</h1>
        <p className="alert" role="alert">
          {error}
        </p>
      </section>
    );
  if (!brief)
    return (
      <section className="admin-page">
        <h1>Morning brief</h1>
        <p className="muted">Loading…</p>
      </section>
    );

  const { orders, available_vs_pending: avp, leaks, runway, money: cash } = brief.cards;
  return (
    <section className="admin-page brief">
      <h1>Morning brief</h1>
      <p className="muted">
        {brief.date} · Five cards, then today’s three actions, biggest rupee impact first. Tap ⓘ on
        any number to see how it is worked out.
      </p>

      <h2>Today’s 3 actions</h2>
      {brief.actions.length === 0 ? (
        <p className="muted">Nothing needs you today.</p>
      ) : (
        <ol className="actions-list">
          {brief.actions.map((a) => (
            <li key={a.kind} className="action-item">
              <span className="action-title">{words(a.title)}</span>
              <Num value={a.impact} label={words(a.title)} />
              <Link className="btn btn-primary" to={a.link}>
                Open
              </Link>
            </li>
          ))}
        </ol>
      )}

      <div className="brief-cards">
        <article className="brief-card">
          <h2>Today’s orders</h2>
          <p className="big">{orders.today.count}</p>
          <p className="muted">dated today, worth {money(orders.today.value)} before tax</p>
          <p>
            <strong>{orders.to_decide.count}</strong> waiting for a decision (
            {money(orders.to_decide.value)})
          </p>
          <Link to={orders.link}>Open the order inbox</Link>
        </article>

        <article className="brief-card">
          <h2>Available vs pending</h2>
          {avp.note && <p className="muted">{avp.note}</p>}
          {avp.items.length === 0 && !avp.note && <p className="muted">No open orders.</p>}
          <ul className="plain-list">
            {avp.items.map((d) => (
              <li key={d.item_code}>
                <strong>{words(d.item_code)}</strong>: {d.available} available, {d.open_packets}{" "}
                still to supply
                {d.shortfall !== "0" && <span className="chip chip-bad">{d.shortfall} short</span>}
              </li>
            ))}
          </ul>
          <Link to={avp.link}>Open the batch planner</Link>
        </article>

        <article className="brief-card">
          <h2>Where profit leaks</h2>
          {leaks.top.length === 0 ? (
            <p className="muted">No batch in the last 30 days cost more than standard.</p>
          ) : (
            <ol className="plain-list">
              {leaks.top.map((l) => (
                <li key={`${l.run_id}-${l.label}`}>
                  <Link to={l.link}>
                    {words(l.label)} · {l.run_no}
                  </Link>{" "}
                  <Num value={l.value} label={`${words(l.label)} on ${l.run_no}`} />
                </li>
              ))}
            </ol>
          )}
          <Link to={leaks.link}>All batches</Link>
        </article>

        <article className="brief-card">
          <h2>Material runway</h2>
          <ul className="plain-list">
            {runway.packs.map((p) => (
              <li key={p.pack_code}>
                <strong>{words(p.pack_code)}</strong>:{" "}
                <Num value={p.full_batches} label={`full batches of ${words(p.pack_code)}`} /> in
                full from stock; runs out first: {p.binding.map(words).join(", ")}
              </li>
            ))}
          </ul>
          <Link to={runway.link}>See every material</Link>
        </article>

        <article className="brief-card">
          <h2>Money to collect</h2>
          <p className="big">{money(cash.outstanding)}</p>
          <p>
            Overdue: <Num value={cash.overdue} label="overdue receivables" />
          </p>
          <p className="muted">
            Unpaid more than 45 days (MSME clock): {money(cash.past_msme_45_days)}
          </p>
          <Link to={cash.link}>Open collections</Link>
        </article>
      </div>
    </section>
  );
}
