import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Num } from "../components/Num";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet, apiPost } from "../lib/api";
import type { Explained } from "../lib/explained";

interface RunBrief {
  id: string;
  run_no: string;
  status: string;
  cost_status: string;
  run_date: string;
  good_units: number | null;
}
interface Costing {
  run_no: string;
  cost_status: string;
  cost: {
    materials: Explained;
    conversion: Explained;
    total: Explained;
    per_good_unit: Explained | null;
  };
}

/**
 * Batch → Run costs (MP15, NIT step 8): add labour and gas / power to a finished batch, see the cost per good
 * packet, then mark the costs final. Late costs reach the batch's packets wherever they are now (ADR-0014).
 */
export function RunCostsPage() {
  const [runs, setRuns] = useState<RunBrief[]>([]);
  const [runId, setRunId] = useState("");
  const [costing, setCosting] = useState<Costing | null>(null);
  const [labour, setLabour] = useState("");
  const [gas, setGas] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<{ runs: RunBrief[] }>("/api/runs")
      .then((r) => {
        const finished = r.runs.filter((x) => x.status === "COMPLETED").reverse();
        setRuns(finished);
        setRunId((id) => id || finished[0]?.id || "");
      })
      .catch(() => setError("Could not load the batches."));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    if (!runId) return;
    apiGet<Costing>(`/api/runs/${runId}/costing`)
      .then(setCosting)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load the run cost."));
  }, [runId, done]);

  async function act(what: () => Promise<string>) {
    setBusy(true);
    setError(null);
    try {
      setDone(await what());
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The factory server did not answer.");
    } finally {
      setBusy(false);
    }
  }

  const add = () =>
    act(async () => {
      for (const [kind, amount] of [
        ["LABOUR", labour],
        ["GAS_POWER", gas],
      ] as const) {
        if (amount.trim())
          await apiPost(`/api/runs/${runId}/costs`, { kind, amount: amount.trim() });
      }
      setLabour("");
      setGas("");
      return "Costs added. The cost per packet below now includes them.";
    });

  const final = costing?.cost_status === "FINAL";

  return (
    <section className="admin-page floor">
      <h1>Run costs</h1>
      <p className="muted">
        Labour and gas / power for a finished batch. They are added to the batch&apos;s packets
        wherever those packets are now, so the cost per packet is complete.
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
      <label className="form">
        Batch
        <select value={runId} onChange={(e) => setRunId(e.target.value)}>
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              {r.run_no} · {r.run_date} · {r.good_units ?? 0} good packets ·{" "}
              {r.cost_status === "FINAL" ? "final" : "provisional"}
            </option>
          ))}
        </select>
      </label>
      {runs.length === 0 && (
        <p className="muted">No finished batch yet. Post one on the batch card.</p>
      )}
      {costing && (
        <div className="brief-cards">
          <div className="brief-card">
            <h2>Materials</h2>
            <Num className="big" value={costing.cost.materials} label="materials cost" />
          </div>
          <div className="brief-card">
            <h2>Labour and gas</h2>
            <Num className="big" value={costing.cost.conversion} label="labour and gas" />
          </div>
          <div className="brief-card">
            <h2>Total</h2>
            <Num className="big" value={costing.cost.total} label="run cost" />
          </div>
          <div className="brief-card">
            <h2>Per good packet</h2>
            {costing.cost.per_good_unit ? (
              <Num
                className="big"
                value={costing.cost.per_good_unit}
                label="cost per good packet"
              />
            ) : (
              "-"
            )}
            {final ? (
              <StatusChip tone="ok">final</StatusChip>
            ) : (
              <StatusChip tone="todo">provisional</StatusChip>
            )}
          </div>
        </div>
      )}
      {runId && !final && (
        <>
          <div className="floor-row">
            <label>
              Labour ₹
              <input
                className="big"
                inputMode="decimal"
                value={labour}
                onChange={(e) => setLabour(e.target.value)}
              />
            </label>
            <label>
              Gas / power ₹
              <input
                className="big"
                inputMode="decimal"
                value={gas}
                onChange={(e) => setGas(e.target.value)}
              />
            </label>
          </div>
          <div className="floor-bar">
            <button
              type="button"
              className="btn btn-primary btn-lg"
              disabled={busy || (!labour.trim() && !gas.trim())}
              onClick={() => void add()}
            >
              Add costs
            </button>
            <button
              type="button"
              className="btn btn-lg"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  await apiPost(`/api/runs/${runId}/costs/finalise`);
                  return "Costs are final for this batch.";
                })
              }
            >
              Mark costs final
            </button>
          </div>
        </>
      )}
      {runId && (
        <p>
          <Link to={`/leaks/${runId}`}>Where did this batch&apos;s money go? →</Link>
        </p>
      )}
    </section>
  );
}
