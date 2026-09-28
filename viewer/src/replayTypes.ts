/* Generated from schemas/replay.schema.json by npm run types. Do not edit. */

/**
 * One match's replay export, version 1. Thin by design (DATA_SOURCES.md): period boundaries, goals with the running score, cards with only their own evidence events, and recorded facts. Never the full event stream.
 */
export interface RegistaReplayExport {
  schema_version: 1;
  attribution: "Data: StatsBomb";
  match: {
    id: number;
    competition: string;
    season: string;
    date: string;
    home: Team;
    away: Team;
  };
  periods: {
    period: number;
    start: Clock;
    end: Clock;
  }[];
  goals: {
    event_id: string;
    clock: Clock;
    team_id: number;
    own_goal: boolean;
    penalty: boolean;
    score: Score;
  }[];
  cards: Card[];
  facts: {
    clock: Clock;
    kind: "lineup" | "substitution" | "formation_change";
    team_id: number;
    sentence: string;
    event_id: string;
  }[];
}
export interface Team {
  id: number;
  name: string;
}
/**
 * Provider clock: minute runs continuously across periods, so always read it with the period.
 */
export interface Clock {
  period: number;
  minute: number;
  second: number;
}
export interface Score {
  home: number;
  away: number;
}
export interface Card {
  id: string;
  kind: "side_shift" | "burst";
  experimental: boolean;
  team_id: number;
  clock: Clock;
  trigger_event_id: string;
  score: Score;
  sentence: string;
  evidence_lines: string[];
  evidence: Evidence[];
  /**
   * @minItems 1
   */
  sources: [string, ...string[]];
}
export interface Evidence {
  event_id: string;
  role: "recent" | "shot";
  clock: Clock;
  team_id: number;
  action: string;
  start: Point | null;
  end: Point | null;
}
export interface Point {
  x: number;
  y: number;
}
