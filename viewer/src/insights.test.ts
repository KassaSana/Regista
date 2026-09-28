import { describe, expect, it } from "vitest";
import { syntheticExport } from "./fixtures/syntheticExport";
import { bulbOf, shownCards } from "./insights";
import { positionOf, timelineOf, visibleAt } from "./replay";

const timeline = timelineOf(syntheticExport.periods);
const shownAt = (position: number, showExperimental: boolean) =>
  shownCards(visibleAt(syntheticExport, timeline, position).cards, showExperimental);
const positionOfCard = (index: number): number => {
  const card = syntheticExport.cards[index];
  if (card === undefined) {
    throw new Error(`fixture has no card ${index}`);
  }
  return positionOf(card.clock, timeline);
};
const NONE = new Set<string>();

describe("bulb", () => {
  it.each(syntheticExport.cards.map((card, index) => ({ id: card.id, index })))(
    "does not light for $id before its clock, and lights at it",
    ({ id, index }) => {
      const position = positionOfCard(index);
      const before = bulbOf(shownAt(position - 1, true), NONE);
      const at = bulbOf(shownAt(position, true), NONE);

      expect(shownAt(position - 1, true).map((card) => card.id)).not.toContain(id);
      expect(at.state).toBe("new");
      expect(at.opens?.id).toBe(id);
      expect(at.newCount).toBe(before.newCount + 1);
    },
  );

  it("is off at kickoff", () => {
    expect(bulbOf(shownAt(0, true), NONE)).toEqual({ state: "off", newCount: 0, opens: null });
  });

  it("never lights for an experimental card while the toggle is off", () => {
    const end = timeline.total;
    const shown = shownAt(end, false);

    expect(shown.map((card) => card.kind)).toEqual(["side_shift"]);
    expect(bulbOf(shown, NONE).newCount).toBe(1);
    expect(bulbOf(shown, NONE).opens?.experimental).toBe(false);
    expect(shownAt(end, true).map((card) => card.kind)).toEqual(["side_shift", "burst"]);
  });

  it("turns seen once read, and new again when a later card surfaces", () => {
    const firstId = syntheticExport.cards[0]?.id ?? "";
    const read = new Set([firstId]);

    const afterFirst = bulbOf(shownAt(positionOfCard(0), true), read);
    expect(afterFirst.state).toBe("seen");
    expect(afterFirst.opens?.id).toBe(firstId);

    const afterSecond = bulbOf(shownAt(positionOfCard(1), true), read);
    expect(afterSecond.state).toBe("new");
    expect(afterSecond.newCount).toBe(1);
  });

  it("hides a card again when scrubbing back before it, while it stays read", () => {
    const firstId = syntheticExport.cards[0]?.id ?? "";
    const read = new Set([firstId]);

    expect(bulbOf(shownAt(positionOfCard(0) - 1, true), read).state).toBe("off");
    expect(bulbOf(shownAt(positionOfCard(0), true), read).state).toBe("seen");
  });

  it("carries each card's own score, never a later one", () => {
    const shown = shownAt(timeline.total, true);

    expect(shown.map((card) => card.score)).toEqual([
      { home: 1, away: 0 },
      { home: 2, away: 1 },
    ]);
    expect(visibleAt(syntheticExport, timeline, timeline.total).score).toEqual({
      home: 2,
      away: 1,
    });
  });
});
