import { Attribution } from "./Attribution";
import { KIND_LABELS } from "./insights";
import { Pitch } from "./Pitch";
import { formatClock, periodLabel } from "./replay";
import type { Card } from "./replayTypes";

/** One insight at a time, inline so play continues behind it. */
export function InsightPanel({
  cards,
  index,
  teamName,
  homeName,
  awayName,
  onStep,
  onClose,
}: {
  cards: Card[];
  index: number;
  teamName: (teamId: number) => string;
  homeName: string;
  awayName: string;
  onStep: (index: number) => void;
  onClose: () => void;
}) {
  const card = cards[index];
  if (card === undefined) {
    return null;
  }
  return (
    <article className="insight" aria-label="Insight">
      <header className="insight-header">
        <span className="insight-kind">{KIND_LABELS[card.kind]}</span>
        {card.experimental && <span className="badge">Experimental</span>}
        <button type="button" className="close" aria-label="Close insight" onClick={onClose}>
          ×
        </button>
      </header>
      <p className="insight-meta">
        {periodLabel(card.clock.period)} · {formatClock(card.clock)} · {teamName(card.team_id)} ·{" "}
        {homeName} {card.score.home}–{card.score.away} {awayName}
      </p>
      <p className="insight-sentence">{card.sentence}</p>
      <details className="why">
        <summary>Why this insight?</summary>
        <Pitch card={card} />
        <ul className="evidence-lines">
          {card.evidence_lines.map((line, lineIndex) => (
            // Evidence lines are fixed text in export order; the order is the identity.
            // biome-ignore lint/suspicious/noArrayIndexKey: static list, never reordered
            <li key={lineIndex}>{line}</li>
          ))}
        </ul>
        <p className="muted sources">Source: {card.sources.join(", ")}</p>
      </details>
      <nav className="insight-steps" aria-label="Insights so far">
        <button type="button" disabled={index === 0} onClick={() => onStep(index - 1)}>
          ‹ Earlier
        </button>
        <span className="muted">
          {index + 1} of {cards.length}
        </span>
        <button
          type="button"
          disabled={index === cards.length - 1}
          onClick={() => onStep(index + 1)}
        >
          Later ›
        </button>
      </nav>
      <Attribution />
    </article>
  );
}
