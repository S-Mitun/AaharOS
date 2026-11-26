import { Link } from "react-router-dom";
import { formatValue } from "../lib/format";

export interface ReportColumn {
  key: string;
  label: string;
  kind: string;
}

export interface ReportData {
  name: string;
  title: string;
  organization: string;
  filters: Record<string, string>;
  generated_at: string;
  columns: ReportColumn[];
  rows: Record<string, unknown>[];
  totals: Record<string, string>;
  notes: string[];
}

/** Where a row's source document opens in this app (drill-down). Unknown types have no link. */
function sourceLink(source: unknown): string | null {
  const s = source as { type?: string; id?: string } | undefined;
  if (!s?.type || !s.id) return null;
  if (s.type === "invoice") return `/admin/invoices/${s.id}`;
  if (s.type === "production_run") return `/leaks/${s.id}`;
  if (s.type === "sales_order") return `/admin/orders/${s.id}`;
  return null;
}

function cell(value: unknown, kind: string): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "boolean") return value ? "yes" : "no";
  const text = String(value);
  if (kind === "money") return formatValue(text, "INR");
  if (kind === "pct") return `${text}%`;
  return text;
}

/** Any report from the server: header, notes, rows with drill-down, totals. Exact strings, never floats. */
export function ReportTable({ report }: { report: ReportData }) {
  const numeric = (k: string) => ["money", "qty", "pct"].includes(k);
  return (
    <div className="report">
      <p className="muted small">
        {report.organization} · generated {report.generated_at}
        {Object.keys(report.filters).length > 0 &&
          ` · ${Object.entries(report.filters)
            .map(([k, v]) => `${k} ${v}`)
            .join(", ")}`}
      </p>
      {report.notes.map((n) => (
        <p key={n} className="muted small">
          {n}
        </p>
      ))}
      {report.rows.length === 0 ? (
        <p className="muted">Nothing in this range.</p>
      ) : (
        <div className="table-wrap" tabIndex={0}>
          <table className="lines">
            <thead>
              <tr>
                {report.columns.map((c) => (
                  <th key={c.key} scope="col" className={numeric(c.kind) ? "num" : undefined}>
                    {c.label}
                  </th>
                ))}
                <th scope="col">
                  <span className="sr-only">Source</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {report.rows.map((r, i) => {
                const link = sourceLink(r._source);
                return (
                  <tr key={i}>
                    {report.columns.map((c) => (
                      <td key={c.key} className={numeric(c.kind) ? "num" : undefined}>
                        {cell(r[c.key], c.kind)}
                      </td>
                    ))}
                    <td>{link && <Link to={link}>Open</Link>}</td>
                  </tr>
                );
              })}
            </tbody>
            {Object.keys(report.totals).length > 0 && (
              <tfoot>
                <tr>
                  {report.columns.map((c, i) => (
                    <td key={c.key} className={numeric(c.kind) ? "num" : undefined}>
                      <strong>
                        {c.key in report.totals
                          ? cell(report.totals[c.key], c.kind)
                          : i === 0
                            ? "Total"
                            : ""}
                      </strong>
                    </td>
                  ))}
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </div>
  );
}
