import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, apiGet } from "../lib/api";

/** What /api/public/passport returns: only what is printed on the pack. */
export interface PublicPassport {
  demo: string;
  factory: string;
  fssai_no: string | null;
  product: string;
  lot_no: string;
  made_on: string | null;
  best_before: string | null;
  past_best_before: boolean;
  net_quantity: string | null;
  can_ask_for_more: boolean;
}

/**
 * The public batch passport (MP13, T4): opened by scanning the QR on a pack or an invoice, with no login. It shows
 * the label facts only. "Ask for more" hands the retailer's phone a link for their salesman; the salesman opens it
 * signed in and submits the pre-filled order, so a scan never places an order by itself.
 */
export function PassportPage() {
  const { token = "" } = useParams();
  const [p, setP] = useState<PublicPassport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shared, setShared] = useState<string | null>(null);

  useEffect(() => {
    apiGet<PublicPassport>(`/api/public/passport/${encodeURIComponent(token)}`)
      .then(setP)
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "The factory server did not answer."),
      );
  }, [token]);

  const reorderUrl = `${window.location.origin}/sales/reorder/${encodeURIComponent(token)}`;
  const message = p ? `Please send more ${p.product} (batch ${p.lot_no}). Open: ${reorderUrl}` : "";

  async function askForMore() {
    if (navigator.share) {
      try {
        await navigator.share({ title: "Ask for more", text: message });
        setShared("Sent to your share sheet.");
      } catch {
        setShared(null); // cancelled
      }
      return;
    }
    window.open(`https://wa.me/?text=${encodeURIComponent(message)}`, "_blank", "noopener");
  }

  return (
    <main className="passport" id="main">
      <p className="demo-banner" role="note">
        {p?.demo ?? "DEMO: fictional factory and product, not for sale."}
      </p>
      <h1>Batch passport</h1>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {!p && !error && <p className="muted">Loading…</p>}
      {p && (
        <>
          <dl className="passport-facts">
            <dt>Product</dt>
            <dd>{p.product}</dd>
            <dt>Batch / lot</dt>
            <dd>{p.lot_no}</dd>
            <dt>Net quantity</dt>
            <dd>{p.net_quantity ?? "not recorded"}</dd>
            <dt>Made on</dt>
            <dd>{p.made_on ?? "not recorded"}</dd>
            <dt>Best before</dt>
            <dd>
              {p.best_before ?? "not recorded"}
              {p.past_best_before && (
                <strong className="past"> (past its best-before date: do not sell)</strong>
              )}
            </dd>
            <dt>Made by</dt>
            <dd>{p.factory}</dd>
            <dt>FSSAI licence</dt>
            <dd>{p.fssai_no ?? "not set"}</dd>
          </dl>
          {p.can_ask_for_more && (
            <>
              <button
                type="button"
                className="btn btn-primary btn-lg"
                onClick={() => void askForMore()}
              >
                Ask for more
              </button>
              <p className="muted small">
                Sends your salesman a link to a ready order. Nothing is ordered until they confirm
                it.
              </p>
              {shared && <p role="status">{shared}</p>}
            </>
          )}
        </>
      )}
    </main>
  );
}

/** The salesman's end of "Ask for more": resolve the link to one of their customers, then open the order. */
export function ReorderPage() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<{ customer_id: string; order_path: string }>(
      `/api/trace/reorder/${encodeURIComponent(token)}`,
    )
      .then((r) => navigate(r.order_path, { replace: true }))
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "The factory server did not answer."),
      );
  }, [token, navigate]);

  return (
    <section className="narrow">
      <h1>Ask for more</h1>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : (
        <p className="muted">Opening the order…</p>
      )}
    </section>
  );
}
