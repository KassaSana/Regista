import { InsightBody, InsightKind } from "./InsightPanel";
import type { Card, Score } from "./replayTypes";

/**
 * Every insight surfaced so far, in match order. At a break it opens with a
 * short summary. It never lists a card later than the replay position, so it
 * cannot spoil the rest of the match.
 */
export function History({
  cards,
  hiddenExperimental,
  breakTitle,
  score,
  teamName,
  homeName,
  awayName,
  onContinue,
}: {
  cards: Card[];
  hiddenExperimental: number;
  breakTitle: string | null;
  score: Score;
  teamName: (teamId: number) => string;
  homeName: string;
  awayName: string;
  onContinue: (() => void) | null;
}) {
  const noticed =
    cards.length === 0
      ? "Nothing stood out so far. Regista stays quiet when nothing matters."
      : `Regista noticed ${cards.length} ${cards.length === 1 ? "thing" : "things"} so far.`;
  return (
    <section className="history" aria-label="Insight history">
      {breakTitle !== null && (
        <div className="break-summary">
          <h2 className="break-title">{breakTitle}</h2>
          <p className="break-score">
            {homeName} {score.home}–{score.away} {awayName}
          </p>
          {onContinue !== null && (
            <button type="button" className="play" onClick={onContinue}>
              Continue
            </button>
          )}
        </div>
      )}
      <p className="muted">{noticed}</p>
      {hiddenExperimental > 0 && (
        <p className="muted small">
          {hiddenExperimental} experimental{" "}
          {hiddenExperimental === 1 ? "insight is" : "insights are"} hidden. Turn on "Show
          experimental insights" to include them.
        </p>
      )}
      <ol className="history-list">
        {cards.map((card) => (
          <li key={card.id} className="history-item">
            <header className="insight-header">
              <InsightKind card={card} />
            </header>
            <InsightBody card={card} teamName={teamName} homeName={homeName} awayName={awayName} />
          </li>
        ))}
      </ol>
    </section>
  );
}
