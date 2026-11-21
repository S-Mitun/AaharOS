import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useSession } from "../lib/sessionContext";

/** A plain sign-in (ADR-0014, F8). Role-specific home screens arrive with MP08. */
export function SignInPage() {
  const { me, signIn, signOut } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const next = (location.state as { next?: string } | null)?.next ?? "/leaks";
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
      await signIn(email.trim(), password, org.trim() || undefined);
      navigate(next, { replace: true });
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
        <p className="actions">
          <Link className="btn btn-primary" to="/leaks">
            Where profit leaks
          </Link>
          <button type="button" className="btn" onClick={() => void signOut()}>
            Sign out
          </button>
        </p>
      </section>
    );
  }

  return (
    <section className="signin">
      <h1>Sign in</h1>
      <p className="muted">Use one of the DEMO logins listed in the README.</p>
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
        <label>
          Organization code{" "}
          <span className="muted small">(only if your login belongs to several)</span>
          <input value={org} onChange={(e) => setOrg(e.target.value)} />
        </label>
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
