import { useT } from "../lib/i18n";
import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { DEMO_EMAIL_DOMAIN, tourCompleted } from "../guide/memory";
import { homeFor } from "../guide/screens";
import { ApiError } from "../lib/api";
import { useSession } from "../lib/sessionContext";
import { SignOutButton } from "../shell/SignOutButton";

/** The DEMO logins (make seed-demo). Passwords come from .env; the shared default (also on the hosted demo) is
 * DEMO_PASSWORD, which a tap fills in. */
export const DEMO_PASSWORD = "change-me-demo";
const DEMO_LOGINS = [
  {
    role: "Salesman A",
    email: "salesman.a@aaharos-demo.invalid",
    does: "Takes orders on the phone",
  },
  {
    role: "Salesman B",
    email: "salesman.b@aaharos-demo.invalid",
    does: "Takes orders on the phone",
  },
  {
    role: "Factory admin",
    email: "admin@aaharos-demo.invalid",
    does: "Approves, invoices, dispatches",
  },
  { role: "Production", email: "production@aaharos-demo.invalid", does: "Purchases and batches" },
  { role: "Owner", email: "owner@aaharos-demo.invalid", does: "Sees where profit leaks" },
  {
    role: "Auditor",
    email: "auditor@aaharos-demo.invalid",
    does: "Reads everything, changes nothing",
  },
];

/** Sign in; each role lands on its own home (G7): a salesman on Today, other roles on today's pages. */
export function SignInPage() {
  const { me, signIn } = useSession();
  const { t } = useT();
  const navigate = useNavigate();
  const location = useLocation();
  const next = (location.state as { next?: string } | null)?.next;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [org, setOrg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!email.trim().toLowerCase().endsWith(DEMO_EMAIL_DOMAIN) && !tourCompleted()) {
      setError(
        "Your own account opens after the guided tour. Use a DEMO login above to follow it, then sign in here.",
      );
      return;
    }
    setBusy(true);
    try {
      const who = await signIn(email.trim(), password, org.trim() || undefined);
      const target = next && next !== "/sign-in" && next !== "/" ? next : homeFor(who.role);
      navigate(target, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not reach the factory server. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (me) {
    return (
      <section className="signin">
        <h1>{t("Signed in")}</h1>
        <p>
          {me.user.display_name} · {me.role} · {me.organization.name}
        </p>
        <p className="actions-row">
          <Link className="btn btn-primary" to={homeFor(me.role)}>
            {t("Go to my home screen")}
          </Link>
          <SignOutButton className="btn" />
        </p>
      </section>
    );
  }

  return (
    <section className="signin">
      <h1>{t("Sign in")}</h1>
      <p className="muted">
        Tap a DEMO login: it fills the email and the shared DEMO password (
        <code>{DEMO_PASSWORD}</code>), then press <strong>Sign in</strong>. Everyone shares this
        DEMO factory. After the <Link to="/guide">guided tour</Link>, sign in with your own account
        or <Link to="/sign-up">create your own factory</Link>.
      </p>
      <ul className="demo-logins" aria-label="DEMO logins">
        {DEMO_LOGINS.map((d) => (
          <li key={d.email}>
            <button
              type="button"
              className={`demo-login${email === d.email ? " picked" : ""}`}
              onClick={() => {
                setEmail(d.email);
                setPassword(DEMO_PASSWORD);
              }}
            >
              <strong>{d.role}</strong>
              <span className="muted small">{d.does}</span>
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={(e) => void submit(e)} className="form">
        <label>
          {t("Email")}
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          {t("Password")}
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <details>
          <summary className="muted small">
            Organization code (only if your login belongs to several)
          </summary>
          <label>
            Organization code
            <input value={org} onChange={(e) => setOrg(e.target.value)} />
          </label>
        </details>
        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="btn btn-primary btn-lg" disabled={busy}>
          {busy ? t("Signing in…") : t("Sign in")}
        </button>
      </form>
    </section>
  );
}
