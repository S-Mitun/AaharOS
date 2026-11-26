import { useT } from "../lib/i18n";
import { Link } from "react-router-dom";
import { StatusChip } from "../components/StatusChip";
import { NIT_CHECKS, type Check } from "../guide/checks";
import { STEPS } from "../guide/steps";
import { formatValue, lookup } from "../lib/format";
import type { ScoreRow } from "../lib/guideData";
import { useGuideData } from "../lib/guideStore";

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

function rowStatus(check: Check, rows: ScoreRow[] | null) {
  if (!rows) return <StatusChip tone="info">Not run yet</StatusChip>;
  const mine = rows.filter((r) => check.assertions.includes(r.n));
  if (mine.some((r) => r.status === "FAIL")) return <StatusChip tone="bad">Failing</StatusChip>;
  if (mine.length > 0 && mine.every((r) => r.status === "GREEN"))
    return <StatusChip tone="ok">Passing</StatusChip>;
  const mp = mine.find((r) => r.status === "RED")?.owner_mp;
  return <StatusChip tone="todo">{mp ? `Coming in ${mp}` : "Not built yet"}</StatusChip>;
}

function ChecksTable() {
  const { oracle, scoreboard } = useGuideData();
  const payload = oracle.state === "ok" ? oracle.data : undefined;
  const rows = scoreboard.state === "ok" && scoreboard.data.available ? scoreboard.data.rows : null;
  return (
    <div className="table-wrap" tabIndex={0}>
      <table className="checks">
        <caption className="sr-only">
          NIT benchmark checks with expected values and build status
        </caption>
        <thead>
          <tr>
            <th scope="col">What NIT checks</th>
            <th scope="col">Expected</th>
            <th scope="col">Status in this build</th>
          </tr>
        </thead>
        <tbody>
          {NIT_CHECKS.map((c) => (
            <tr key={c.label}>
              <th scope="row">
                {c.label}
                {c.note ? <span className="cell-note">{c.note}</span> : null}
              </th>
              <td className="num">
                {payload
                  ? c.keys.map((k) => formatValue(lookup(payload, k), c.unit)).join(" / ")
                  : "…"}
              </td>
              <td>{rowStatus(c, rows)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BuildStatus() {
  const { scoreboard } = useGuideData();
  if (scoreboard.state === "loading") return <p className="muted">Checking build status…</p>;
  if (scoreboard.state === "error") return <StatusChip tone="bad">Server not reachable</StatusChip>;
  if (!scoreboard.data.available)
    return <StatusChip tone="info">Benchmark not run on this server yet</StatusChip>;
  const { green, total } = scoreboard.data;
  return (
    <StatusChip
      tone={green === total ? "ok" : "todo"}
    >{`${green} of ${total} benchmark checks passing`}</StatusChip>
  );
}

const ROLES = [
  {
    role: "Salesman",
    device: "Phone",
    job: "Place an order for a shop in under 30 seconds, even offline.",
    mp: "MP08",
  },
  {
    role: "Factory admin",
    device: "Desktop",
    job: "Approve orders without overselling, raise GST invoices, dispatch, collect.",
    mp: "MP09",
  },
  {
    role: "Production supervisor",
    device: "Tablet",
    job: "Record a batch like the paper batch sheet: planned vs actual.",
    mp: "MP06",
  },
  {
    role: "Owner",
    device: "Any",
    job: "See today's 3 actions and where profit leaks, in rupees.",
    mp: "MP12",
  },
  {
    role: "Auditor",
    device: "Desktop, read-only",
    job: "Download the month's reports and trace any number to its source.",
    mp: "MP11",
  },
];

export function HomePage() {
  const { t } = useT();
  const { oracle } = useGuideData();

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
          <a href="#checks" className="btn btn-lg">
            {t("See what gets checked")}
          </a>
        </div>
        <div className="hero-status">
          <BuildStatus />
        </div>
        {oracle.state === "error" && (
          <p className="alert" role="alert">
            The expected values could not be loaded from the server. If you are running locally,
            start the stack with <code>make up</code> and reload.
          </p>
        )}
      </section>

      <section aria-labelledby="how-h">
        <h2 id="how-h">How it works in one picture</h2>
        <LoopsDiagram />
      </section>

      <section aria-labelledby="ways-h">
        <h2 id="ways-h">Three ways to test it</h2>
        <div className="ways">
          <article className="way">
            <span className="way-time">30 seconds</span>
            <h3>Run the NIT benchmark</h3>
            <p>
              One button replays NIT&apos;s nine steps on a separate demo copy and fills a
              scoreboard of 26 checks. Each row links to the tour step that shows it.
            </p>
            <Link to="/judge" className="btn">
              Open Judge Mode
            </Link>
          </article>
          <article className="way way-main">
            <span className="way-time">{STEPS.length} short steps · about 8 minutes</span>
            <h3>Follow the guided tour</h3>
            <p>
              Step by step, in NIT&apos;s order: who does it, where to click, what to type, and the
              number you should see. Open it any time with the <strong>Guide</strong> button at the
              bottom right.
            </p>
            <Link to="/guide" className="btn btn-primary">
              Start the tour →
            </Link>
          </article>
          <article className="way">
            <span className="way-time">Your pace</span>
            <h3>Explore as any role</h3>
            <p>
              Log in as a salesman, admin, production supervisor, owner or auditor of the shared
              DEMO factory (one tap fills the login), or create your own factory to work on your own
              copy. Each role sees only its own job.
            </p>
            <p className="actions-row">
              <Link to="/sign-in" className="btn">
                Use a DEMO login
              </Link>
              <Link to="/sign-up" className="btn">
                Create your own factory
              </Link>
            </p>
          </article>
        </div>
      </section>

      <section id="checks" aria-labelledby="checks-h">
        <h2 id="checks-h">What NIT checks, and what you should see</h2>
        <p className="muted">
          Expected values are read live from the benchmark file in the repository (
          <code>benchmark/expected_results.yaml</code>), not typed into this page.
        </p>
        <ChecksTable />
      </section>

      <section aria-labelledby="roles-h">
        <h2 id="roles-h">Who uses it</h2>
        <div className="roles">
          {ROLES.map((r) => (
            <article className="role" key={r.role}>
              <h3>{r.role}</h3>
              <p className="muted small">{r.device}</p>
              <p>{r.job}</p>
              <StatusChip tone="todo">{`Screen coming in ${r.mp}`}</StatusChip>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
