import { useCallback, useEffect, useState } from "react";
import { ApiError, api, apiGet, apiPost } from "../lib/api";
import { useSession } from "../lib/sessionContext";

interface SettingRow {
  key: string;
  label: string;
  unit: string;
  value: string | null;
}
interface TaxRule {
  id: string;
  hsn: string;
  rate_pct: string;
  effective_from: string;
  effective_to: string | null;
}

const DECIMAL = /^\d{1,12}(\.\d{1,6})?$/;
const tomorrow = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
};

/**
 * Owner → Settings: the numbers the factory may change (thresholds, prices, GST rates). Every change is a new value
 * from a date, never an edit of the past: batches and invoices already posted keep the value they were made with.
 */
export function SettingsPage() {
  const { me } = useSession();
  const canChange = me?.permissions.includes("settings.manage") ?? false;
  const [rows, setRows] = useState<SettingRow[] | null>(null);
  const [rules, setRules] = useState<TaxRule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ key: string; value: string; from: string } | null>(null);
  const [rule, setRule] = useState({ hsn: "", rate_pct: "", from: tomorrow() });

  const load = useCallback(() => {
    Promise.all([
      apiGet<{ settings: SettingRow[] }>("/api/settings"),
      apiGet<{ rules: TaxRule[] }>("/api/tax/rules"),
    ])
      .then(([s, t]) => {
        setRows(s.settings);
        setRules(t.rules);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load the settings."));
  }, []);
  useEffect(load, [load]);

  async function save() {
    if (!edit) return;
    setError(null);
    try {
      await api("PUT", `/api/settings/${edit.key}`, {
        value: edit.value,
        effective_from: edit.from,
      });
      setDone(`Saved: the new value applies from ${edit.from}.`);
      setEdit(null);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the setting.");
    }
  }

  async function addRule() {
    setError(null);
    try {
      await apiPost("/api/tax/rules", {
        hsn: rule.hsn,
        rate_pct: rule.rate_pct,
        effective_from: rule.from,
      });
      setDone(`GST ${rule.rate_pct}% for HSN ${rule.hsn} applies from ${rule.from}.`);
      setRule({ hsn: "", rate_pct: "", from: tomorrow() });
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add the GST rate.");
    }
  }

  return (
    <section className="admin-page">
      <h1>Settings</h1>
      <p className="muted">
        A change applies from the date you pick. Anything already posted keeps the value it was made
        with, so the past never changes.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {done && (
        <p className="banner banner-ok" role="status">
          <span aria-hidden="true">✓</span> {done}
        </p>
      )}
      {!rows && !error && <p className="muted">Loading…</p>}

      {rows && (
        <div className="table-wrap" tabIndex={0}>
          <table className="lines">
            <thead>
              <tr>
                <th scope="col">Setting</th>
                <th scope="col" className="num">
                  Today
                </th>
                <th scope="col">Unit</th>
                {canChange && <th scope="col">Change</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td>{r.label}</td>
                  <td className="num">{r.value ?? "not set"}</td>
                  <td>{r.unit}</td>
                  {canChange && (
                    <td>
                      {edit?.key === r.key ? (
                        <span className="actions-row">
                          <label className="field">
                            New value
                            <input
                              inputMode="decimal"
                              value={edit.value}
                              onChange={(e) => setEdit({ ...edit, value: e.target.value })}
                            />
                          </label>
                          <label className="field">
                            From
                            <input
                              type="date"
                              value={edit.from}
                              onChange={(e) => setEdit({ ...edit, from: e.target.value })}
                            />
                          </label>
                          <button
                            type="button"
                            className="btn btn-primary"
                            disabled={!DECIMAL.test(edit.value) || !edit.from}
                            onClick={() => void save()}
                          >
                            Save
                          </button>
                          <button type="button" className="btn" onClick={() => setEdit(null)}>
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="btn"
                          aria-label={`Change ${r.label}`}
                          onClick={() => {
                            setDone(null);
                            setEdit({ key: r.key, value: r.value ?? "", from: tomorrow() });
                          }}
                        >
                          Change
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>GST rates</h2>
      <div className="table-wrap" tabIndex={0}>
        <table className="lines">
          <thead>
            <tr>
              <th scope="col">HSN</th>
              <th scope="col" className="num">
                Rate
              </th>
              <th scope="col">From</th>
              <th scope="col">Until</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((t) => (
              <tr key={t.id}>
                <td>{t.hsn}</td>
                <td className="num">{t.rate_pct}%</td>
                <td>{t.effective_from}</td>
                <td>{t.effective_to ?? "open"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canChange && (
        <>
          <h3>Add a GST rate</h3>
          <div className="actions-row">
            <label className="field">
              HSN
              <input
                inputMode="numeric"
                value={rule.hsn}
                onChange={(e) => setRule({ ...rule, hsn: e.target.value })}
              />
            </label>
            <label className="field">
              Rate (%)
              <input
                inputMode="decimal"
                value={rule.rate_pct}
                onChange={(e) => setRule({ ...rule, rate_pct: e.target.value })}
              />
            </label>
            <label className="field">
              From
              <input
                type="date"
                value={rule.from}
                onChange={(e) => setRule({ ...rule, from: e.target.value })}
              />
            </label>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!/^\d{4,8}$/.test(rule.hsn) || !/^\d{1,3}(\.\d{1,2})?$/.test(rule.rate_pct)}
            onClick={() => void addRule()}
          >
            Add GST rate
          </button>
          <p className="muted small">
            The rate before it ends the day before; invoices already posted keep their rate. Check
            rates with a chartered accountant (DEMO values).
          </p>
        </>
      )}
    </section>
  );
}
