import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Num } from "../components/Num";
import { StatusChip } from "../components/StatusChip";
import { ApiError, apiGet } from "../lib/api";
import { words } from "../owner/planningTypes";
import {
  isSupplier,
  type Batch,
  type BatchBackward,
  type ForwardLot,
  type LotRow,
  type PassportLabelData,
  type Recall,
  type SupplierBackward,
  type Trace,
} from "./traceTypes";

const versioned = (b: Batch) =>
  [
    b.recipe ? `Recipe ${b.recipe.code} v${b.recipe.version}` : "no recipe frozen",
    ...b.packs.map((p) => `Pack ${p.code} v${p.version}`),
  ].join(" · ");

/**
 * Trace and recall (MP13, ADR-0020): pick a lot, see where it came from and where it went, and simulate a recall.
 * Read-only: the recall is a DEMO simulation, nothing is stored and nothing is sent.
 */
export function TracePage() {
  const [params, setParams] = useSearchParams();
  const lotId = params.get("lot");
  const [q, setQ] = useState("");
  const [found, setFound] = useState<LotRow[] | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [recall, setRecall] = useState<Recall | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const search = useCallback((text: string) => {
    apiGet<{ lots: LotRow[] }>(`/api/trace/lots?q=${encodeURIComponent(text)}`)
      .then((r) => setFound(r.lots))
      .catch(() => setError("Could not search the lots."));
  }, []);
  useEffect(() => search(""), [search]);

  useEffect(() => {
    setTrace(null);
    setRecall(null);
    if (!lotId) return;
    apiGet<Trace>(`/api/trace/lots/${lotId}`)
      .then(setTrace)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not trace this lot."));
  }, [lotId]);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setError(null);
    search(q);
  }

  async function simulate() {
    if (!lotId) return;
    setBusy(true);
    setError(null);
    try {
      const why = reason.trim() ? `?reason=${encodeURIComponent(reason.trim())}` : "";
      setRecall(await apiGet<Recall>(`/api/trace/recall/${lotId}${why}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The factory server did not answer.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="admin-page trace">
      <h1>Trace and recall</h1>
      <p className="muted">
        Pick a batch or a supplier lot: where it came from, where every packet went, and what a
        recall would reach. Read-only.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <form className="trace-search" onSubmit={onSearch} role="search">
        <label>
          Lot or batch number
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="B-001, FL-…"
            maxLength={60}
          />
        </label>
        <button type="submit" className="btn">
          Search
        </button>
      </form>
      {found && (
        <ul className="plain-list lot-list" aria-label="Lots found">
          {found.length === 0 && <li className="muted">No lot matches.</li>}
          {found.map((l) => (
            <li key={l.lot_id}>
              <button
                type="button"
                className={`btn-ghost lot-pick ${l.lot_id === lotId ? "is-current" : ""}`}
                aria-current={l.lot_id === lotId ? "true" : undefined}
                onClick={() => setParams({ lot: l.lot_id })}
              >
                <strong>{l.lot_no}</strong> {l.kind_label} · {words(l.item_code)}
                {l.best_before && ` · best before ${l.best_before}`}
              </button>
            </li>
          ))}
        </ul>
      )}

      {trace && (
        <>
          <h2>
            {trace.lot.kind_label} {trace.lot.lot_no}
          </h2>
          <p className="muted">
            {trace.lot.item_name}
            {trace.lot.mfg_date && ` · made on ${trace.lot.mfg_date}`}
            {trace.lot.best_before && ` · best before ${trace.lot.best_before}`}
          </p>
          {isSupplier(trace.backward) ? (
            <SupplierBack back={trace.backward} />
          ) : (
            <BatchBack back={trace.backward} />
          )}
          <h3>Where it went</h3>
          <Forward lots={trace.forward} />
          {trace.lot.kind !== "supplier_lot" && <PassportLabel lot={trace.lot} />}

          <h3>Recall simulator</h3>
          <p className="muted">
            DEMO simulation: it lists what a recall of this lot would reach and drafts a notice.
            Nothing is stored and nothing is sent.
          </p>
          <div className="trace-search">
            <label>
              Reason (for the draft notice)
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="DEMO: suspected quality problem"
                maxLength={200}
              />
            </label>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void simulate()}
            >
              Simulate recall
            </button>
          </div>
          {recall && <RecallView recall={recall} />}
        </>
      )}
    </section>
  );
}

/** The batch passport label: the QR (from the server) that opens the public passport page. */
function PassportLabel({ lot }: { lot: LotRow }) {
  const [label, setLabel] = useState<PassportLabelData | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setLabel(null);
    apiGet<PassportLabelData>(`/api/trace/passport/${lot.lot_id}`)
      .then(setLabel)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not make the label."));
  }, [lot.lot_id]);
  return (
    <>
      <h3>Batch passport</h3>
      {error && <p className="muted">{error}</p>}
      {label && (
        <div className="passport-label" aria-label="Passport label">
          <img
            src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(label.qr_svg)}`}
            alt={`QR code for the passport of lot ${lot.lot_no}`}
          />
          <div>
            <p>
              <strong>{lot.item_name}</strong> · lot {lot.lot_no}
              {lot.best_before && ` · best before ${lot.best_before}`}
            </p>
            <p className="muted small">
              Scanning opens the public passport: product, lot, dates, net quantity and the FSSAI
              number. No prices, no customers.
            </p>
            <a href={label.path} target="_blank" rel="noopener">
              Open the passport
            </a>
          </div>
        </div>
      )}
    </>
  );
}

