import { describe, expect, it } from "vitest";
import { syntheticExport } from "./fixtures/syntheticExport";
import { clockAt, formatClock, periodLabel, positionOf, timelineOf, visibleAt } from "./replay";
import type { Clock } from "./replayTypes";

const timeline = timelineOf(syntheticExport.periods);
const at = (period: number, minute: number, second = 0): number =>
  positionOf({ period, minute, second }, timeline);

describe("timeline", () => {
  it("lays the periods end to end", () => {
    // 47 minutes of first half, then 48 minutes from 45:00 to 93:00.
    expect(timeline.total).toBe(47 * 60 + 48 * 60);
    expect(at(1, 0)).toBe(0);
    expect(at(1, 47)).toBe(47 * 60);
    expect(at(2, 45)).toBe(47 * 60);
  });

  it("keeps first-half stoppage time before the second half", () => {
    expect(at(1, 46, 30)).toBeLessThan(at(2, 45, 30));
  });

  it("round-trips every second across the half-time boundary", () => {
    for (let position = 0; position <= timeline.total; position += 1) {
      expect(positionOf(clockAt(position, timeline), timeline)).toBe(position);
    }
  });

  it("gives the period's last second to that period", () => {
    expect(clockAt(47 * 60, timeline)).toEqual({ period: 1, minute: 47, second: 0 });
    expect(clockAt(47 * 60 + 1, timeline)).toEqual({ period: 2, minute: 45, second: 1 });
  });

  it("clamps positions and clocks outside the timeline", () => {
    expect(clockAt(-10, timeline)).toEqual({ period: 1, minute: 0, second: 0 });
    expect(clockAt(timeline.total + 10, timeline)).toEqual({ period: 2, minute: 93, second: 0 });
    expect(at(5, 121)).toBe(timeline.total);
    expect(at(2, 99)).toBe(timeline.total);
  });
});

describe("visibleAt", () => {
  const items: { name: string; clock: Clock }[] = [
    ...syntheticExport.goals.map((goal) => ({ name: goal.event_id, clock: goal.clock })),
    ...syntheticExport.cards.map((card) => ({ name: card.id, clock: card.clock })),
    ...syntheticExport.facts.map((fact) => ({ name: fact.event_id, clock: fact.clock })),
  ];
  const names = (position: number): string[] => {
    const visible = visibleAt(syntheticExport, timeline, position);
    return [
      ...visible.goals.map((goal) => goal.event_id),
      ...visible.cards.map((card) => card.id),
      ...visible.facts.map((fact) => fact.event_id),
    ];
  };

  it.each(items)(
    "never shows $name before its clock, and shows it at its clock",
    ({ name, clock }) => {
      const position = positionOf(clock, timeline);
      if (position > 0) {
        expect(names(position - 1)).not.toContain(name);
      }
      expect(names(position)).toContain(name);
    },
  );

  it("keeps the score as it stood at each moment", () => {
    const score = (position: number) => visibleAt(syntheticExport, timeline, position).score;
    expect(score(0)).toEqual({ home: 0, away: 0 });
    expect(score(at(1, 11, 59))).toEqual({ home: 0, away: 0 });
    expect(score(at(1, 12))).toEqual({ home: 1, away: 0 });
    expect(score(at(1, 47))).toEqual({ home: 2, away: 0 });
    expect(score(at(2, 45, 29))).toEqual({ home: 2, away: 0 });
    expect(score(timeline.total)).toEqual({ home: 2, away: 1 });
  });

  it("reports the clock at the position", () => {
    expect(visibleAt(syntheticExport, timeline, at(2, 63, 5)).clock).toEqual({
      period: 2,
      minute: 63,
      second: 5,
    });
  });
});

describe("labels", () => {
  it("names periods and formats clocks", () => {
    expect(periodLabel(1)).toBe("1st half");
    expect(periodLabel(5)).toBe("Penalties");
    expect(periodLabel(7)).toBe("Period 7");
    expect(formatClock({ period: 2, minute: 93, second: 5 })).toBe("93:05");
    expect(formatClock({ period: 4, minute: 120, second: 0 })).toBe("120:00");
  });
});
