import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { StatusChip } from "../components/StatusChip";
import { STEPS } from "../guide/steps";
import { ApiError, apiGet, apiPost } from "../lib/api";
import { useSession } from "../lib/sessionContext";

interface Row {
  n: number;
  title: string;
  owner_mp: string;
  status: string;
  detail: string;
  expected: Record<string, string>;
}
interface Board {
  available: boolean;
  generated_at?: string;
  green?: number;
  total?: number;
  rows?: Row[];
  oracle_integrity?: { passed: number; failed: number };
  reason?: string;
}
interface Status {
  judge_mode: boolean;
  running: boolean;
  seconds: number | null;
}

/** The tour step that shows a benchmark row, so a judge can see it happen on the screens. */
const stepFor = (n: number) => STEPS.find((s) => s.assertions.includes(n));

/**
 * Judge Mode (MP15): replay NIT's nine steps on a fresh benchmark factory (never the DEMO factory or yours) and
 * compare all 26 figures with the oracle. Anyone can read the scoreboard; the DEMO admin or owner can run it again.
 */
export function JudgePage() {
  const { me } = useSession();
  const canRun = !!me?.permissions.includes("benchmark.run");
  const [board, setBoard] = useState<Board | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<Board>("/api/guide/scoreboard")
      .then(setBoard)
      .catch(() => setError("Could not load the scoreboard."));
    apiGet<Status>("/api/judge/status")
      .then(setStatus)
      .catch(() => undefined);
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    if (!status?.running) return;
    const t = window.setInterval(load, 3000);
    return () => window.clearInterval(t);
  }, [status?.running, load]);

  async function run() {
    setError(null);
    try {
      await apiPost("/api/judge/run");
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The factory server did not answer.");
    }
  }

  const steps = STEPS.filter((s) => s.nitStep);
  return (
    <section className="admin-page judge">
      <h1>Judge Mode</h1>
      <p className="muted">
        NIT&apos;s nine steps are replayed through the real services on a fresh benchmark factory,
        then all 26 figures are compared with the oracle (
        <code>benchmark/expected_results.yaml</code>). The DEMO factory and your own factory are
        never touched.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <div className="judge-run">
        {status?.running ? (
          <StatusChip tone="info">{`replaying… ${status.seconds ?? 0} s`}</StatusChip>
        ) : canRun ? (
          <button
            type="button"
            className="btn btn-primary btn-lg"
            disabled={!status?.judge_mode}
            onClick={() => void run()}
          >
            Run the benchmark now
          </button>
        ) : (
          <p className="muted">
            <Link to="/sign-in">Sign in as the DEMO Factory admin or Owner</Link> to run it again.
          </p>
        )}
        {board?.available && (
          <p>
            <StatusChip tone={board.green === board.total ? "ok" : "bad"}>
              {`${board.green} of ${board.total} green`}
            </StatusChip>{" "}
            <span className="muted small">
              oracle integrity {board.oracle_integrity?.passed} passed ·{" "}
              {board.generated_at && new Date(board.generated_at).toLocaleString()}
            </span>
          </p>
        )}
      </div>

      <h2>The nine steps</h2>
      <ol className="judge-steps">
        {steps.map((s) => (
          <li key={s.id}>
            <strong>{s.title}</strong>{" "}
            <span className="muted small">
              ({s.who.role}) — {s.why}
            </span>{" "}
            <Link to={`/guide/${s.id}`}>see it in the tour</Link>
          </li>
        ))}
      </ol>

      <h2>Scoreboard</h2>
      {!board?.available ? (
        <p className="muted">{board?.reason ?? "Loading…"}</p>
      ) : (
        <div className="table-wrap" tabIndex={0}>
          <table className="lines">
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Check</th>
                <th>Expected (oracle)</th>
                <th>Result</th>
                <th>Where to see it</th>
              </tr>
            </thead>
            <tbody>
              {board.rows?.map((r) => {
                const step = stepFor(r.n);
                return (
                  <tr key={r.n}>
                    <td className="num">{r.n}</td>
                    <td>{r.title}</td>
                    <td className="small">
                      {Object.values(r.expected).join(" · ") || "see title"}
                    </td>
                    <td>
                      {r.status === "GREEN" ? (
                        <StatusChip tone="ok">green</StatusChip>
                      ) : (
                        <StatusChip tone="bad">{r.status.toLowerCase()}</StatusChip>
                      )}
                      {r.detail && <span className="muted small"> {r.detail}</span>}
                    </td>
                    <td>{step ? <Link to={`/guide/${step.id}`}>{step.title}</Link> : "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
