import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet, apiPost } from "../lib/api";
import { words } from "../owner/planningTypes";

interface PackVersion {
  id: string;
  version: number;
  status: string;
  net_g: string;
  units_per_carton: number;
  lines: { item_id: string; item_code: string; qty_per_good_unit: string }[];
}
interface PackSpec {
  id: string;
  code: string;
  name: string;
  recipe_id: string;
  versions: PackVersion[];
}
interface Recipe {
  id: string;
  code: string;
  versions: { id: string; status: string }[];
}
interface RunBrief {
  id: string;
  run_no: string;
  status: string;
  run_date: string;
}
interface Ingredient {
  label: string;
  item_id: string;
  unit: string;
  standard: string;
  actual: string;
}
interface PackLine {
  pack_line_id: string;
  pack_spec: string;
  pack_spec_version: number;
  expected_units: string;
  good_units: number | null;
}
interface Run {
  id: string;
  run_no: string;
  status: string;
  analysis: { ingredients: Ingredient[]; pack_lines: PackLine[]; flags: string[] } | null;
}
interface Balance {
  item_id: string;
  location: string;
  qty: string;
}

interface Draft {
  actual: Record<string, string>;
  good: string;
  damaged: string;
  cartons: string;
  reason: string;
  fresh: string;
  topup: string;
  tpc: string;
  nets: string;
}
const EMPTY: Draft = {
  actual: {},
  good: "",
  damaged: "0",
  cartons: "",
  reason: "",
  fresh: "",
  topup: "",
  tpc: "",
  nets: "",
};
const REASONS = ["Seal failure", "Torn pouch", "Print error", "Under weight", "Other"];
const POUCH_TARE_G = 4.5; // DEMO tare of one pouch; gross = net + tare
const draftKey = (runId: string) => `aaharos.batch.draft.${runId}`;

function loadDraft(runId: string): Draft {
  try {
    return {
      ...EMPTY,
      ...(JSON.parse(localStorage.getItem(draftKey(runId)) ?? "{}") as Partial<Draft>),
    };
  } catch {
    return EMPTY;
  }
}
const num = (s: string) => (s.trim() === "" ? null : Number(s));

/**
 * Production → Batch card (MP15, NIT steps 2 and 3). Start a batch from the recipe and pack, issue what was
 * actually used (the stock-impact preview shows each store before posting), then record good packets, damage with a
 * reason chip, oil and fill samples. Big inputs for a phone or tablet; the card is kept on this device as a draft
 * until it is posted, so a dropped network loses nothing.
 */
