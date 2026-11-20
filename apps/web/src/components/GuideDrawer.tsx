import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { SCREENS } from "../guide/screens";
import { STEPS } from "../guide/steps";
import { recalledStep, rememberStep } from "../guide/memory";
import { StepCard } from "./StepCard";

/** The step that belongs to the current screen, else the last one viewed, else the first. */
function stepForPath(pathname: string): number {
  const onScreen = STEPS.findIndex((s) => {
    const screen = SCREENS[s.screen];
    return screen?.built && screen.route !== "/" && pathname.startsWith(screen.route);
  });
  if (onScreen >= 0) return onScreen;
  const last = STEPS.findIndex((s) => s.id === recalledStep());
  return last >= 0 ? last : 0;
}

/** Floating Guide button + side panel, present on every page except the tour itself. */
export function GuideDrawer() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (pathname.startsWith("/guide")) return null;

  const step = STEPS[index] ?? STEPS[0]!;
  const go = (i: number) => {
    setIndex(i);
    rememberStep(STEPS[i]!.id);
  };

  return (
    <>
      <button
        type="button"
        className="guide-fab"
        aria-expanded={open}
        aria-controls="guide-panel"
        onClick={() => {
          if (!open) setIndex(stepForPath(pathname));
          setOpen(!open);
        }}
      >
        <span aria-hidden="true">?</span> Guide
      </button>

      {open && (
        <div className="drawer-backdrop" onClick={() => setOpen(false)}>
          <div
            id="guide-panel"
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Testing guide"
            tabIndex={-1}
            ref={panelRef}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="drawer-top">
              <strong>
                Step {index + 1} of {STEPS.length}
              </strong>
              <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
                Close ✕
              </button>
            </div>
            <StepCard step={step} compact />
            <div className="drawer-nav">
              <button
                type="button"
                className="btn"
                disabled={index === 0}
                onClick={() => go(index - 1)}
              >
                ← Back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={index === STEPS.length - 1}
                onClick={() => go(index + 1)}
              >
                Next →
              </button>
            </div>
            <Link className="link-strong" to={`/guide/${step.id}`} onClick={() => setOpen(false)}>
              Open the full guided tour
            </Link>
            <nav aria-label="All steps" className="drawer-steps">
              <ol>
                {STEPS.map((s, i) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      className={i === index ? "step-link current" : "step-link"}
                      aria-current={i === index ? "step" : undefined}
                      onClick={() => go(i)}
                    >
                      {s.title}
                    </button>
                  </li>
                ))}
              </ol>
            </nav>
          </div>
        </div>
      )}
    </>
  );
}
