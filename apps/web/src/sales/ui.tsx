import { useRef } from "react";
import { NavLink } from "react-router-dom";
import { StatusChip } from "../components/StatusChip";
import { useOutbox } from "./outboxContext";
import { PHONE_STATUS, SERVER_STATUS, savedAtText } from "./status";
import type { OutboxState } from "./types";

export function PhoneStatus({ state }: { state: OutboxState }) {
  const [tone, word] = PHONE_STATUS[state];
  return <StatusChip tone={tone}>{word}</StatusChip>;
}

export function ServerStatus({ status }: { status: string }) {
  const [tone, word] = SERVER_STATUS[status] ?? ["info", status];
  return <StatusChip tone={tone}>{word}</StatusChip>;
}

export function StaleChip() {
  return <StatusChip tone="warn">Price changed: admin will confirm</StatusChip>;
}

/** Today · My orders · Summary (bottom tabs at phone width), plus the connection banner. */
export function SalesTabs() {
  const outbox = useOutbox();
  const waiting = outbox.entries.filter((e) => e.state === "saved" || e.state === "sending").length;
  const attention = outbox.entries.filter((e) => e.state === "attention").length;
  return (
    <>
      {!outbox.online && (
        <p className="banner banner-offline" role="status">
          <span aria-hidden="true">⚡</span> No connection. You can still take orders: they are
          saved on this phone and send themselves when the network is back.
        </p>
      )}
      {outbox.paused && (
        <p className="banner banner-warn" role="status">
          <span aria-hidden="true">⚑</span> Your sign-in expired. {waiting} saved order
          {waiting === 1 ? "" : "s"} will send after you sign in again.
        </p>
      )}
      <nav className="sales-tabs" aria-label="Salesman">
        <NavLink to="/sales" end>
          <span aria-hidden="true">☀</span> Today
        </NavLink>
        <NavLink to="/sales/orders">
          <span aria-hidden="true">☰</span> My orders
          {waiting + attention > 0 && (
            <span className="tab-count" aria-label={`${waiting + attention} not yet received`}>
              {waiting + attention}
            </span>
          )}
        </NavLink>
        <NavLink to="/sales/summary">
          <span aria-hidden="true">Σ</span> Summary
        </NavLink>
      </nav>
    </>
  );
}

/** A generated DEMO illustration of a snack pouch (no photos, G7). Colour and size follow the product code. */
export function ProductArt({ code, name }: { code: string; name: string }) {
  let hash = 0;
  for (const ch of code) hash = (hash * 31 + ch.charCodeAt(0)) % 360;
  const grams = /(\d+)\s*g/i.exec(code)?.[1] ?? "";
  const tall = Number(grams) >= 500;
  return (
    <svg
      className="product-art"
      viewBox="0 0 64 64"
      role="img"
      aria-label={`DEMO illustration of ${name}`}
    >
      <rect width="64" height="64" rx="12" fill={`hsl(${hash} 70% 92%)`} />
      <path
        d={tall ? "M18 8h28l4 6v42H14V14z" : "M18 16h28l4 6v34H14V22z"}
        fill={`hsl(${hash} 65% 45%)`}
      />
      <rect x="20" y={tall ? 24 : 30} width="24" height="14" rx="3" fill="#fff" opacity="0.92" />
      <text x="32" y={tall ? 34 : 40} textAnchor="middle" fontSize="8" fontWeight="700" fill="#333">
        {grams ? `${grams}g` : "DEMO"}
      </text>
      <circle cx="26" cy={tall ? 47 : 50} r="3" fill="#f6d28b" />
      <circle cx="34" cy={tall ? 49 : 51} r="3" fill="#f6d28b" />
      <circle cx="40" cy={tall ? 46 : 49} r="2.5" fill="#f6d28b" />
    </svg>
  );
}

/** Whole packets only (G2). Tap + adds a packet; holding + (or the carton button) adds a full carton. */
export function Stepper({
  value,
  onChange,
  perCarton,
  label,
}: {
  value: number;
  onChange: (n: number) => void;
  perCarton: number | null;
  label: string;
}) {
  const held = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressed = useRef(false);
  const set = (n: number) => onChange(Math.max(0, Math.min(999_999, Math.trunc(n))));

  return (
    <div className="stepper" role="group" aria-label={`${label}: packets`}>
      <button
        type="button"
        className="step-btn"
        aria-label={`One packet less of ${label}`}
        onClick={() => set(value - 1)}
        disabled={value <= 0}
      >
        −
      </button>
      <input
        className="step-input"
        inputMode="numeric"
        pattern="[0-9]*"
        aria-label={`${label}: packets`}
        value={String(value)}
        onChange={(e) => set(Number(e.target.value.replace(/\D/g, "") || "0"))}
      />
      <button
        type="button"
        className="step-btn"
        aria-label={`One packet more of ${label}`}
        onPointerDown={() => {
          longPressed.current = false;
          if (!perCarton) return;
          held.current = setTimeout(() => {
            longPressed.current = true;
            set(value + perCarton);
          }, 500);
        }}
        onPointerUp={() => held.current && clearTimeout(held.current)}
        onPointerLeave={() => held.current && clearTimeout(held.current)}
        onClick={() => {
          if (longPressed.current) {
            longPressed.current = false;
            return;
          }
          set(value + 1);
        }}
      >
        +
      </button>
      {perCarton ? (
        <button
          type="button"
          className="step-carton"
          aria-label={`One carton more of ${label} (${perCarton} packets)`}
          onClick={() => set(value + perCarton)}
        >
          +1 carton
          <span className="small"> ({perCarton})</span>
        </button>
      ) : null}
    </div>
  );
}

export function OfflineCopy({ savedAt }: { savedAt: number | null }) {
  return (
    <p className="banner banner-offline small" role="status">
      Showing the copy saved on this phone at {savedAtText(savedAt)}.
    </p>
  );
}
