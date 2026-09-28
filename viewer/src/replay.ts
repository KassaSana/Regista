/**
 * Replay logic for the viewer: where the replay is, what the clock reads, and
 * what has happened so far. Pure functions only, so they are easy to test.
 *
 * The provider minute runs on across periods: the second half starts at 45:00
 * even when the first half ran to 47:00. The viewer therefore moves along a
 * replay position in seconds, with the recorded periods laid end to end.
 *
 * The viewer never decides anything. It only reveals what the export already
 * holds, and nothing appears before its own clock (the viewer's mirror of the
 * prefix rule).
 */

import type { Card, Clock, RegistaReplayExport, Score } from "./replayTypes";

export type Goal = RegistaReplayExport["goals"][number];
export type Fact = RegistaReplayExport["facts"][number];
type Period = RegistaReplayExport["periods"][number];

export interface Segment {
  period: number;
  /** Provider seconds (minute * 60 + second) at the recorded start and end. */
  startSeconds: number;
  endSeconds: number;
  /** Where this period starts on the replay position. */
  offset: number;
  length: number;
}

export interface Timeline {
  segments: Segment[];
  total: number;
}

export interface Visible {
  clock: Clock;
  score: Score;
  goals: Goal[];
  cards: Card[];
  facts: Fact[];
}

const secondsOf = (clock: Clock): number => clock.minute * 60 + clock.second;

export function timelineOf(periods: Period[]): Timeline {
  const segments: Segment[] = [];
  let offset = 0;
  for (const period of [...periods].sort((a, b) => a.period - b.period)) {
    const startSeconds = secondsOf(period.start);
    const endSeconds = Math.max(startSeconds, secondsOf(period.end));
    const length = endSeconds - startSeconds;
    segments.push({ period: period.period, startSeconds, endSeconds, offset, length });
    offset += length;
  }
  return { segments, total: offset };
}

/** The replay position of a clock, clamped to its period (or to the timeline). */
export function positionOf(clock: Clock, timeline: Timeline): number {
  const segment = timeline.segments.find((candidate) => candidate.period === clock.period);
  if (segment === undefined) {
    const first = timeline.segments[0];
    return first !== undefined && clock.period < first.period ? 0 : timeline.total;
  }
  const into = secondsOf(clock) - segment.startSeconds;
  return segment.offset + Math.min(Math.max(into, 0), segment.length);
}

/** The clock at a replay position. A period's last second belongs to that period. */
export function clockAt(position: number, timeline: Timeline): Clock {
  const clamped = Math.min(Math.max(position, 0), timeline.total);
  const segment =
    timeline.segments.find((candidate) => clamped <= candidate.offset + candidate.length) ??
    timeline.segments.at(-1);
  if (segment === undefined) {
    return { period: 1, minute: 0, second: 0 };
  }
  const seconds = segment.startSeconds + Math.floor(clamped - segment.offset);
  return { period: segment.period, minute: Math.floor(seconds / 60), second: seconds % 60 };
}

/** Everything the viewer may show at a replay position, in replay order. */
export function visibleAt(
  exported: RegistaReplayExport,
  timeline: Timeline,
  position: number,
): Visible {
  const reached = <T extends { clock: Clock }>(items: T[]): T[] =>
    items.filter((item) => positionOf(item.clock, timeline) <= position);
  const goals = reached(exported.goals);
  return {
    clock: clockAt(position, timeline),
    score: goals.at(-1)?.score ?? { home: 0, away: 0 },
    goals,
    cards: reached(exported.cards),
    facts: reached(exported.facts),
  };
}

const PERIOD_LABELS: Record<number, string> = {
  1: "1st half",
  2: "2nd half",
  3: "Extra time, 1st half",
  4: "Extra time, 2nd half",
  5: "Penalties",
};

export function periodLabel(period: number): string {
  return PERIOD_LABELS[period] ?? `Period ${period}`;
}

/** A match clock such as "63:05" (minutes can pass 99). */
export function formatClock(clock: Clock): string {
  return `${String(clock.minute).padStart(2, "0")}:${String(clock.second).padStart(2, "0")}`;
}

/**
 * The first period whose end lies in (from, to]: playback crossing it pauses
 * there for a break (half time, the end of extra-time halves, full time).
 */
export function breakBetween(from: number, to: number, timeline: Timeline): Segment | undefined {
  return timeline.segments.find((segment) => {
    const end = segment.offset + segment.length;
    return from < end && end <= to;
  });
}

/** Whether a replay position sits exactly at the end of a period. */
export function isBreak(position: number, timeline: Timeline): boolean {
  return timeline.segments.some((segment) => segment.offset + segment.length === position);
}

export function breakLabel(segment: Segment, timeline: Timeline): string {
  if (segment === timeline.segments.at(-1)) {
    return "Full time";
  }
  return segment.period === 1 ? "Half time" : `End of ${periodLabel(segment.period).toLowerCase()}`;
}
