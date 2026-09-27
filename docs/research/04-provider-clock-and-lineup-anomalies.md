# Research note: Provider clock and lineup anomalies in the first development wave

Last updated: 2026-09-27

## Question
Can in-match windows trust the provider's event clock, and can player time on the pitch trust the provider's lineup spells? A fan never sees these directly, but a clock error can silence or mistime a card, and a lineup error can make a player's involvement look higher or lower than it was.

## Definitions
- **Clock regression:** an event whose period-relative timestamp is earlier than the latest timestamp of any event before it (by provider `index`) in the same period. Flag: `analytical.event_context.clock_out_of_order`. Check: `clock_monotonic` (warning).
- **Inconsistent lineup:** a player's position spells overlap or end before they start (`position_spells_consistent`), or a substituted player's lineup spell runs more than 60 seconds past their Substitution event (`substitution_ends_lineup_spell`). Both are warnings. `analytical.team_matches.lineup_consistent` is false when either fails.
- Player on-pitch intervals: `analytical.player_intervals`, definition version 1.

## Data
- Matches: 270 development matches (266 Premier League 2015/16, plus the four already-inspected development matches).
- Split bucket: development only (`splits/v1.json`).
- Source commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`; ingest run `737fb3d365f90ce8`.
- Code: git `449aa78` plus the uncommitted increment 7–8 changes (the run records a source digest).

## Method
Queries against `data/warehouse/regista.duckdb` through `regista.warehouse.research.connect_research`:

```sql
-- Backward steps by event type
WITH steps AS (
  SELECT match_id, period, provider_event_type,
         period_seconds - max(period_seconds) OVER (
           PARTITION BY match_id, period ORDER BY sequence
           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS step
  FROM normalized.events)
SELECT provider_event_type, period, count(*), min(step), max(step)
FROM steps WHERE step < 0 GROUP BY ALL;

-- Players on the pitch per team, as a multiple of match time
WITH team AS (SELECT match_id, team_id, sum(seconds_on_pitch) AS s
              FROM analytical.player_period_spans GROUP BY ALL),
     played AS (SELECT match_id, sum(end_seconds) AS s FROM analytical.periods
                WHERE NOT is_shootout GROUP BY ALL)
SELECT match_id, team_id, team.s / played.s FROM team JOIN played USING (match_id);
```

The contract tests `test_large_clock_regressions_are_only_final_first_half_ball_receipts` and `test_consistent_lineups_never_put_more_than_eleven_players_on` pin both findings.

Point-in-time check: `period_seconds`, `minute`, and `second` are `known_at_event`. Substitution events are `known_at_event`. Position-spell ends are `hindsight`.

## Results
**Clock.** 112 regressions in 100 of 270 matches.
- 94 are one pattern: the last `Ball Receipt*` before the first-half whistle is stamped about `00:00:00`–`00:00:02`, and its `minute` and `second` are also 0. It sits between events at minutes 46–49. This happens in 94 matches, once each. Steps range from −2,706 to −3,021 seconds.
- 18 are period-end events stamped 0.04–1.5 seconds before the last action. These are harmless.
- No other event type regresses by more than 5 seconds.

Effect on existing code:
- The Phase 1 side-shift detector reads `minute` and `second` on every event. At the corrupted receipt it sees "less than one window into the period" and returns no card for that single event.
- Warehouse metrics never count Ball Receipt or period-end events in team bins. `player_time_bins.located_events` places those 94 receipts in bin 0 of the first half (94 of 931,293 events).

**Lineups.** With intervals built from the union of spells, the median team has exactly 11.00 players on the pitch over match time. Before the fixes, a SQL alias bug and overlapping spells produced 11.7. Anomalies:
- 5 matches have overlapping or inverted spells. Two are the inspected World Cup matches, whose lineups are internally inconsistent (for example, substitutes the events bring on in the second half are listed from extra time).
- 8 matches have a substituted player whose lineup spell runs past the Substitution event. In 6 Premier League matches this is one player each, for example a half-time substitution with a lineup spell to the final whistle.
- `player_intervals` now cuts a spell at the player's Substitution event (11 intervals cut, `cut_by_substitution`). 16 of 540 team-matches have `lineup_consistent = false`.
- After the fixes, every consistent team-match has at most 11.02 players on the pitch. The small excess comes from lineup clocks having whole-second precision.
- Croatia in World Cup match 3869420 is under-covered (9.96 players on average), because its lineup file cannot be reconciled without guessing.

Confidence:
- **High (0.9)** that the Ball Receipt pattern is a provider timestamp artifact rather than a real event at kickoff. The surrounding sequence, location, and next event (Half End at minute 46–49) all place it at the end of the half.
- **Medium (0.7)** that the Substitution event is more reliable than the lineup spell when they disagree. It agrees with later events in the checked case, but only one match was inspected by hand.

**Addendum after wave 2 (800 matches, ingest run `9a6c9d48abd4fa3f`).**
- 128 matches (143 events) have clock regressions: 100 of 266 Premier League matches, but only 1 of 268 Serie A matches. The Ball Receipt artifact looks largely specific to Premier League 2015/16.
- The pinned patterns still hold: large regressions are only first-half Ball Receipts, and consistent lineups never exceed 11.02 players on the pitch.
- 46 of 1,600 team-matches have `lineup_consistent = false`.

## Counterexamples and alternative interpretations
- The receipt could be a genuine delayed record inserted late with a reset clock. Either way, its clock is unusable for windows.
- Lineup overlaps could reflect position changes the provider records with a lag rather than two simultaneous spells. Taking the union counts the time once either way.
- Premier League 2015/16 is one provider data version (1.1.0). Later waves may show different anomalies; rerun this note's queries after each wave.

## Owner judgment

## Decision
Investigate further before any detector change; nothing is changed in the Phase 1 detector now.
- Normalized data keeps provider values unchanged. The analytical layer flags them (`clock_out_of_order`, `lineup_consistent`) and quality warnings report them.
- Detector candidate (for owner review): skip window evaluation, or ignore the clock, on events whose timestamp regresses within a period. Because the corrupted event is the last receipt before the whistle, the Phase 1 effect is at most one skipped evaluation per first half.
- Player-involvement research should filter `analytical.team_matches.lineup_consistent`.
