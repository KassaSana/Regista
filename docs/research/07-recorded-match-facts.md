# Research note: Recorded match facts for Phase 3

Last updated: 2026-09-28

## Question

Which lineup, substitution, and formation records can support factual replay
observations, and how busy would a stream of those observations be?

## Definitions

- **Starting lineup:** a provider `Starting XI` event with its recorded
  formation and eleven player records, available before kickoff.
- **Substitution:** a provider `Substitution` event naming the departing player
  and replacement. The provider reason is excluded from the proposed wording.
- **Formation change:** a provider `Tactical Shift` whose recorded formation
  differs from that team's most recent `Starting XI` or `Tactical Shift`
  formation in event order. A repeated formation is not described as a change.
- **Near a substitution:** a `Tactical Shift` within 60 provider-clock seconds
  of a substitution by the same team and period. It measures co-occurrence,
  not causation.

## Data

The 800 development matches in frozen split version one, from the pinned
StatsBomb Open Data commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.
Warehouse ingest run `72e2ced0e72fc4eb` at clean git `1aa2425a66cf`.
No validation or test match data was opened.

## Method

Read `normalized.formation_changes`, `normalized.substitutions`, and
`normalized.events` through `regista.warehouse.research.connect_research`.
The core comparison is:

```sql
SELECT f.match_id, f.team_id, f.kind, f.formation,
  lag(f.formation) OVER (
    PARTITION BY f.match_id, f.team_id ORDER BY e.sequence
  ) AS previous
FROM normalized.formation_changes AS f
JOIN normalized.events AS e USING (event_id);
```

Counts by kind and match, and substitution counts, were grouped from those
tables. A second query joined shift and substitution events on match, team,
period, and absolute clock difference at most 60 seconds. The proposed fact
count per match is two starting lineups plus substitutions plus shifts with a
different formation.

Point-in-time check: `Starting XI`, `Substitution`, and `Tactical Shift` event
identifiers, event order, formation, and player names are `known_at_event` (the
starting lineup is known before kickoff). No hindsight field or result after
the event is needed. The 60-second co-occurrence uses both observed events
only for retrospective analysis and never implies a cause.

## Results

| Record | Events | Matches |
|---|---:|---:|
| Starting XI | 1,600 | 800 |
| Substitution | 5,384 | 800 |
| Tactical Shift | 2,031 | 716 |

Every match has exactly one `Starting XI` event per team. Of the 2,031
`Tactical Shift` events, **1,288 (63.4%) repeat** the team's last recorded
formation and **743 (36.6%) change** it. At least 1,287 shifts occur within a
minute of a same-team substitution. The recorded substitution reason is
`Tactical` for 4,985 and `Injury` for 399; this note does not infer a medical
condition or a coach's motive from either label.

Showing every starting lineup, substitution, and changed formation would make
7,727 candidate facts across 800 matches: a mean of 9.66 per match, median 9,
90th percentile 13, and maximum 17. These counts precede any side-shift or
other Phase 2 observations. Windows and matches are not a random sample of all
football; two 2015/16 leagues provide most development matches.

## Counterexamples and alternative interpretations

- A `Tactical Shift` with the same formation may record player-position changes
  within that shape. Calling it a formation change would be false; suppressing
  it also loses a possible positional observation until that evidence is
  modeled explicitly.
- A shift near a substitution may be part of the same provider annotation
  sequence, but proximity alone does not establish that the substitution
  caused it.
- Around ten facts per match before trend cards could be too busy for a live
  companion. Frequency alone cannot tell whether fans value particular facts
  or prefer them in an evidence view.

## Confidence

Scores are judgmental evidence strength, not calibrated probabilities.

- **0.95:** these counts and repeated-formation proportions describe the
  development warehouse; the adapter validated every match.
- **0.85:** a formation-change sentence is supported when consecutive recorded
  formations differ.
- **0.35:** displaying all candidate facts as cards would improve the viewing
  experience. No owner or fan judgment has been collected.

## Owner judgment

Kassahun's fan-usefulness judgment remains empty.

| Match, time | Observation | Correct? | Timely? | Added understanding? | Attention cost | Repetitive? | Keep or drop | Better at halftime or after? | Notes |
|---|---|---|---|---|---|---|---|---|---|---|

## Decision

**Implement a provisional, separate fact stream and evaluate later.** It can
state the starting lineup, recorded substitutions, and actual recorded
formation changes with event evidence. It must not claim causes or medical
conditions. Do not merge the stream into the default Phase 2 cards or claim
the Phase 3 gate passed until redundancy and attention cost have been judged.
