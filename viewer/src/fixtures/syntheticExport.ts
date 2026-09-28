/**
 * A hand-built export for tests. No provider data is copied: the teams, events,
 * and sentences are invented. Typed with the generated schema types, so a schema
 * change breaks this fixture at compile time.
 *
 * The first half runs to 47:00 and the second restarts at 45:00, with a goal in
 * each overlap (46:30 in the first half, 45:30 in the second): sorting by the raw
 * minute would put them in the wrong order.
 */

import type { Card, Clock, RegistaReplayExport } from "../replayTypes";

const clock = (period: number, minute: number, second = 0): Clock => ({ period, minute, second });

// Side-shift evidence is entries (arrows into the final third); burst evidence is shots (dots).
const evidenceFor = (id: string, kind: Card["kind"], at: Clock): Card["evidence"] =>
  kind === "side_shift"
    ? [10, 14, 20].map((y, index) => ({
        event_id: `${id}-entry-${index}`,
        role: "recent" as const,
        clock: at,
        team_id: 1,
        action: "pass",
        start: { x: 70, y },
        end: { x: 88, y: y - 2 },
      }))
    : [36, 44].map((y, index) => ({
        event_id: `${id}-shot-${index}`,
        role: "shot" as const,
        clock: at,
        team_id: 1,
        action: "shot",
        start: { x: 106, y },
        end: null,
      }));

const card = (id: string, kind: Card["kind"], at: Clock, home: number, away: number): Card => ({
  id,
  kind,
  experimental: kind === "burst",
  team_id: 1,
  clock: at,
  trigger_event_id: `${id}-trigger`,
  score: { home, away },
  sentence: `Synthetic ${kind} card.`,
  evidence_lines: ["synthetic evidence line"],
  evidence: evidenceFor(id, kind, at),
  sources: ["Synthetic"],
});

export const syntheticExport: RegistaReplayExport = {
  schema_version: 1,
  attribution: "Data: StatsBomb",
  match: {
    id: 1,
    competition: "Synthetic League",
    season: "2026",
    date: "2026-09-28",
    home: { id: 1, name: "Home" },
    away: { id: 2, name: "Away" },
  },
  periods: [
    { period: 1, start: clock(1, 0), end: clock(1, 47) },
    { period: 2, start: clock(2, 45), end: clock(2, 93) },
  ],
  goals: [
    {
      event_id: "goal-1",
      clock: clock(1, 12),
      team_id: 1,
      own_goal: false,
      penalty: false,
      score: { home: 1, away: 0 },
    },
    {
      event_id: "goal-2",
      clock: clock(1, 46, 30),
      team_id: 1,
      own_goal: false,
      penalty: true,
      score: { home: 2, away: 0 },
    },
    {
      event_id: "goal-3",
      clock: clock(2, 45, 30),
      team_id: 2,
      own_goal: true,
      penalty: false,
      score: { home: 2, away: 1 },
    },
  ],
  cards: [
    card("side_shift-a", "side_shift", clock(1, 24, 14), 1, 0),
    card("burst-b", "burst", clock(2, 80), 2, 1),
  ],
  facts: [
    {
      clock: clock(1, 0),
      kind: "lineup",
      team_id: 1,
      sentence: "Home started in a recorded 4-3-3 shape.",
      event_id: "fact-1",
    },
    {
      clock: clock(2, 60),
      kind: "substitution",
      team_id: 2,
      sentence: "Player B replaced Player A for Away.",
      event_id: "fact-2",
    },
  ],
};