export function BatchPage() {
  const [packs, setPacks] = useState<PackSpec[]>([]);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [runs, setRuns] = useState<RunBrief[]>([]);
  const [stock, setStock] = useState<Record<string, number>>({});
  const [packCode, setPackCode] = useState("");
  const [multiplier, setMultiplier] = useState("1");
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const loadLists = useCallback(() => {
    apiGet<{ pack_specs: PackSpec[] }>("/api/pack-specs")
      .then((r) => {
        setPacks(r.pack_specs);
        setPackCode((c) => c || r.pack_specs[0]?.code || "");
      })
      .catch(() => setError("Could not load the pack specs."));
    apiGet<{ recipes: Recipe[] }>("/api/recipes")
      .then((r) => setRecipes(r.recipes))
      .catch(() => undefined);
    apiGet<{ runs: RunBrief[] }>("/api/runs")
      .then((r) => setRuns(r.runs))
      .catch(() => undefined);
    apiGet<{ balances: Balance[] }>("/api/stock/balances")
      .then((r) => {
        const s: Record<string, number> = {};
        for (const b of r.balances)
          if (b.location === "RAW_STORE" || b.location === "PACK_STORE")
            s[b.item_id] = (s[b.item_id] ?? 0) + Number(b.qty);
        setStock(s);
      })
      .catch(() => undefined);
  }, []);
  useEffect(loadLists, [loadLists]);

  const loadRun = useCallback((id: string) => {
    apiGet<Run>(`/api/runs/${id}`)
      .then((r) => setRun(r))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load the batch."));
  }, []);
  useEffect(() => {
    if (!runId) return;
    setDraft(loadDraft(runId));
    loadRun(runId);
  }, [runId, loadRun]);

  function update(patch: Partial<Draft>) {
    const next = { ...draft, ...patch };
    setDraft(next);
    if (runId) {
      try {
        localStorage.setItem(draftKey(runId), JSON.stringify(next));
      } catch {
        /* storage blocked: the card still works */
      }
    }
  }

  async function act(what: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      setDone(await what());
      loadLists();
      if (runId) loadRun(runId);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "The factory server did not answer. Your card is kept on this device.",
      );
    } finally {
      setBusy(false);
    }
  }

  const pack = packs.find((p) => p.code === packCode);
  const packVersion = pack?.versions.find((v) => v.status === "ACTIVE");
  const recipeVersion = recipes
    .find((r) => r.id === pack?.recipe_id)
    ?.versions.find((v) => v.status === "ACTIVE");

  const start = () =>
    act(async () => {
      const made = await apiPost<{ id?: string; run_id?: string; run_no: string }>("/api/runs", {
        recipe_version_id: recipeVersion?.id,
        batch_multiplier: multiplier,
        run_date: new Date().toLocaleDateString("en-CA"),
        pack_lines: [{ pack_spec_version_id: packVersion?.id }],
      });
      const id = made.id ?? made.run_id ?? "";
      await apiPost(`/api/runs/${id}/start`);
      setRunId(id);
      return `Batch ${made.run_no} started. The recipe and pack are now frozen for this batch.`;
    });

  const ingredients = run?.analysis?.ingredients ?? [];
  const line = run?.analysis?.pack_lines[0];
  const runPack = packs
    .find((p) => p.code === line?.pack_spec)
    ?.versions.find((v) => v.version === line?.pack_spec_version);
  const pouch = runPack?.lines.find((l) => l.item_code.startsWith("pouch"));
  const carton = runPack?.lines.find((l) => l.item_code.startsWith("carton"));

  const preview = useMemo(
    () =>
      ingredients.map((i) => {
        const now = stock[i.item_id] ?? 0;
        const take = num(draft.actual[i.item_id] ?? "") ?? 0;
        return { ...i, now, after: now - take };
      }),
    [ingredients, stock, draft.actual],
  );
  const issuable = preview.some((p) => (num(draft.actual[p.item_id] ?? "") ?? 0) > 0);

  const issue = () =>
    act(async () => {
      const lines = preview
        .filter((p) => (num(draft.actual[p.item_id] ?? "") ?? 0) > 0)
        .map((p) => ({ item_id: p.item_id, qty: draft.actual[p.item_id], unit: p.unit }));
      const r = await apiPost<{ issue_no: string }>(`/api/runs/${runId}/issues`, { lines });
      update({ actual: {} });
      return `Materials issued on ${r.issue_no}. Raw stock is down by exactly these quantities.`;
    });

  const post = () =>
    act(async () => {
      const good = Number(draft.good || "0");
      const damaged = Number(draft.damaged || "0");
      const nets = draft.nets
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const r = await apiPost<{ run_no: string; analysis: { flags: string[] } }>(
        `/api/runs/${runId}/complete`,
        {
          pack_lines: [
            {
              pack_line_id: line?.pack_line_id,
              good_units: String(good),
              packaging: [
                ...(pouch
                  ? [
                      {
                        item_id: pouch.item_id,
                        used: String(good + damaged),
                        damaged: String(damaged),
                      },
                    ]
                  : []),
                ...(carton && draft.cartons
                  ? [{ item_id: carton.item_id, used: draft.cartons }]
                  : []),
              ],
            },
          ],
          scrap_reason: damaged > 0 && draft.reason ? `Damaged pouches: ${draft.reason}` : null,
          fill_weight_samples: nets.map((n) => ({
            net_g: n,
            gross_g: String(Number(n) + POUCH_TARE_G),
          })),
          oil_session: draft.fresh
            ? {
                fresh_ml: String(Number(draft.fresh) * 1000),
                topup_ml: String(Number(draft.topup || "0") * 1000),
                tpc_pct: draft.tpc || null,
              }
            : null,
        },
      );
      try {
        localStorage.removeItem(draftKey(runId ?? ""));
      } catch {
        /* nothing to clear */
      }
      const flags = r.analysis.flags.length ? ` Flagged: ${r.analysis.flags.join("; ")}.` : "";
      return `Batch ${r.run_no} posted: finished packets are in stock.${flags}`;
    });

  const open = runs.filter((r) => r.status === "DRAFT" || r.status === "IN_PROGRESS");

  return (
    <section className="admin-page floor">
      <h1>Batch card</h1>
      <p className="muted">
        One card per batch: issue what was really used, then record what it made. A posted batch is
        never edited; a mistake is corrected with a reversal.
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

      {!run || run.status === "COMPLETED" ? (
        <>
          <h2>Start a batch</h2>
          <div className="floor-row">
            <label>
              Product and pack
              <select value={packCode} onChange={(e) => setPackCode(e.target.value)}>
                {packs.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Batches
              <input
                inputMode="decimal"
                className="big"
                value={multiplier}
                onChange={(e) => setMultiplier(e.target.value)}
              />
            </label>
          </div>
          <div className="floor-bar">
            <button
              type="button"
              className="btn btn-primary btn-lg"
              disabled={busy || !recipeVersion || !packVersion}
              onClick={() => void start()}
            >
              Start batch
            </button>
          </div>
          {open.length > 0 && (
            <>
              <h2>Batches in progress</h2>
              <ul className="plain-list">
                {open.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      className="btn"
                      onClick={() =>
                        r.status === "DRAFT"
                          ? void act(async () => {
                              await apiPost(`/api/runs/${r.id}/start`);
                              setRunId(r.id);
                              return `Batch ${r.run_no} started.`;
                            })
                          : setRunId(r.id)
                      }
                    >
                      {r.status === "DRAFT" ? "Start" : "Open"} {r.run_no} ({r.run_date})
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {run?.status === "COMPLETED" && (
            <p>
              <Link to={`/leaks/${run.id}`}>See where batch {run.run_no}&apos;s money went →</Link>
            </p>
          )}
        </>
      ) : (
        <>
          <h2>
            Batch {run.run_no} <StatusChip tone="info">in progress</StatusChip>
          </h2>
          <h3>1. Materials used</h3>
          <div className="table-wrap">
            <table className="lines">
              <thead>
                <tr>
                  <th>Material</th>
                  <th className="num">Planned</th>
                  <th className="num">Issued so far</th>
                  <th className="num">Actual now</th>
                  <th className="num">In store → after</th>
                </tr>
              </thead>
              <tbody>
                {preview.map((p) => (
                  <tr key={p.item_id}>
                    <td>{words(p.label)}</td>
                    <td className="num">
                      {p.standard} {p.unit}
                    </td>
                    <td className="num">
                      {p.actual} {p.unit}
                    </td>
                    <td className="num">
                      <input
                        className="big"
                        inputMode="decimal"
                        aria-label={`${words(p.label)} used, ${p.unit}`}
                        value={draft.actual[p.item_id] ?? ""}
                        onChange={(e) =>
                          update({ actual: { ...draft.actual, [p.item_id]: e.target.value } })
                        }
                      />
                    </td>
                    <td className={`num ${p.after < 0 ? "bad-text" : ""}`}>
                      {p.now} → {Math.round(p.after * 1000) / 1000} {p.unit}
                      {p.after < 0 && " (not enough)"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="floor-bar">
            <button
              type="button"
              className="btn btn-primary btn-lg"
              disabled={busy || !issuable || preview.some((p) => p.after < 0)}
              onClick={() => void issue()}
            >
              Issue materials
            </button>
          </div>

          <h3>2. What the batch made</h3>
          <div className="floor-row">
            <label>
              Good packets (expected {line?.expected_units})
              <input
                className="big"
                inputMode="numeric"
                value={draft.good}
                onChange={(e) => update({ good: e.target.value })}
              />
            </label>
            <label>
              Damaged pouches
              <input
                className="big"
                inputMode="numeric"
                value={draft.damaged}
                onChange={(e) => update({ damaged: e.target.value })}
              />
            </label>
            <label>
              Cartons used
              <input
                className="big"
                inputMode="numeric"
                value={draft.cartons}
                onChange={(e) => update({ cartons: e.target.value })}
              />
            </label>
          </div>
          {Number(draft.damaged || "0") > 0 && (
            <div className="chips" role="group" aria-label="Why were pouches damaged?">
              {REASONS.map((r) => (
                <button
                  key={r}
                  type="button"
                  className={`chip-btn${draft.reason === r ? " picked" : ""}`}
                  aria-pressed={draft.reason === r}
                  onClick={() => update({ reason: r })}
                >
                  {r}
                </button>
              ))}
            </div>
          )}
          <details>
            <summary>Oil and fill-weight samples (optional)</summary>
            <div className="floor-row">
              <label>
                Fresh oil, L
                <input
                  inputMode="decimal"
                  value={draft.fresh}
                  onChange={(e) => update({ fresh: e.target.value })}
                />
              </label>
              <label>
                Top-ups, L
                <input
                  inputMode="decimal"
                  value={draft.topup}
                  onChange={(e) => update({ topup: e.target.value })}
                />
              </label>
              <label>
                TPC %
                <input
                  inputMode="decimal"
                  value={draft.tpc}
                  onChange={(e) => update({ tpc: e.target.value })}
                />
              </label>
            </div>
            <label>
              Net weights sampled, g (for example 203, 201, 205)
              <input value={draft.nets} onChange={(e) => update({ nets: e.target.value })} />
            </label>
          </details>
          <div className="floor-bar">
            <button
              type="button"
              className="btn btn-primary btn-lg"
              disabled={
                busy || draft.good === "" || (Number(draft.damaged || "0") > 0 && !draft.reason)
              }
              onClick={() => void post()}
            >
              Post batch
            </button>
          </div>
        </>
      )}
    </section>
  );
}
