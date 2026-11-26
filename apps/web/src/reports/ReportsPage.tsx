import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet, apiPost } from "../lib/api";
import { useSession } from "../lib/sessionContext";
import { ReportTable, type ReportData } from "./ReportTable";
import { localDate } from "../lib/dates";

interface Cockpit {
  organization: string;
  month: string;
  locked: boolean;
  checklist: { key: string; label: string; count: number; ok: boolean; link: string }[];
  integrity: { check: string; ok: boolean; problems: number }[];
  can_close: boolean;
  history: {
    id: string;
    locked_at: string;
    reason: string;
    reopened_at: string | null;
    reopen_reason: string | null;
    active: boolean;
  }[];
}

const TABS = [
  { id: "reports", label: "Reports" },
  { id: "gst", label: "GST" },
  { id: "close", label: "Close month" },
  { id: "evidence", label: "Evidence" },
] as const;

const today = () => localDate();
const monthStart = (d: string) => `${d.slice(0, 7)}-01`;

/** Auditor → Reports (MP11): every report with downloads, the GST summary and export, the month-end close and the
 * evidence pack. Every figure comes from posted records on the server. */
export function ReportsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "reports";
  return (
    <section className="admin-page">
      <h1>Reports</h1>
      <p className="muted">
        Registers, stock, production, ageing, GST and the month-end close. Every number is read from
        posted records; every row opens its source document.
      </p>
      <div className="filter-chips" role="tablist" aria-label="Reports sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`filter-chip${tab === t.id ? " on" : ""}`}
            onClick={() => setParams({ tab: t.id })}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "reports" && <ReportsTab />}
      {tab === "gst" && <GstTab />}
      {tab === "close" && <CloseTab />}
      {tab === "evidence" && <EvidenceTab />}
    </section>
  );
}

function ReportsTab() {
  const [catalogue, setCatalogue] = useState<{ name: string; title: string }[]>([]);
  const [name, setName] = useState("sales-register");
  const [from, setFrom] = useState(monthStart(today()));
  const [to, setTo] = useState(today());
  const [report, setReport] = useState<ReportData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<{ reports: { name: string; title: string }[] }>("/api/reports")
      .then((r) => setCatalogue(r.reports))
      .catch(() => setError("Could not load the list of reports."));
  }, []);

  const query =
    name === "receivables-ageing" || name === "bank-statement"
      ? `as_of=${to}`
      : `date_from=${from}&date_to=${to}`;
  const url = `/api/reports/${name}?${query}`;

  async function show() {
    setError(null);
    try {
      setReport(await apiGet<ReportData>(url));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the report.");
    }
  }

  return (
    <>
      <div className="actions-row">
        <label className="field">
          Report
          <select value={name} onChange={(e) => setName(e.target.value)}>
            {catalogue.map((c) => (
              <option key={c.name} value={c.name}>
                {c.title}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          From
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="field">
          To
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>
      <div className="actions-row">
        <button type="button" className="btn btn-primary" onClick={() => void show()}>
          Show
        </button>
        <a className="btn" href={`${url}&format=csv`}>
          CSV
        </a>
        <a className="btn" href={`${url}&format=xlsx`}>
          Excel
        </a>
        <a className="btn" href={`${url}&format=html`} target="_blank" rel="noreferrer">
          Print / PDF
        </a>
      </div>
      {error && <p className="alert">{error}</p>}
      {report && (
        <>
          <h2>{report.title}</h2>
          <ReportTable report={report} />
        </>
      )}
    </>
  );
}

function GstTab() {
  const [month, setMonth] = useState(monthStart(today()));
  const [report, setReport] = useState<ReportData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    apiGet<ReportData>(`/api/reports/gst-summary?month=${month}`)
      .then(setReport)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load the GST summary."),
      );
  }, [month]);

  return (
    <>
      <div className="actions-row">
        <label className="field">
          Month
          <input
            type="month"
            value={month.slice(0, 7)}
            onChange={(e) => setMonth(`${e.target.value}-01`)}
          />
        </label>
        <a className="btn" href={`/api/reports/gstr1-export?month=${month}`}>
          GSTR-1 file (JSON, for review)
        </a>
        <a className="btn" href={`/api/reports/gst-summary?month=${month}&format=xlsx`}>
          Excel
        </a>
      </div>
      <p className="muted small">
        The GSTR-1 file is shaped like the portal&apos;s offline tool for your chartered accountant
        to review. Nothing is filed or sent.
      </p>
      {error && <p className="alert">{error}</p>}
      {report && <ReportTable report={report} />}
    </>
  );
}

