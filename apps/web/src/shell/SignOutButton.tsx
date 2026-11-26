import { useT } from "../lib/i18n";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../lib/sessionContext";
import { useOutbox } from "../sales/outboxContext";

/**
 * Sign out, wiping what the app stored on this device (G6). If orders are still on the phone, say how many first and
 * offer "Send now" or "Delete them and sign out".
 */
export function SignOutButton({ className = "btn btn-ghost" }: { className?: string }) {
  const { t } = useT();
  const { signOut } = useSession();
  const outbox = useOutbox();
  const navigate = useNavigate();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);

  async function finish() {
    setBusy(true);
    try {
      await outbox.wipe();
      await signOut();
      navigate("/", { replace: true });
    } finally {
      setBusy(false);
      setAsking(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className={className}
        onClick={() => (outbox.unsentCount > 0 ? setAsking(true) : void finish())}
        disabled={busy}
      >
        {t("Sign out")}
      </button>
      {asking && (
        <div className="modal-backdrop">
          <div
            className="modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="unsent-title"
          >
            <h2 id="unsent-title">
              {outbox.unsentCount === 1
                ? "1 order is not with the factory yet"
                : `${outbox.unsentCount} orders are not with the factory yet`}
            </h2>
            <p>
              Signing out deletes everything this app saved on the phone. Send them first, or delete
              them.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-primary btn-lg"
                disabled={busy || !outbox.online}
                onClick={() => {
                  void outbox.sendNow().then(() => setAsking(false));
                }}
              >
                Send now
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={busy}
                onClick={() => void finish()}
              >
                Delete them and sign out
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setAsking(false)}>
                Cancel
              </button>
            </div>
            {!outbox.online && (
              <p className="muted small">No connection right now, so “Send now” is unavailable.</p>
            )}
          </div>
        </div>
      )}
    </>
  );
}
