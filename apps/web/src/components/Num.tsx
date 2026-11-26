import { useEffect, useId, useRef, useState } from "react";
import { formatAmount } from "../lib/amount";
import { sourceLabel, type Explained } from "../lib/explained";

/**
 * A number from the API with its "Explain this number" popover: the formula, the method and every input with the
 * document it came from. Keyboard: the ⓘ button toggles it, Escape closes it and returns focus.
 */
export function Num({
  value,
  label,
  className,
}: {
  value: Explained;
  label: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const popId = useId();
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <span className={`numx ${className ?? ""}`}>
      <span className="num">{formatAmount(value.value, value.unit)}</span>
      <button
        ref={button}
        type="button"
        className="info-btn"
        aria-expanded={open}
        aria-controls={popId}
        aria-label={`Explain this number: ${label}`}
        onClick={() => setOpen((o) => !o)}
      >
        ⓘ
      </button>
      {open && (
        <span
          id={popId}
          role="dialog"
          aria-label={`How ${label} is worked out`}
          className="explain-pop"
        >
          <span className="explain-title">{label}</span>
          <span className="explain-formula">
            <span className="meta-label">Formula</span> {value.formula}
          </span>
          {value.method && (
            <span className="explain-method">
              <span className="meta-label">Method</span> {value.method}
            </span>
          )}
          {value.inputs.length > 0 && (
            <span className="explain-inputs" role="list">
              {value.inputs.map((i, n) => (
                <span role="listitem" key={`${i.label}-${n}`} className="explain-input">
                  <span>{i.label}</span>
                  <strong className="num">{formatAmount(i.value, i.unit)}</strong>
                  {i.source && (
                    <span className="muted small" title={i.source.id}>
                      from the {sourceLabel(i.source.type).toLowerCase()}
                    </span>
                  )}
                </span>
              ))}
            </span>
          )}
          <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
            Close
          </button>
        </span>
      )}
    </span>
  );
}