function CloseTab() {
  const { me } = useSession();
  const [month, setMonth] = useState(monthStart(today()));
  const [cockpit, setCockpit] = useState<Cockpit | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const can = (p: string) => !!me?.permissions.includes(p);

  const load = useCallback(() => {
    apiGet<Cockpit>(`/api/reports/close?month=${month}`)
      .then(setCockpit)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not load the close cockpit."),
      );
  }, [month]);
  useEffect(load, [load]);

  async function act(path: "lock" | "reopen") {
    setError(null);
    setDone(null);
    try {
      setCockpit(await apiPost<Cockpit>(`/api/reports/close/${path}`, { month, reason }));
      setReason("");
      setDone(
        path === "lock" ? "Month closed: postings dated in it are now refused." : "Month reopened.",
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The factory server did not answer.");
    }
  }

  return (
    <>
      <label className="field">
        Month
        <input
          type="month"
          value={month.slice(0, 7)}
          onChange={(e) => setMonth(`${e.target.value}-01`)}
        />
      </label>
      {error && <p className="alert">{error}</p>}
      {done && <p className="banner banner-ok">{done}</p>}
      {cockpit && (
        <>
          <p>
            {cockpit.locked ? (
              <StatusChip tone="info">Closed</StatusChip>
            ) : (
              <StatusChip tone="todo">Open</StatusChip>
            )}
          </p>
          <h2>Before you close</h2>
          <ul className="checklist">
            {cockpit.checklist.map((c) => (
              <li key={c.key}>
                {c.ok ? (
                  <StatusChip tone="ok">Done</StatusChip>
                ) : (
                  <StatusChip tone="warn">{String(c.count)}</StatusChip>
                )}{" "}
                {c.ok ? c.label : <Link to={c.link}>{c.label}</Link>}
              </li>
            ))}
          </ul>
          <h2>Integrity</h2>
          <ul className="checklist">
            {cockpit.integrity.map((c) => (
              <li key={c.check}>
                {c.ok ? (
                  <StatusChip tone="ok">Pass</StatusChip>
                ) : (
                  <StatusChip tone="bad">Fail</StatusChip>
                )}{" "}
                {c.check}
              </li>
            ))}
          </ul>
          {((!cockpit.locked && can("period.lock")) ||
            (cockpit.locked && can("period.reopen"))) && (
            <div className="option">
              <label className="field">
                Reason
                <input value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              {!cockpit.locked ? (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!cockpit.can_close || reason.trim().length < 3}
                  onClick={() => void act("lock")}
                >
                  Close the month
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={reason.trim().length < 3}
                  onClick={() => void act("reopen")}
                >
                  Reopen the month
                </button>
              )}
              {!cockpit.can_close && !cockpit.locked && (
                <p className="muted small">
                  An integrity check fails, so the month cannot be closed.
                </p>
              )}
            </div>
          )}
          {cockpit.history.length > 0 && (
            <>
              <h2>History</h2>
              <ul>
                {cockpit.history.map((h) => (
                  <li key={h.id}>
                    Closed {h.locked_at.slice(0, 16).replace("T", " ")}: {h.reason}
                    {h.reopened_at &&
                      ` · reopened ${h.reopened_at.slice(0, 16).replace("T", " ")}: ${h.reopen_reason}`}
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </>
  );
}

function EvidenceTab() {
  const [from, setFrom] = useState(monthStart(today()));
  const [to, setTo] = useState(today());
  const [bank, setBank] = useState<ReportData | null>(null);
  useEffect(() => {
    apiGet<ReportData>(`/api/reports/bank-statement?as_of=${to}`)
      .then(setBank)
      .catch(() => setBank(null));
  }, [to]);
  return (
    <>
      <div className="actions-row">
        <label className="field">
          From
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="field">
          To
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>
      <div className="actions-row">
        <a
          className="btn btn-primary"
          href={`/api/reports/evidence-pack?date_from=${from}&date_to=${to}`}
        >
          Download the Evidence Pack (ZIP)
        </a>
        <a className="btn" href={`/api/reports/tally-xml?date_from=${from}&date_to=${to}`}>
          Tally XML (sales vouchers)
        </a>
      </div>
      <p className="muted small">
        The pack holds every report, the GSTR-1 file, every stock movement, the audit-chain check
        with its head hash, the integrity results and the assumptions.
      </p>
      {bank && (
        <>
          <h2>{bank.title}</h2>
          <ReportTable report={bank} />
        </>
      )}
    </>
  );
}
