type Tone = "ok" | "todo" | "warn" | "bad" | "info";

const ICON: Record<Tone, string> = { ok: "✓", todo: "○", warn: "⚑", bad: "✕", info: "ℹ" };

/** Status is always icon + word + colour, never colour alone. */
export function StatusChip({ tone, children }: { tone: Tone; children: string }) {
  return (
    <span className={`chip chip-${tone}`}>
      <span aria-hidden="true">{ICON[tone]}</span> {children}
    </span>
  );
}
