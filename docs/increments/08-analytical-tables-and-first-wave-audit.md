# Increment 8: Analytical tables and the first-wave audit

Last updated: 2026-09-27

## Scope
Build the analytical layer the fan questions need, run data-quality reporting over every ingested match, prove the warehouse rebuilds deterministically, and record an inventory of the first development corpus. Validation and test matches were never opened. This is the check-in point for [increments 7](07-validation-and-normalized-warehouse.md) and 8.

## Exit evidence

| Claim | Evidence |
|---|---|
| Every ingested match validated | 270 of 270 passed adapter validation and all 7 blocking checks; 0 exclusions (`out/dq/latest.md`) |
| Deterministic rebuild | An independent rebuild into a scratch file matched `data/warehouse/regista.duckdb` in all 32 tables (`regista data fingerprint --compare`: "Identical.") |
| Analytical definitions agree with the domain | SQL `final_third_entries` equals `is_final_third_entry` + `channel_of` on a synthetic boundary match and on real match 3773497 (126 entries) |
| Quality checks work | Each of the 11 SQL checks has a firing test and passes on the reference match; checksum and adapter failures are recorded and excluded while other matches still load |
| Isolation | The research connection is read-only and cannot read outside files; the warehouse contains development matches and development raw files only (contract tests) |
| Repository checks | 220 tests passed (205 synthetic and unit, 15 contract); Ruff lint and format passed; strict Pyright reported 0 errors |

The first determinism run caught real nondeterminism: floating-point xG sums varied in their last bits with DuckDB's parallel aggregation. `event_context.provider_xg` is now an exact `DECIMAL(18, 12)` (every provider value has at most 10 decimals and round-trips exactly), so all downstream sums are order-independent. `normalized.shots.provider_xg` keeps the provider's double.

## Analytical tables (`analytical` schema)
Built in SQL (`src/regista/warehouse/analytical.sql`) from `normalized`, over matches with no blocking failure. Every table has `definition_version` (all 1) and `ingest_run_id`. Definitions are also queryable in `analytical.definitions`.

Conventions:
- Time is `(period, period_seconds)`; 5-minute `time_bin`s restart each period, and the last bin of a period is shorter (`bin_seconds`).
- Space is 120 × 80, and the acting team always attacks toward increasing x.
- Thirds split at x = 40 and 80; channels at y = 80/3 and 160/3; the zone grid is 6 × 5 cells of 20 × 16.
- Box means x ≥ 102 and 18 ≤ y ≤ 62.
- xG is always the provider's model (`provider_xg`).

| Table | Rows | Grain and key columns | Example research questions |
|---|---:|---|---|
| `team_matches` | 540 | Team × match: opponent, home or away, final goals (hindsight), `lineup_consistent` | Which teams and matches are available? Home and away splits |
| `periods` | 546 | Match × period: `end_seconds`, `is_shootout` | How long is stoppage time? |
| `event_context` | 931,293 | Event: `time_bin`, thirds, channel, zones, `in_box`, end location equivalents, `open_play`, `set_piece_type`, `completed`, `provider_xg`, `scores_goal`, `under_pressure`, score before the event (`goals_for_before`, `score_state`), `clock_out_of_order` | Where do teams lose the ball when leading? Spatial heat maps by score state; open play versus set pieces |
| `score_states` | 931,293 | Event: home and away score before it | Game state at any moment |
| `final_third_entries` | 25,451 | Locked AGENTS.md definition, with channel | How are entry channels distributed per 15 minutes? What does a normal left share look like? |
| `box_entries` | 7,070 | **Provisional v1**: open-play completed pass or carry from outside to inside the box | Is pressure dangerous or just possession (entries against box entries against shots)? |
| `team_time_bins` | 11,006 | Team × period × 5-minute bin, including empty bins: passes, completed, open-play and set-piece passes, carries, entries by channel, box entries, tilt passes (own and opponent), `field_tilt`, shots, open-play shots, xG, goals, pressures, recoveries | What changed in the last 10–15 minutes? Who took control without scoring? |
| `player_intervals` | 7,563 | Player × on-pitch interval (union of spells, cut at the Substitution event) | Who was on when? |
| `player_period_spans` | 13,583 | Interval × period, for joins by clock | Which players were on for an event or bin? |
| `player_match_involvement` | 9,756 | Player × match: minutes, located events, passes, `pass_share` of team passes while on, carries, entries, box entries, shots, xG, goals, pressures | Which players carry involvement, and how variable is it? |
| `player_time_bins` | 122,394 | Player × bin while on: seconds on, own passes, team passes, `pass_share` | Which player suddenly became much more involved? |
| `possessions` | 51,016 | Provider possession (**hindsight**, research only): duration, passes, furthest x, reached final third, shots, xG, starting score state | Retrospective: how often does territory become threat? |
| `team_match_summary` | 540 | Whole-match totals and field tilt, for exploration and data quality only, **never a baseline** | Corpus distributions; sanity checks |

Rolling windows are sums over consecutive bins. For example, 15-minute rolling open-play entries and field tilt:

```sql
SELECT match_id, team_id, period, time_bin,
       sum(final_third_entries) OVER w AS entries_15,
       sum(tilt_passes) OVER w / nullif(sum(tilt_passes + opponent_tilt_passes) OVER w, 0) AS tilt_15
FROM analytical.team_time_bins
WINDOW w AS (PARTITION BY match_id, team_id, period ORDER BY time_bin
             ROWS BETWEEN 2 PRECEDING AND CURRENT ROW);
```

Overlapping windows are not independent observations. `team_window_distributions` (the only allowed source for "unusual for this team") is deferred until a metric and window length are chosen in a research note.

