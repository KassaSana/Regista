import type { Bulb as BulbModel } from "./insights";

/** A quiet indicator: off until Regista has something, then a count of new insights. */
export function Bulb({ bulb, onOpen }: { bulb: BulbModel; onOpen: () => void }) {
  const label =
    bulb.state === "off"
      ? "No insight yet"
      : bulb.state === "new"
        ? `${bulb.newCount} new ${bulb.newCount === 1 ? "insight" : "insights"}`
        : "Insights so far";
  return (
    <button
      type="button"
      className={`bulb bulb-${bulb.state}`}
      disabled={bulb.state === "off"}
      aria-label={label}
      title={label}
      onClick={onOpen}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z" />
      </svg>
      {bulb.state === "new" && <span className="bulb-count">{bulb.newCount}</span>}
    </button>
  );
}
