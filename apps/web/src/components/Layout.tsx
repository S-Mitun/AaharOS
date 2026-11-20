import { Link, Outlet } from "react-router-dom";
import { GuideDrawer } from "./GuideDrawer";

export function Layout() {
  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <Link to="/" className="brand" aria-label="AaharOS home">
          <span className="brand-mark" aria-hidden="true">
            ▲
          </span>
          AaharOS
        </Link>
        <nav aria-label="Main" className="topnav">
          <Link to="/">Start here</Link>
          <Link to="/guide">Guided tour</Link>
        </nav>
      </header>
      <main id="main">
        <Outlet />
      </main>
      <footer className="footer">
        <p>
          Prototype for the NIT Tiruchirappalli CDI internship task. All companies, people, GSTINs
          and licence numbers are fictional <strong>DEMO</strong> data.
        </p>
      </footer>
      <GuideDrawer />
    </div>
  );
}
