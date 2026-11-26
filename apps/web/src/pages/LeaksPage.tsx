import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useParams } from "react-router-dom";
import { Num } from "../components/Num";
import { formatAmount } from "../lib/amount";
import { ApiError, apiGet } from "../lib/api";
import { isNegative, sharePercent } from "../lib/decimal";
import { checkFor, words, type Component, type Costing } from "../lib/leaks";
import { useSession } from "../lib/sessionContext";

interface RunRow {
  id: string;
  run_no: string;
  status: string;
  cost_status: string;
  run_date: string;
  recipe: string | null;
  good_units: number | null;
}

function Direction({ c }: { c: Component }) {
  if (c.direction === "UNFAVOURABLE") return <span className="chip chip-bad">▲ Costs more</span>;
  if (c.direction === "FAVOURABLE") return <span className="chip chip-ok">▼ Saves</span>;
  return <span className="chip chip-todo">● On standard</span>;
}

function useSignedIn() {
  const { me, loading } = useSession();
  const location = useLocation();
  if (loading) return { gate: <p className="muted">Checking sign-in…</p> };
  if (!me) return { gate: <Navigate to="/sign-in" replace state={{ next: location.pathname }} /> };
  return { gate: null };
}

export function LeaksIndexPage() {
  const { gate } = useSignedIn();
  const [runs, setRuns] = useState<RunRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (gate) return;
    apiGet<{ runs: RunRow[] }>("/api/runs")
      .then((r) => setRuns(r.runs))
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : "Could not load runs."));
  }, [gate]);
  if (gate) return gate;
  const done = (runs ?? []).filter((r) => r.status === "COMPLETED");
  return (
    <section className="leaks">
      <h1>Where profit leaks</h1>
      <p className="lead">
        Pick a completed batch to see where its cost went above or below the standard.
      </p>
      {error && <p className="alert">{error}</p>}
      {runs && done.length === 0 && <p className="muted">No completed batches yet.</p>}
      <ul className="run-list">
        {done.map((r) => (
          <li key={r.id}>
            <Link className="link-strong" to={`/leaks/${r.id}`}>
              Batch {r.run_no}
            </Link>{" "}
            <span className="muted">
              {r.run_date} · {r.recipe} · {r.good_units} good packets ·{" "}
            </span>
            <CostStatus status={r.cost_status} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function CostStatus({ status }: { status: string }) {
  return status === "FINAL" ? (
    <span className="chip chip-ok">✓ Cost final</span>
  ) : (
    <span className="chip chip-warn">⏳ Cost provisional</span>
  );
}

export function LeaksPage() {
  const { gate } = useSignedIn();
  const { runId = "" } = useParams();
  const [data, setData] = useState<Costing | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (gate) return;
    apiGet<Costing>(`/api/runs/${runId}/costing`)
      .then(setData)
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Could not load the costing."),
      );
  }, [gate, runId]);
  if (gate) return gate;
  if (error) return <p className="alert">{error}</p>;
  if (!data) return <p className="muted">Loading batch costing…</p>;

  const wf = data.waterfall;
  const parts = (wf?.components ?? []).filter((c) => c.value !== "0.00");
  const largest = parts.reduce(
    (m, c) => (sharePercent(c.value, m) > 100 ? c.value : m),
    parts[0]?.value ?? "0",
  );
  const checks = parts.map((c) => checkFor(c, data.run_no)).filter((t): t is string => t !== null);
  return (
    <section className="leaks">
      <p className="eyebrow">
        <Link to="/leaks">Where profit leaks</Link>
      </p>
      <h1>
        Batch {data.run_no} <CostStatus status={data.cost_status} />
      </h1>
      <div className="kpis">
        <div className="kpi">
          <span className="meta-label">Run cost</span>
          <Num value={data.cost.total} label="Run cost" />
        </div>
        {data.cost.per_good_unit && (
          <div className="kpi">
            <span className="meta-label">Cost per good packet</span>
            <Num value={data.cost.per_good_unit} label="Cost per good packet" />
          </div>
        )}
        {wf && (
          <>
            <div className="kpi">
              <span className="meta-label">Standard for the good packets</span>
              <Num value={wf.standard} label="Standard cost of the good output" />
            </div>
            <div className="kpi">
              <span className="meta-label">
                {isNegative(wf.total.value) ? "Saved against standard" : "Leak against standard"}
              </span>
              <Num value={wf.total} label="Actual minus standard" />
            </div>
          </>
        )}
      </div>

      {!wf && <p className="alert">No waterfall for this batch: {data.waterfall_unavailable}.</p>}
      {wf && (
        <>
          <h2>Where the money went</h2>
          <ol className="waterfall" aria-label="Variance waterfall, largest first">
            {parts.map((c) => (
              <li key={`${c.kind}-${c.label}`} className={`wf-row wf-${c.direction.toLowerCase()}`}>
                <span className="wf-label">
                  {words(c.label)}
                  {c.note && <span className="muted small"> · {c.note}</span>}
                </span>
                <span className="wf-bar" aria-hidden="true">
                  <span style={{ width: `${sharePercent(c.value, largest)}%` }} />
                </span>
                <Num value={c.explained} label={words(c.label)} />
                <Direction c={c} />
              </li>
            ))}
          </ol>
          <h2>Checks to make</h2>
          <p className="muted small">Possibilities to verify on the floor, not findings.</p>
          <ul className="checks-list">
            {checks.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </>
      )}

      <h2>Valuation method comparison</h2>
      <div className="table-wrap" tabIndex={0}>
        <table>
          <thead>
            <tr>
              <th scope="col">Method</th>
              <th scope="col">Run cost</th>
              <th scope="col">Per good packet</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.sensitivity).map(([method, s]) => (
              <tr key={method}>
                <th scope="row">
                  {method} {s.posts && <span className="chip chip-info">In the books</span>}
                </th>
                <td>
                  <Num value={s.total} label={`Run cost under ${method}`} />
                </td>
                <td className="num">
                  {s.per_good_unit_display ? formatAmount(s.per_good_unit_display, s.unit) : "—"}
                </td>
                <td className="muted small">
                  {s.book_value_used_for.length > 0 &&
                    `No purchase yet for ${s.book_value_used_for.map(words).join(", ")}: book value used.`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">{data.note}</p>
    </section>
  );
}
