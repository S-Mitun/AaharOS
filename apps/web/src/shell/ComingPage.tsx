import { Link } from "react-router-dom";
import type { Screen } from "../guide/types";

/** A screen that is not built yet: what it will do and when, in plain words. Never sample numbers or fake data. */
export function ComingPage({ screen }: { screen: Screen }) {
  return (
    <section className="narrow coming">
      <p className="eyebrow">
        {screen.group} · Coming in {screen.mp}
      </p>
      <h1>
        <span aria-hidden="true">{screen.icon}</span> {screen.label}
      </h1>
      <p className="lead">{screen.description}</p>
      <p className="muted">
        This screen is not built yet, so it shows nothing rather than made-up figures. AaharOS is
        built one stage at a time; the guided tour marks which steps already work.
      </p>
      <p className="actions-row">
        <Link to="/guide" className="btn btn-primary">
          Open the guided tour
        </Link>
        <Link to="/" className="btn">
          Back to start
        </Link>
      </p>
    </section>
  );
}
