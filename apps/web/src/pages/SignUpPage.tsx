import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { homeFor } from "../guide/screens";
import { stepsLeft, tourCompleted } from "../guide/memory";
import { STEPS } from "../guide/steps";
import { ApiError, apiPost } from "../lib/api";
import { useSession } from "../lib/sessionContext";

/**
 * Create your own factory (deployment). The new factory is a private sandbox with the same starting data as NIT's
 * Section 5 (items, recipe, prices, opening stock), so the guided tour works in it too. You become its Owner.
 */
export function SignUpPage() {
  const { signIn } = useSession();
  const navigate = useNavigate();
  const [factory, setFactory] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiPost("/api/signup", {
        factory_name: factory.trim(),
        display_name: name.trim(),
        email: email.trim(),
        password,
      });
      const who = await signIn(email.trim(), password);
      navigate(homeFor(who.role), { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not reach the factory server. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!tourCompleted()) return <TourFirst what="create your own factory" />;

  return (
    <section className="signin">
      <h1>Create your own factory</h1>
      <p className="muted">
        Your own private copy, separate from the shared DEMO factory, with the same starting stock,
        recipe and prices as NIT&apos;s exercise. You are its Owner and can use every screen. Use
        fictional data only: this is a demo server.
      </p>
      <form onSubmit={(e) => void submit(e)} className="form">
        <label>
          Factory name
          <input
            required
            minLength={2}
            maxLength={80}
            value={factory}
            onChange={(e) => setFactory(e.target.value)}
            placeholder="Lakshmi Snacks"
          />
        </label>
        <label>
          Your name
          <input
            required
            minLength={2}
            maxLength={80}
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Email
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password (at least 10 characters)
          <input
            type="password"
            required
            minLength={10}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="btn btn-primary btn-lg" disabled={busy}>
          {busy ? "Setting up your factory…" : "Create my factory"}
        </button>
      </form>
      <p className="muted small">
        Just looking? <Link to="/sign-in">Use a shared DEMO login</Link> or{" "}
        <Link to="/guide">follow the guided tour</Link>.
      </p>
    </section>
  );
}

/** The guided tour is the mandatory first task: own accounts open once it has been finished. */
export function TourFirst({ what }: { what: string }) {
  const left = stepsLeft();
  const seen = STEPS.length - left.length;
  const resume = left[0] ?? STEPS[0]!.id;
  return (
    <section className="signin">
      <h1>Take the guided tour first</h1>
      <p>
        Before you {what}, follow the guided tour once with the shared DEMO logins, so the workflow
        makes sense: order → approval → GST invoice → dispatch → payment, and purchase → batch →
        cost → where profit leaks.
      </p>
      <p className="muted">
        {seen} of {STEPS.length} steps seen. When you finish, the tour offers to continue with your
        own account.
      </p>
      <p className="actions-row">
        <Link to={`/guide/${resume}`} className="btn btn-primary btn-lg">
          {seen ? "Continue the tour →" : "Start the guided tour →"}
        </Link>
      </p>
    </section>
  );
}
