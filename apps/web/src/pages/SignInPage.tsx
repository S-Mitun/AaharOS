import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { homeFor } from "../guide/screens";
import { ApiError } from "../lib/api";
import { useSession } from "../lib/sessionContext";
import { SignOutButton } from "../shell/SignOutButton";

/** The DEMO logins (make seed-demo). Passwords come from .env; the local default is documented in the README. */
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
    setBusy(true);
    setError(null);
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
        <h1>Signed in</h1>
        <p>
          {me.user.display_name} · {me.role} · {me.organization.name}
        </p>
        <p className="actions-row">
          <Link className="btn btn-primary" to={homeFor(me.role)}>
            Go to my home screen
          </Link>
          <SignOutButton className="btn" />
        </p>
      </section>
    );
  }

  return (
    <section className="signin">
      <h1>Sign in</h1>
      <p className="muted">
        Pick a DEMO login to fill the email, then type the password. Locally the DEMO password is
        the one in <code>.env</code> (default <code>change-me-demo</code>).
      </p>
      <ul className="demo-logins" aria-label="DEMO logins">
        {DEMO_LOGINS.map((d) => (
          <li key={d.email}>
            <button
              type="button"
              className={`demo-login${email === d.email ? " picked" : ""}`}
              onClick={() => setEmail(d.email)}
            >
              <strong>{d.role}</strong>
              <span className="muted small">{d.does}</span>
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={(e) => void submit(e)} className="form">
        <label>
          Email
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
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
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </section>
  );
}
