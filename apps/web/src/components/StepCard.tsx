import { Link } from "react-router-dom";
import { screenFor } from "../guide/screens";
import type { GuideStep } from "../guide/types";
import { fillTemplate } from "../lib/format";
import { useGuideData } from "../lib/guideStore";
import { ExpectList } from "./ExpectList";
import { StatusChip } from "./StatusChip";

function ProofStatus({ assertions }: { assertions: number[] }) {
  const { scoreboard } = useGuideData();
  if (assertions.length === 0) return null;
  if (scoreboard.state !== "ok" || !scoreboard.data.available) {
    return <p className="muted small">Benchmark rows {assertions.join(", ")} check this step.</p>;
  }
  const rows = scoreboard.data.rows.filter((r) => assertions.includes(r.n));
  const green = rows.filter((r) => r.status === "GREEN").length;
  return (
    <p className="proof">
      <span className="muted small">Checked by benchmark rows {assertions.join(", ")}: </span>
      {green === rows.length ? (
        <StatusChip tone="ok">{`All ${rows.length} passing`}</StatusChip>
      ) : (
        <StatusChip tone="todo">{`${green} of ${rows.length} built so far`}</StatusChip>
      )}
    </p>
  );
}

export function StepCard({ step, compact = false }: { step: GuideStep; compact?: boolean }) {
  const { oracle } = useGuideData();
  const payload = oracle.state === "ok" ? oracle.data : undefined;
  const screen = screenFor(step.screen);
  const fill = (t: string) => (payload ? fillTemplate(t, payload) : t.replace(/\{[^}]+\}/g, "…"));

  return (
    <article
      className={`step-card${compact ? " compact" : ""}`}
      aria-labelledby={`step-${step.id}`}
    >
      <header className="step-head">
        {step.nitStep ? <span className="step-badge">NIT step {step.nitStep}</span> : null}
        <h2 id={`step-${step.id}`}>{step.title}</h2>
      </header>

      <div className="step-meta">
        <div>
          <span className="meta-label">Who</span>
          <span>
            <strong>{step.who.role}</strong> · {step.who.login}
          </span>
        </div>
        <div>
          <span className="meta-label">Where</span>
          <span>
            {screen.name}{" "}
            {screen.built ? (
              <Link to={screen.route} className="link-strong">
                Take me there →
              </Link>
            ) : (
              <StatusChip tone="todo">{`Coming in ${screen.mp}`}</StatusChip>
            )}
          </span>
        </div>
      </div>

      <section>
        <h3>What to do</h3>
        <ol className="actions">
          {step.actions.map((a) => (
            <li key={a}>{fill(a)}</li>
          ))}
        </ol>
      </section>

      <section>
        <h3>What you should see</h3>
        <ExpectList items={step.expect} />
      </section>

      {!compact && (
        <section className="why">
          <h3>Why it matters</h3>
          <p>{step.why}</p>
        </section>
      )}
      <ProofStatus assertions={step.assertions} />
    </article>
  );
}
