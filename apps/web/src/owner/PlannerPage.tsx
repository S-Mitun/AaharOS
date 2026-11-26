import { useCallback, useEffect, useState } from "react";
import { Num } from "../components/Num";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet, apiPost } from "../lib/api";
import { formatValue } from "../lib/format";
import { useSession } from "../lib/sessionContext";
import { words, type BatchPlan, type DraftPo, type RunwayPack } from "./planningTypes";

/**
 * Production → Batch planner (MP12, ADR-0019): how many batches the stock allows, what to make next, what to buy.
 * It only recommends. "Create draft batch" and "Create draft purchase order" make DRAFT documents; nothing is posted.
 */
export function PlannerPage() {
  const { me } = useSession();
  const can = (p: string) => !!me?.permissions.includes(p);
  const [runway, setRunway] = useState<RunwayPack[] | null>(null);
  const [plan, setPlan] = useState<BatchPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<DraftPo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    apiGet<{ packs: RunwayPack[] }>("/api/planning/runway")
      .then((r) => setRunway(r.packs))
      .catch(() => setError("Could not load the material runway."));
    apiGet<BatchPlan>("/api/planning/plan")
      .then((p) => {
        setPlan(p);
        setPlanError(null);
      })
      .catch((e) => setPlanError(e instanceof ApiError ? e.message : "Could not load the plan."));
    apiGet<{ drafts: DraftPo[] }>("/api/planning/purchase-drafts")
      .then((d) => setDrafts(d.drafts))
      .catch(() => undefined);
  }, []);
  useEffect(load, [load]);

  async function run(what: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      setDone(await what());
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The factory server did not answer.");
    } finally {
      setBusy(false);
    }
  }

  const draftBatch = (b: BatchPlan["batches"][number]) =>
    run(async () => {
      await apiPost("/api/planning/batches", {
        recipe_version_id: b.recipe_version_id,
        pack_version_id: b.pack_version_id,
        batches: Number(b.batches?.value ?? 0),
      });
      return `Draft batch of ${b.pack_code} created. Start it from the batch card when the floor is ready.`;
    });

  const draftPurchase = (p: BatchPlan) =>
    run(async () => {
      const r = await apiPost<{ draft_no: string }>("/api/planning/purchase-drafts", {
        note: `From the batch plan of ${p.date}`,
        lines: p.purchases.map((x) => ({
          item_id: x.item_id,
          qty_base: x.qty_base,
          needed_by: x.needed_by,
          reason: "batch planner",
        })),
      });
      return `Draft purchase order ${r.draft_no} created. Nothing is bought until a person sends it.`;
    });

  return (
    <section className="admin-page planner">
      <h1>Batch planner</h1>
      <p className="muted">
        What the stock allows, what to make next and what to buy. It only recommends: approving
        creates a <strong>draft</strong>, nothing is posted.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {done && (
        <p className="done" role="status">
          {done}
        </p>
      )}

      <h2>Material runway</h2>
      {runway === null ? (
        <p className="muted">Loading…</p>
      ) : (
        runway.map((p) => (
          <div key={p.pack_code} className="table-wrap">
            <p>
              <strong>{p.pack_name}</strong> ({p.recipe}): stock allows{" "}
              <Num value={p.full_batches} label={`full batches of ${p.pack_code}`} /> in full. Runs
              out first: <strong>{p.binding.map(words).join(", ")}</strong>.
            </p>
            <table className="lines">
              <thead>
                <tr>
                  <th>Material</th>
                  <th className="num">Available</th>
                  <th className="num">Per batch</th>
                  <th className="num">Batches it allows</th>
                </tr>
              </thead>
              <tbody>
                {p.materials.map((m) => (
                  <tr key={m.item_code} className={m.binding ? "row-binding" : undefined}>
                    <td>
                      {words(m.item_code)}{" "}
                      {m.binding && <StatusChip tone="bad">runs out first</StatusChip>}
                    </td>
                    <td className="num">
                      {m.available} {m.unit}
                    </td>
                    <td className="num">
                      {m.per_batch} {m.unit}
                    </td>
                    <td className="num">
                      <Num value={m.batches} label={`batches ${words(m.item_code)} allows`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))
      )}

      <h2>Next production day</h2>
      {planError && <p className="muted">{planError}</p>}
      {plan && (
        <>
          <p className="muted">
            Room for {plan.capacity} batches a day. The planner makes the most order value the
            materials and the day allow (
            {plan.status === "OPTIMAL" ? "best plan found" : plan.status.toLowerCase()}).
          </p>
          <div className="table-wrap">
            <table className="lines">
              <thead>
                <tr>
                  <th>Product</th>
                  <th className="num">Still to supply</th>
                  <th className="num">Available</th>
                  <th className="num">Short</th>
                  <th className="num">Covered by this plan</th>
                </tr>
              </thead>
              <tbody>
                {plan.demand.map((d) => (
                  <tr key={d.item_code}>
                    <td>{words(d.item_code)}</td>
                    <td className="num">{d.open_packets}</td>
                    <td className="num">{d.available}</td>
                    <td className="num">{d.shortfall}</td>
                    <td className="num">{d.met_today}</td>
                  </tr>
                ))}
                {plan.demand.length === 0 && (
                  <tr>
                    <td colSpan={5} className="muted">
                      No open orders waiting for stock.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <ul className="plain-list">
            {plan.batches.map((b) => (
              <li key={b.pack_code} className="actions-row">
                <span>
                  <strong>{b.pack_code}</strong>: make{" "}
                  {b.batches ? (
                    <Num value={b.batches} label={`batches of ${b.pack_code}`} />
                  ) : (
                    "no batches"
                  )}
                  , about {b.good_packets_per_batch} good packets each
                </span>
                {can("run.start") && b.batches && b.batches.value !== "0" && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={busy}
                    onClick={() => void draftBatch(b)}
                  >
                    Create draft batch
                  </button>
                )}
              </li>
            ))}
          </ul>
          <p>
            Order value this plan supplies: <strong>{formatValue(plan.value_met, "INR")}</strong>{" "}
            before tax.
          </p>

          <h2>What to buy</h2>
          {plan.materials_short.length > 0 && (
            <p>
              To supply every open packet the factory is short of:{" "}
              {plan.materials_short
                .map((m) => `${m.qty} ${m.unit} ${words(m.item_code)}`)
                .join(", ")}
              .
            </p>
          )}
          {plan.purchases.length === 0 ? (
            <p className="muted">Nothing to buy: stock covers the orders and the reorder levels.</p>
          ) : (
            <>
              <div className="table-wrap">
                <table className="lines">
                  <thead>
                    <tr>
                      <th>Material</th>
                      <th className="num">Suggested</th>
                      <th>Needed by</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.purchases.map((p) => (
                      <tr key={p.item_code}>
                        <td>{words(p.item_code)}</td>
                        <td className="num">
                          {p.qty} {p.unit}{" "}
                          <Num value={p.explained} label={`suggested ${words(p.item_code)}`} />
                        </td>
                        <td>
                          {p.needed_by} ({p.lead_time_days} days lead time)
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {can("receipt.post") && (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => void draftPurchase(plan)}
                >
                  Create draft purchase order
                </button>
              )}
            </>
          )}
        </>
      )}

      {drafts.length > 0 && (
        <>
          <h2>Draft purchase orders</h2>
          <ul className="plain-list">
            {drafts.map((d) => (
              <li key={d.id}>
                <strong>{d.draft_no}</strong>{" "}
                <StatusChip tone={d.status === "DRAFT" ? "info" : "todo"}>
                  {d.status === "DRAFT" ? "Draft" : "Cancelled"}
                </StatusChip>{" "}
                {d.lines.map((l) => `${l.qty} ${l.unit} ${words(l.item_code)}`).join(" · ")}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
