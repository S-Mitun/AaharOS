import { LanguageSwitch, useT } from "../lib/i18n";
import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { restartTour } from "../guide/memory";
import { STEPS } from "../guide/steps";
import { GuideDrawer } from "../components/GuideDrawer";
import { useSession } from "../lib/sessionContext";
import { HowToPanel, onOpenHowToPanel } from "./HowToPanel";
import { Sidebar } from "./Sidebar";
import { SignOutButton } from "./SignOutButton";

/** One app for every role (G9): a grouped sidebar, a top bar with who is signed in, and the page. At phone width the
 * sidebar folds into a Menu button. */
/** Always at the top, signed in or not: start the guided tour again from step 1, as often as wanted. */
function RestartTourButton() {
  const navigate = useNavigate();
  const { t } = useT();
  return (
    <button
      type="button"
      className="btn btn-ghost restart-tour"
      aria-label={t("Restart tour")}
      onClick={() => {
        restartTour();
        navigate(`/guide/${STEPS[0]!.id}`);
      }}
    >
      <span aria-hidden="true">↺</span> <span className="restart-label">{t("Restart tour")}</span>
    </button>
  );
}

export function AppShell() {
  const { t } = useT();
  const { me } = useSession();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [howTo, setHowTo] = useState(() => {
    try {
      return window.sessionStorage.getItem("aaharos.howto") === "1";
    } catch {
      return false;
    }
  });
  const toggleHowTo = (open: boolean) => {
    setHowTo(open);
    try {
      window.sessionStorage.setItem("aaharos.howto", open ? "1" : "0");
    } catch {
      /* storage blocked */
    }
  };

  useEffect(() => {
    setMenuOpen(false);
    document.documentElement.scrollTop = 0; // a new screen starts at its top
  }, [pathname]);
  useEffect(() => onOpenHowToPanel(() => toggleHowTo(true)));
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        {t("Skip to content")}
      </a>
      <header className="topbar">
        <button
          type="button"
          className="menu-btn"
          aria-expanded={menuOpen}
          aria-controls="sidebar"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <span aria-hidden="true">☰</span> {t("Menu")}
        </button>
        <Link to="/" className="brand" aria-label="AaharOS home">
          <span className="brand-mark" aria-hidden="true">
            ▲
          </span>
          <span className="brand-name">AaharOS</span>
        </Link>
        <span className="demo-tag" title="All data is fictional">
          DEMO
        </span>
        <div className="topbar-right">
          <LanguageSwitch />
          <button
            type="button"
            className={`btn btn-ghost howto-btn${pathname === "/how-to" ? " active" : ""}`}
            aria-label={t("Instructions")}
            onClick={() => navigate("/how-to")}
          >
            <span aria-hidden="true">?</span>{" "}
            <span className="howto-label">{t("Instructions")}</span>
          </button>
          <RestartTourButton />
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
              {t("Sign in")}
            </Link>
          )}
        </div>
      </header>
      <div className="shell-body">
        <aside id="sidebar" className={`sidebar${menuOpen ? " open" : ""}`} aria-label="Menu">
          <Sidebar me={me} onNavigate={() => setMenuOpen(false)} />
        </aside>
        {menuOpen && <div className="sidebar-backdrop" onClick={() => setMenuOpen(false)} />}
        <div className={`shell-main${howTo ? " with-howto" : ""}`}>
          <main id="main">
            <Outlet />
          </main>
          <footer className="footer">
            <p>
              All companies, people, GSTINs and licence numbers in this app are fictional{" "}
              <strong>DEMO</strong> data.
            </p>
          </footer>
        </div>
        {howTo && <HowToPanel onClose={() => toggleHowTo(false)} />}
      </div>
      <GuideDrawer />
    </div>
  );
}