## Inventory

### Matches represented

| Competition-season | Ingested | Split sizes (dev/val/test) |
|---|---:|---|
| Premier League 2015/16 | 266 (all development; 8 Aug 2015 – 27 Feb 2016) | 266 / 57 / 57 |
| La Liga 2015/16 | 1 (inspected: 265958) | 277 / 54 / 49 |
| La Liga 2020/21 | 1 (inspected: 3773497) | 25 / 5 / 5 |
| FIFA World Cup 2022 | 2 (inspected: 3869420, 3869321) | 46 / 10 / 8 |

Premier League development covers the first ~70% of the season chronologically. Season-long questions (for example, late-season form) cannot be answered from development data alone.

27 teams, 755 distinct players (760 name rows; a few players appear under more than one name or nickname, so use `min(player_name)` per `player_id`). 3 matches have 360 frames available (not downloaded).

### Normalized tables

| Table | Rows | Notes |
|---|---:|---|
| `matches` | 270 | 163 passed, 107 passed with warnings, 0 excluded |
| `events` | 931,293 | 17 Regista types; `other` 264,802 (mostly Ball Receipt), pass 263,594, carry 197,443, pressure 79,374 |
| `passes` | 263,594 | 76.7% completed; 89.5% open play |
| `carries` | 197,443 | Key only; locations in `events` |
| `shots` | 6,994 | Open Play 6,629, Free Kick 282, Penalty 82, Corner 1; provider xG total 701.3 |
| `goals` | 723 | 681 shot goals and 29 own goals in play; 13 shootout goals (period 5) |
| `substitutions` | 1,504 | Tactical 1,416, Injury 88 |
| `formation_changes` | 962 | 540 starting, 422 tactical shifts |
| `appearances` / `position_spells` | 9,756 / 9,012 | 7,444 appearances with time on the pitch |
| `raw_files` | 554 | 540 match files plus 14 indexes |
| `splits` | 1,894 | Identifiers and buckets from `splits/v1.json` |
| `dq_checks` | 3,510 | 13 checks × 270 matches |
| `field_availability` | 43 | Availability tag per column |

### Missingness (important columns)

| Column | Missing | Why |
|---|---:|---|
| `events.player_id` | 0.36% | Period, formation, and team-level events |
| `events.x` | 0.63% | Events without a location (period start and end, substitutions, formation changes) |
| `events.end_x` for passes and carries | 0% | |
| `passes.recipient_player_id` | 8.35% | Mostly incomplete passes |
| `passes.outcome` | 76.7% empty = completed | 1,423 are "Unknown", which Regista counts as not completed (locked definition) |
| `shots.provider_xg` | 0% | |
| `shots.key_pass_event_id` | 1,935 of 6,994 | Shots not directly assisted |
| `shots.end_z` | 2,309 of 6,994 | Provider gives height only for some shots |
| `possession` | 0% | Hindsight field |
| Match metadata (`data_version` and fidelity versions) | 0 matches | |

### Data-quality results

| Check | Severity | Failed matches |
|---|---|---:|
| raw_checksum, adapter_validation, teams_present, event_count_plausible, sequence_contiguous, score_reconciles, substitutes_in_lineup | blocking | 0 |
| clock_monotonic | warning | 100 |
| substitution_ends_lineup_spell | warning | 8 |
| position_spells_consistent | warning | 5 |
| coordinates_on_pitch | warning | 1 (3754162: a direct goal from a corner recorded at x = 120.2) |
| event_players_in_lineup, provider_metadata_present | warning | 0 |

Exclusions: none. Important findings, detailed in [research note 04](../research/04-provider-clock-and-lineup-anomalies.md):
- In 94 matches, the last first-half Ball Receipt is stamped 00:00, with `minute` 0. These events are flagged by `clock_out_of_order`, and the note assesses their Phase 1 detector impact.
- Lineup spells sometimes overlap or ignore a substitution. Intervals take the union and cut at the Substitution event; 16 of 540 team-matches have `lineup_consistent = false`, and the two inspected World Cup lineups are the least reliable.

### First corpus facts (development, Premier League team-matches)
Per team-match averages:
- 46.9 open-play final-third entries (range 14–106)
- 13.1 box entries
- 12.9 shots
- 1.27 provider xG

Entry channels: left 10,169; right 9,929; center 5,353. Field tilt is undefined (no tilt passes by either team) in 480 of 11,006 bins; the median bin has 6 combined tilt passes, so any field-tilt minimum must be set with that sparsity in mind. Events split by score state: level 52.3%, trailing 25.1%, leading 22.6% (event-weighted, not time-weighted). These are descriptions, not findings about fans.

## Owner decisions needed
- **Box-entry definition.** Provisional v1 (penalty area x ≥ 102, 18 ≤ y ≤ 62, open-play completed pass or carry from outside to inside). Accept, change, or add to AGENTS.md "Locked definitions".
- **Field-tilt minimum.** Still unset; the bins above show how sparse tilt passes are per 5 minutes.
- **DuckDB server.** The DuckDB server configured for agents opens the development warehouse read-only, but its configuration lives outside the repository (`~/.claude.json`). Switching off external file access there (the Phase 2 specification requirement) is the owner's change. `regista.warehouse.research.connect_research` already does it for code.

## Remaining work
- The held-out warehouse and mechanical validation of held-out matches (only when evaluation needs them).
- `team_window_distributions`, after a research note chooses a metric and window.
- Ingestion waves 2 and 3, only when a named question needs them.
- Probe 01 viewing judgments (owner).
- A detector response to the clock anomaly (research note 04, owner review).
