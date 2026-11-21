import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useSession } from "../lib/sessionContext";

/** A screen that needs data: signed out, it asks to sign in; signed in without the permission, it says so. */
export function Gate({
  permission,
  what,
  children,
}: {
  permission: string;
  what: string;
  children: ReactNode;
}) {
  const { me, loading } = useSession();
  const location = useLocation();
  if (loading) return <p className="muted narrow">Loading…</p>;
  if (!me) {
    return (
      <section className="narrow gate">
        <h1>Sign in to see {what}</h1>
        <p className="muted">
          This screen shows real data from the factory, so it needs a login. The DEMO logins are on
          the sign-in page.
        </p>
        <Link className="btn btn-primary btn-lg" to="/sign-in" state={{ next: location.pathname }}>
          Sign in
        </Link>
      </section>
    );
  }
  if (!me.permissions.includes(permission)) {
    return (
      <section className="narrow gate">
        <h1>Not part of your role</h1>
        <p>
          You are signed in as <strong>{me.role}</strong>. {what[0]?.toUpperCase()}
          {what.slice(1)} belongs to another role, so this screen is hidden from your menu.
        </p>
        <Link className="btn" to="/sign-in">
          Switch user
        </Link>
      </section>
    );
  }
  return <>{children}</>;
}
