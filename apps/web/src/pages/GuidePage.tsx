import { useEffect, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { StepCard } from "../components/StepCard";
import { rememberStep } from "../guide/memory";
import { STEPS, stepIndex } from "../guide/steps";

export function GuidePage() {
  const { stepId } = useParams();
  const navigate = useNavigate();
  const index = stepIndex(stepId);
  const step = STEPS[index]!;
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    rememberStep(step.id);
    headingRef.current?.focus();
  }, [step.id]);

  const prev = STEPS[index - 1];
  const next = STEPS[index + 1];

  return (
    <div className="guide">
      <div className="guide-top">
        <h1 tabIndex={-1} ref={headingRef}>
          Guided tour
        </h1>
        <p className="progress-text" aria-live="polite">
          Step {index + 1} of {STEPS.length}
        </p>
        <div
          className="progress"
          role="progressbar"
          aria-valuemin={1}
          aria-valuemax={STEPS.length}
          aria-valuenow={index + 1}
          aria-label="Tour progress"
        >
          <div
            className="progress-bar"
            style={{ width: `${((index + 1) / STEPS.length) * 100}%` }}
          />
        </div>
      </div>

      <div className="guide-body">
        <nav aria-label="Tour steps" className="guide-steps">
          <ol>
            {STEPS.map((s, i) => (
              <li key={s.id}>
                <Link
                  to={`/guide/${s.id}`}
                  className={
                    i === index ? "step-link current" : i < index ? "step-link done" : "step-link"
                  }
                  aria-current={i === index ? "step" : undefined}
                >
                  <span className="step-num" aria-hidden="true">
                    {i < index ? "✓" : i + 1}
                  </span>
                  {s.title}
                </Link>
              </li>
            ))}
          </ol>
        </nav>

        <div className="guide-main">
          <StepCard step={step} />
          <div className="guide-nav">
            <button
              type="button"
              className="btn"
              disabled={!prev}
              onClick={() => prev && navigate(`/guide/${prev.id}`)}
            >
              ← Back
            </button>
            {next ? (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate(`/guide/${next.id}`)}
              >
                Next: {next.title} →
              </button>
            ) : (
              <Link to="/" className="btn btn-primary">
                Finish → back to start
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