function BatchCard({ b }: { b: Batch }) {
  return (
    <p>
      <strong>Batch {b.run_no}</strong> made {b.run_date} · {versioned(b)} · operator{" "}
      {b.operator ?? "not recorded"}
    </p>
  );
}

function BatchBack({ back }: { back: BatchBackward }) {
  if (!back.batch) return <p>{back.text ?? "No batch record behind this lot."}</p>;
  return (
    <>
      <h3>Where it came from</h3>
      <BatchCard b={back.batch} />
      <div className="table-wrap" tabIndex={0}>
        <table className="lines">
          <thead>
            <tr>
              <th>Material</th>
              <th>Document</th>
              <th>Date</th>
              <th className="num">Quantity</th>
              <th>May contain</th>
            </tr>
          </thead>
          <tbody>
            {back.materials.map((m) => (
              <tr key={`${m.item_code}-${m.document}`}>
                <td>{words(m.item_code)}</td>
                <td>
                  {m.document}
                  {m.direction === "RETURN" && " (return)"}
                </td>
                <td>{m.posting_date}</td>
                <td className="num">
                  <Num value={m.qty} label={`${words(m.item_code)} on ${m.document}`} />
                </td>
                <td>
                  {m.may_contain.length === 0
                    ? "nothing recorded"
                    : m.may_contain.map((c) => c.label).join("; ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function SupplierBack({ back }: { back: SupplierBackward }) {
  return (
    <>
      <h3>Received</h3>
      <ul className="plain-list">
        {back.receipts.map((r) => (
          <li key={r.receipt_id}>
            {r.receipt_no} from {r.supplier} on {r.received_on}:{" "}
            <Num value={r.accepted} label={`accepted on ${r.receipt_no}`} /> accepted
            {r.status !== "POSTED" && ` (${r.status.toLowerCase()})`}
          </li>
        ))}
      </ul>
      <h3>Batches that may contain it</h3>
      <p className="muted">{back.note}</p>
      <p>
        {back.may_still_be_in_store ? (
          <StatusChip tone="warn">may still be in the store</StatusChip>
        ) : (
          <StatusChip tone="ok">used up: the store has run out of it since</StatusChip>
        )}
      </p>
      {back.batches.length === 0 ? (
        <p className="muted">No batch has used this material since the lot arrived.</p>
      ) : (
        <ul className="plain-list">
          {back.batches.map((b) => (
            <li key={b.run_id}>
              <BatchCard b={b} />
              <span className="muted small">
                {(b.issues ?? []).map((i) => `${i.document} on ${i.posting_date}`).join(", ")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Forward({ lots }: { lots: ForwardLot[] }) {
  if (lots.length === 0) return <p className="muted">No packets have been made from it yet.</p>;
  return (
    <>
      {lots.map((l) => (
        <div key={l.lot_id} className="table-wrap" tabIndex={0}>
          <p>
            <strong>Lot {l.lot_no}</strong>
            {l.best_before && ` (best before ${l.best_before})`}:{" "}
            {l.made && (
              <>
                <Num value={l.made} label={`good packets of ${l.lot_no}`} /> made,{" "}
              </>
            )}
            <Num value={l.dispatched} label={`packets of ${l.lot_no} dispatched`} /> dispatched,{" "}
            <Num value={l.on_hand} label={`packets of ${l.lot_no} on hand`} /> still in the store
          </p>
          {l.dispatches.length > 0 && (
            <table className="lines">
              <thead>
                <tr>
                  <th>Dispatch</th>
                  <th>Date</th>
                  <th>Invoice</th>
                  <th>Customer</th>
                  <th className="num">Packets</th>
                </tr>
              </thead>
              <tbody>
                {l.dispatches.map((d) => (
                  <tr key={`${d.dispatch_id}-${l.lot_id}`}>
                    <td>{d.dispatch_no}</td>
                    <td>{d.dispatch_date}</td>
                    <td>
                      <Link to={`/admin/invoices/${d.invoice_id}`}>{d.invoice_no}</Link>
                    </td>
                    <td>{d.customer_name}</td>
                    <td className="num">{d.packets}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </>
  );
}

/** Print only the draft notice: the class scopes the print stylesheet, then comes off again. */
function printNotice() {
  document.body.classList.add("print-notice");
  window.print();
  document.body.classList.remove("print-notice");
}

function RecallView({ recall }: { recall: Recall }) {
  return (
    <div className="recall" aria-label="Recall simulation">
      <p className="demo-banner" role="note">
        {recall.note}
      </p>
      <p>
        Traced from {recall.subject}: {recall.batches.length}{" "}
        {recall.batches.length === 1 ? "batch" : "batches"}, {recall.lots.length}{" "}
        {recall.lots.length === 1 ? "lot" : "lots"} ·{" "}
        <Num value={recall.totals.made} label="packets made in the affected lots" /> made ·{" "}
        <Num value={recall.totals.dispatched} label="affected packets dispatched" /> dispatched ·{" "}
        <Num value={recall.totals.on_hand} label="affected packets still in the store" /> still in
        the store
      </p>
      {recall.may_contain_note && <p className="muted">{recall.may_contain_note}</p>}
      <div className="table-wrap" tabIndex={0}>
        <table className="lines">
          <thead>
            <tr>
              <th>Customer</th>
              <th className="num">Packets</th>
              <th>Invoices</th>
              <th>Lots</th>
              <th>Last dispatch</th>
            </tr>
          </thead>
          <tbody>
            {recall.customers.map((c) => (
              <tr key={c.customer_id}>
                <td>{c.customer_name}</td>
                <td className="num">
                  <Num value={c.packets} label={`affected packets with ${c.customer_name}`} />
                </td>
                <td>{c.invoice_nos.join(", ")}</td>
                <td>{c.lot_nos.join(", ")}</td>
                <td>{c.last_dispatch}</td>
              </tr>
            ))}
            {recall.customers.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No packets of these lots have been dispatched.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <h3>Draft recall notice</h3>
      <pre className="notice">{recall.notice}</pre>
      <button type="button" className="btn" onClick={printNotice}>
        Print the draft notice
      </button>
    </div>
  );
}
