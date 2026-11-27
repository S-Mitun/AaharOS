import { useT } from "../lib/i18n";
import { Link } from "react-router-dom";
import { screenFor } from "../guide/screens";
import { STEPS_TA } from "../guide/stepsTa";
import type { GuideStep } from "../guide/types";
import { fillTemplate } from "../lib/format";
import { useGuideData } from "../lib/guideStore";
import { ExpectList } from "./ExpectList";

export function StepCard({ step, compact = false }: { step: GuideStep; compact?: boolean }) {
  const { t, lang } = useT();
  const ta = lang === "ta" ? STEPS_TA[step.id] : undefined;
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
        <h2 id={`step-${step.id}`}>{ta?.title ?? step.title}</h2>
      </header>

      <div className="step-meta">
        <div>
          <span className="meta-label">Who</span>
          <span>
            <strong>{ta?.role ?? step.who.role}</strong> · {ta?.login ?? step.who.login}
          </span>
        </div>
        <div>
          <span className="meta-label">Where</span>
          <span>
            {screen.name}{" "}
            <Link to={screen.route} className="link-strong">
              {t("Take me there")} →
            </Link>
          </span>
        </div>
      </div>

      <section>
        <h3>What to do</h3>
        <ol className="actions">
          {(ta?.actions ?? step.actions).map((a) => (
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
          <p>{ta?.why ?? step.why}</p>
        </section>
      )}
    </article>
  );
}
