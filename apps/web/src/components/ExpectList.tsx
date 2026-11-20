import type { Expectation } from "../guide/types";
import { formatValue, lookup } from "../lib/format";
import { useGuideData } from "../lib/guideStore";
import { StatusChip } from "./StatusChip";

/** "What you should see": each value is read from the oracle, never typed into the UI. */
export function ExpectList({ items }: { items: Expectation[] }) {
  const { oracle } = useGuideData();
  const payload = oracle.state === "ok" ? oracle.data : undefined;
  return (
    <dl className="expect">
      {items.map((item) => (
        <div className="expect-row" key={item.label}>
          <dt>{item.label}</dt>
          <dd>
            {"text" in item ? (
              <span className="expect-text">{item.text}</span>
            ) : (
              <>
                <span className="num" data-oracle-key={item.key}>
                  {payload ? formatValue(lookup(payload, item.key), item.unit) : "…"}
                </span>
                {item.flagged ? <StatusChip tone="warn">Flagged</StatusChip> : null}
              </>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}
