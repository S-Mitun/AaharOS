import { Link } from "react-router-dom";
import { STEPS } from "../guide/steps";
import { useT } from "../lib/i18n";

function LoopsDiagram() {
  return (
    <figure className="loops" aria-labelledby="loops-caption">
      <div className="loop loop-sales">
        <span className="loop-name">Sales loop</span>
        <ol>
          <li>Salesman order</li>
          <li>Admin approves</li>
          <li>GST invoice</li>
          <li>Dispatch</li>
          <li>Payment</li>
        </ol>
      </div>
      <div className="loop-meet">
        <span aria-hidden="true">↕</span> Both loops meet at <strong>finished-goods stock</strong>
      </div>
      <div className="loop loop-prod">
        <span className="loop-name">Production loop</span>
        <ol>
          <li>Purchase</li>
          <li>Issue per recipe</li>
          <li>Production batch</li>
          <li>Good packets</li>
          <li>Cost &amp; variance</li>
        </ol>
      </div>
      <figcaption id="loops-caption">
        Everything above flows into the month&apos;s reports for the auditor. Each entry is made
        once, where it happens.
      </figcaption>
    </figure>
  );
}

const ROLES = [
  {
    role: "Salesman",
    device: "Phone",
    job: "Place an order for a shop in under 30 seconds, even offline.",
    route: "/sales",
  },
  {
    role: "Factory admin",
    device: "Desktop",
    job: "Approve orders without overselling, raise GST invoices, dispatch, collect.",
    route: "/admin/orders",
  },
  {
    role: "Production supervisor",
    device: "Tablet",
    job: "Record a batch like the paper batch sheet: planned vs actual.",
    route: "/production/batch/new",
  },
  {
    role: "Owner",
    device: "Any",
    job: "See today's 3 actions and where profit leaks, in rupees.",
    route: "/owner",
  },
  {
    role: "Auditor",
    device: "Desktop, read-only",
    job: "Download the month's reports and trace any number to its source.",
    route: "/auditor/reports",
  },
];

export function HomePage() {
  const { t } = useT();
  return (
    <div className="home">
      <section className="hero">
        <p className="eyebrow">Order-to-audit system for a small snack factory</p>
        <h1>{t("Every gram traced. Every rupee explained.")}</h1>
        <p className="lead">
          Most billing apps record what was sold. AaharOS explains what was <em>made</em>, what it{" "}
          <em>cost</em>, where the profit <em>leaked</em>, and what to do <em>next</em>.
        </p>
        <div className="hero-actions">
          <Link to="/guide" className="btn btn-primary btn-lg">
            {t("Start the guided tour →")}
          </Link>
          <Link to="/sign-in" className="btn btn-lg">
            Sign in
          </Link>
        </div>
      </section>

      <section aria-labelledby="how-h">
        <h2 id="how-h">How it works in one picture</h2>
        <LoopsDiagram />
      </section>

      <section aria-labelledby="ways-h">
        <h2 id="ways-h">Two ways to start</h2>
        <div className="ways">
          <article className="way way-main">
            <span className="way-time">{STEPS.length} short steps · about 8 minutes</span>
            <h3>Follow the guided tour</h3>
            <p>
              One working day of the factory, step by step: who does it, where to click, what to
              type, and the number you should see. A voice reads each step aloud, in English or
              Tamil. Open it any time with the <strong>Guide</strong> button at the bottom right.
            </p>
            <Link to="/guide" className="btn btn-primary">
              Start the tour →
            </Link>
          </article>
          <article className="way">
            <span className="way-time">After the tour</span>
            <h3>Work in your own factory</h3>
            <p>
              Create your own factory: a private copy that starts with the same opening stock,
              recipe and prices, with you as its Owner. Or look around the shared DEMO factory with
              a one-tap login for each role.
            </p>
            <p className="actions-row">
              <Link to="/sign-up" className="btn">
                Create your own factory
              </Link>
              <Link to="/sign-in" className="btn">
                Use a DEMO login
              </Link>
            </p>
          </article>
        </div>
      </section>

      <section aria-labelledby="roles-h">
        <h2 id="roles-h">Who uses it</h2>
        <div className="roles">
          {ROLES.map((r) => (
            <article className="role" key={r.role}>
              <h3>{r.role}</h3>
              <p className="muted small">{r.device}</p>
              <p>{r.job}</p>
              <Link to={r.route} className="link-strong">
                {`Open the ${r.role.toLowerCase()} screen →`}
              </Link>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
