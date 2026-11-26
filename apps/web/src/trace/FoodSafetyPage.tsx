import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Num } from "../components/Num";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet } from "../lib/api";
import type { FillWeights, OilLog } from "./traceTypes";

/**
 * Production → Oil and fill weights (MP13, T6): the frying-oil log against the RUCO record-keeping threshold and the
 * TPC discard limit, and fill-weight samples against the declared net (giveaway in rupees, short fills). It reads
 * what batch completion recorded; the thresholds are DEMO settings.
 */
export function FoodSafetyPage() {
  const [oil, setOil] = useState<OilLog | null>(null);
  const [oilError, setOilError] = useState<string | null>(null);
  const [fill, setFill] = useState<FillWeights | null>(null);
  const [fillError, setFillError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<OilLog>("/api/trace/oil?days=30")
      .then(setOil)
      .catch((e) => setOilError(e instanceof ApiError ? e.message : "Could not load the oil log."));
    apiGet<FillWeights>("/api/trace/fill-weights?days=30")
      .then(setFill)
      .catch((e) =>
        setFillError(e instanceof ApiError ? e.message : "Could not load the fill weights."),
      );
  }, []);

  return (
    <section className="admin-page food-safety">
      <h1>Oil and fill weights</h1>
      <p className="muted">
        Last 30 days, from what each batch recorded when it was completed. Thresholds are DEMO
        settings: check them before real use.
      </p>

      <h2>Frying oil</h2>
      {oilError && (
        <p className="alert" role="alert">
          {oilError}
        </p>
      )}
      {!oil && !oilError && <p className="muted">Loading…</p>}
      {oil && (
        <>
          <p>
            {oil.records_required ? (
              <StatusChip tone="warn">daily used-oil records required</StatusChip>
            ) : (
              <StatusChip tone="ok">{`under ${oil.threshold_l_per_day} L on every day`}</StatusChip>
            )}{" "}
            <span className="muted">{oil.note}</span>
          </p>
          {oil.days.length === 0 ? (
            <p className="muted">No oil sessions recorded in these 30 days.</p>
          ) : (
            <div className="table-wrap">
              <table className="lines">
                <thead>
                  <tr>
                    <th>Day</th>
                    <th className="num">Oil used</th>
                    <th>Batch</th>
                    <th className="num">Fresh</th>
                    <th className="num">Top-ups</th>
                    <th className="num">Discarded</th>
                    <th className="num">TPC</th>
                  </tr>
                </thead>
                <tbody>
                  {oil.days.flatMap((d) =>
                    d.sessions.map((s, n) => (
                      <tr key={`${d.date}-${s.run_id}-${n}`}>
                        <td>{n === 0 ? d.date : ""}</td>
                        <td className="num">
                          {n === 0 && (
                            <>
                              <Num value={d.litres} label={`oil used on ${d.date}`} />{" "}
                              {d.above_threshold && (
                                <StatusChip tone="warn">records required</StatusChip>
                              )}
                            </>
                          )}
                        </td>
                        <td>
                          <Link to={`/leaks/${s.run_id}`}>{s.run_no}</Link>
                        </td>
                        <td className="num">{s.fresh_l} L</td>
                        <td className="num">{s.topup_l} L</td>
                        <td className="num">{s.discard_l} L</td>
                        <td className="num">
                          {s.tpc_pct === null ? "not measured" : `${s.tpc_pct}%`}{" "}
                          {s.discard_oil && <StatusChip tone="bad">discard</StatusChip>}
                        </td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <h2>Fill weights</h2>
      {fillError && (
        <p className="alert" role="alert">
          {fillError}
        </p>
      )}
      {!fill && !fillError && <p className="muted">Loading…</p>}
      {fill && (
        <>
          <p className="muted">
            {fill.tolerances.length === 0
              ? "No short-fill tolerance table is configured, so short fills are not checked."
              : `Short if below declared minus: ${fill.tolerances
                  .map((t) => `${t.declared_g} g → ${t.tolerance_g} g`)
                  .join(", ")}. `}
            {fill.note}
          </p>
          {fill.runs.length === 0 ? (
            <p className="muted">No fill-weight samples recorded in these 30 days.</p>
          ) : (
            <div className="table-wrap">
              <table className="lines">
                <thead>
                  <tr>
                    <th>Batch</th>
                    <th>Samples (g)</th>
                    <th className="num">Mean net</th>
                    <th className="num">Over declared</th>
                    <th className="num">Giveaway</th>
                    <th>Short fills</th>
                  </tr>
                </thead>
                <tbody>
                  {fill.runs.map((r) => (
                    <tr key={r.run_id}>
                      <td>
                        <Link to={`/leaks/${r.run_id}`}>{r.run_no}</Link>{" "}
                        <span className="muted small">
                          {r.run_date} · {r.declared_g} g · {r.good_units} good
                        </span>
                      </td>
                      <td>{r.samples.join(", ")}</td>
                      <td className="num">
                        <Num value={r.mean_net} label={`mean net of ${r.run_no}`} />
                      </td>
                      <td className="num">
                        <Num value={r.over_per_packet} label={`grams over declared, ${r.run_no}`} />
                      </td>
                      <td className="num">
                        <Num value={r.giveaway} label={`giveaway of ${r.run_no}`} />
                      </td>
                      <td>
                        {r.short_limit_g === null ? (
                          <span className="muted">no tolerance for {r.declared_g} g</span>
                        ) : r.short_fill_alert ? (
                          <StatusChip tone="bad">
                            {`${r.short_samples.length} below ${r.short_limit_g} g`}
                          </StatusChip>
                        ) : (
                          <StatusChip tone="ok">{`none below ${r.short_limit_g} g`}</StatusChip>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
