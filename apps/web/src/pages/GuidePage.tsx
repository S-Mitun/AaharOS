import { useT } from "../lib/i18n";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { StepCard } from "../components/StepCard";
import {
  doneSteps,
  markStepDone,
  markTourCompleted,
  rememberStep,
  restartTour,
  stepsLeft,
} from "../guide/memory";
import { STEPS, stepIndex } from "../guide/steps";
import { STEPS_TA } from "../guide/stepsTa";
import { VoiceGuide } from "../guide/VoiceGuide";

export function GuidePage() {
  const { stepId } = useParams();
  const navigate = useNavigate();
  const { t, lang } = useT();
  const titleOf = (s: (typeof STEPS)[number]) =>
    (lang === "ta" ? STEPS_TA[s.id]?.title : null) ?? s.title;
  const index = stepIndex(stepId);
  const step = STEPS[index]!;
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    rememberStep(step.id);
    headingRef.current?.focus();
  }, [step.id]);

  const [done, setDone] = useState<string[]>(doneSteps);
  const isDone = done.includes(step.id);
  // A step opens only when every step before it is done (the list on the left cannot skip ahead either).
  const firstOpen = STEPS.findIndex((s) => !done.includes(s.id));
  const reachable = (i: number) => firstOpen < 0 || i <= firstOpen;
  useEffect(() => {
    if (!reachable(index)) navigate(`/guide/${STEPS[firstOpen]!.id}`, { replace: true });
  });
  const prev = STEPS[index - 1];
  const next = STEPS[index + 1];
  const [finished, setFinished] = useState<string[] | null>(null); // null: not asked yet; []: done; else steps left

  function finish() {
    const left = stepsLeft();
    if (left.length === 0) markTourCompleted();
    setFinished(left);
  }

  return (
    <div className="guide">
      <div className="guide-top">
        <h1 tabIndex={-1} ref={headingRef}>
          {t("Guided tour")}
        </h1>
        <p className="progress-text" aria-live="polite">
          {lang === "ta"
            ? `படி ${index + 1} / ${STEPS.length}`
            : `Step ${index + 1} of ${STEPS.length}`}
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
                {!reachable(i) ? (
                  <span className="step-link locked" aria-disabled="true">
                    <span className="step-num" aria-hidden="true">
                      🔒
                    </span>
                    {titleOf(s)}
                  </span>
                ) : (
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
                    {titleOf(s)}
                  </Link>
                )}
              </li>
            ))}
          </ol>
        </nav>

        <div className="guide-main">
          <VoiceGuide stepId={step.id} />
          <StepCard step={step} />
          <label className={`step-done${isDone ? " checked" : ""}`}>
            <input
              type="checkbox"
              checked={isDone}
              onChange={(e) => setDone(markStepDone(step.id, e.target.checked))}
            />{" "}
            {t("I have done this step")}
          </label>
          {!isDone && (
            <p className="muted small">
              {t("Do the step on the screen, tick the box, then press Next.")}
            </p>
          )}
          <div className="guide-nav">
            <button
              type="button"
              className="btn"
              disabled={!prev}
              onClick={() => prev && navigate(`/guide/${prev.id}`)}
            >
              {t("← Back")}
            </button>
            {next ? (
              <button
                type="button"
                className="btn btn-primary"
                disabled={!isDone}
                onClick={() => navigate(`/guide/${next.id}`)}
              >
                {t("Next:")} {titleOf(next)} →
              </button>
            ) : (
              <button type="button" className="btn btn-primary" disabled={!isDone} onClick={finish}>
                {t("Finish the tour")}
              </button>
            )}
          </div>
          {finished && finished.length > 0 && (
            <div className="tour-finish" role="status">
              <p>
                <strong>Almost there.</strong> Open every step once to finish the tour. Not seen
                yet:
              </p>
              <ul>
                {STEPS.filter((s) => finished.includes(s.id)).map((s) => (
                  <li key={s.id}>
                    <Link to={`/guide/${s.id}`}>{titleOf(s)}</Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {finished && finished.length === 0 && (
            <div className="tour-finish" role="status">
              <h2>{t("You have finished the guided tour")}</h2>
              <p>
                Continue with your own account? Your own factory starts with the same data as the
                tour, and you can take the tour again at any time from the top bar.
              </p>
              <p className="actions-row">
                <Link to="/sign-up" className="btn btn-primary">
                  {t("Create your own factory")}
                </Link>
                <Link to="/sign-in" className="btn">
                  {t("Sign in to my account")}
                </Link>
                <Link to="/how-to#own-factory" className="btn">
                  {t("Instructions (step by step)")}
                </Link>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    restartTour();
                    setDone([]);
                    setFinished(null);
                    navigate(`/guide/${STEPS[0]!.id}`);
                  }}
                >
                  {t("Restart the tour")}
                </button>
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
