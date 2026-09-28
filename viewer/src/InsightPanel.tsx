import { Attribution } from "./Attribution";
import { KIND_LABELS } from "./insights";
import { Pitch } from "./Pitch";
import { formatClock, periodLabel } from "./replay";
import type { Card } from "./replayTypes";

interface Names {
  teamName: (teamId: number) => string;
  homeName: string;
  awayName: string;
}

export function InsightKind({ card }: { card: Card }) {
  return (
    <>
      <span className="insight-kind">{KIND_LABELS[card.kind]}</span>
      {card.experimental && <span className="badge">Experimental</span>}
    </>
  );
}

/** The insight itself: when, the score then, the sentence, and why it fired. */
export function InsightBody({ card, teamName, homeName, awayName }: { card: Card } & Names) {
  return (
    <>
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
            // biome-ignore lint/suspicious/noArrayIndexKey: fixed text in export order, never reordered
            <li key={lineIndex}>{line}</li>
          ))}
        </ul>
        <p className="muted sources">Source: {card.sources.join(", ")}</p>
      </details>
    </>
  );
}

/** One insight at a time, inline so play continues behind it. */
export function InsightPanel({
  cards,
  index,
  onStep,
  onClose,
  ...names
}: {
  cards: Card[];
  index: number;
  onStep: (index: number) => void;
  onClose: () => void;
} & Names) {
  const card = cards[index];
  if (card === undefined) {
    return null;
  }
  return (
    <article className="insight" aria-label="Insight">
      <header className="insight-header">
        <InsightKind card={card} />
        <button type="button" className="close" aria-label="Close insight" onClick={onClose}>
          ×
        </button>
      </header>
      <InsightBody card={card} {...names} />
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
