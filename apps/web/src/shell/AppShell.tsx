import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { GuideDrawer } from "../components/GuideDrawer";
import { useSession } from "../lib/sessionContext";
import { Sidebar } from "./Sidebar";
import { SignOutButton } from "./SignOutButton";

/** One app for every role (G9): a grouped sidebar, a top bar with who is signed in, and the page. At phone width the
 * sidebar folds into a Menu button. */
export function AppShell() {
  const { me } = useSession();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
    document.documentElement.scrollTop = 0; // a new screen starts at its top
  }, [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <button
          type="button"
          className="menu-btn"
          aria-expanded={menuOpen}
          aria-controls="sidebar"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <span aria-hidden="true">☰</span> Menu
        </button>
        <Link to="/" className="brand" aria-label="AaharOS home">
          <span className="brand-mark" aria-hidden="true">
            ▲
          </span>
          AaharOS
        </Link>
        <span className="demo-tag" title="All data is fictional">
          DEMO
        </span>
        <div className="topbar-right">
          {me ? (
            <>
              <span className="who">
                <strong>{me.user.display_name}</strong>
                <span className="muted small"> · {me.role}</span>
              </span>
              <SignOutButton />
            </>
          ) : (
            <Link className="btn btn-primary" to="/sign-in" state={{ next: pathname }}>
              Sign in
            </Link>
          )}
        </div>
      </header>
      <div className="shell-body">
        <aside id="sidebar" className={`sidebar${menuOpen ? " open" : ""}`} aria-label="Menu">
          <Sidebar me={me} onNavigate={() => setMenuOpen(false)} />
        </aside>
        {menuOpen && <div className="sidebar-backdrop" onClick={() => setMenuOpen(false)} />}
        <div className="shell-main">
          <main id="main">
            <Outlet />
          </main>
          <footer className="footer">
            <p>
              Prototype for the NIT Tiruchirappalli CDI internship task. All companies, people,
              GSTINs and licence numbers are fictional <strong>DEMO</strong> data.
            </p>
          </footer>
        </div>
      </div>
      <GuideDrawer />
    </div>
  );
}
