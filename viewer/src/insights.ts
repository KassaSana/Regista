/**
 * What the light bulb shows. Pure functions over cards that are already
 * visible at the replay position, so the bulb inherits the prefix rule from
 * visibleAt: no card can light it before its own clock.
 */

import type { Card } from "./replayTypes";

export type BulbState = "off" | "new" | "seen";

export interface Bulb {
  state: BulbState;
  newCount: number;
  /** The card a click opens: the newest unread one, or the newest when all are read. */
  opens: Card | null;
}

/** The surfaced cards, with experimental card types hidden unless asked for. */
export function shownCards(visibleCards: Card[], showExperimental: boolean): Card[] {
  return visibleCards.filter((card) => showExperimental || !card.experimental);
}

export function bulbOf(shown: Card[], readIds: ReadonlySet<string>): Bulb {
  const unread = shown.filter((card) => !readIds.has(card.id));
  const newest = unread.at(-1) ?? shown.at(-1) ?? null;
  if (shown.length === 0) {
    return { state: "off", newCount: 0, opens: null };
  }
  return { state: unread.length > 0 ? "new" : "seen", newCount: unread.length, opens: newest };
}

export const KIND_LABELS: Record<Card["kind"], string> = {
  side_shift: "Attacking side",
  burst: "Attacking burst",
};
