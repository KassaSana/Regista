# Research note: Territory against earlier play in the match

Last updated: 2026-09-28

## Question

When a team makes more final-third entries than it did earlier in the same
match, does that spell also contain more shots or xG? This is the comparison
axis used by the probe's territory prototype; the answer does not establish
whether a fan wants a card.

## Definitions

- A final-third entry uses the locked definition in [AGENTS.md](../../AGENTS.md).
  The analytical table carries `definition_version = 1`.
- Fixed, non-overlapping, complete 10-minute windows start at each regular-time
  half's zero. A window is retained only when its team has at least two earlier
  complete windows in that match. Its **entry excess** is its entry count minus
  the mean count over all those earlier windows. Shot and provider-xG excesses
  use the same calculation. The earlier baseline uses no future window.
- Score state is the team's lead, tie, or deficit before the first event in the
  window. A separate subset excludes windows in which either team scored.
- For the diagnostic "attributed xG per entry," a shot counts only when it is
  open play and follows a completed open-play final-third entry by the shooting
  team in the same provider possession and the same window. Provider possession
  grouping is hindsight and is used only for this retrospective check.
- Five entry-excess bins use corpus quantiles, with ties kept together. Those
  quantiles are retrospective research summaries, never live thresholds.

## Data

- Frozen split: development only, version one; 800 matches, 174 teams, 2015–2024.
  No validation or test match file was opened.
- StatsBomb Open Data commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.
- Development warehouse ingest run `72e2ced0e72fc4eb`, built cleanly at git
  `1aa2425a66cf` with DuckDB 1.5.5. All 800 matches passed blocking checks.
- Analysis: [territory_earlier_match.py](../../scripts/research/territory_earlier_match.py),
  SHA-256 `f05ae3a2e8a031fa1d25800371fd888a2c20f94d30b660efffac15a996b18906`.
  The ignored result is `out/research/06-territory-earlier-match.json`.

## Method

Run `uv run python scripts/research/territory_earlier_match.py`. The script
opens the development warehouse through the read-only, external-access-disabled
research connection. It reuses the window query from research note 05, then
uses `STATE_SQL` and `ATTRIBUTED_SQL` in the script. Spearman intervals resample
whole matches 1,000 times with a fixed seed; the bootstrap uses full-sample
ranks as an approximation. Both teams and several windows of one match are
correlated, so window counts are not independent sample sizes.

Point-in-time availability: pass location, pass type/outcome, and goals before
the window are `known_at_event`; carries and provider shot xG are `delayed`.
The comparison uses only earlier windows and the current completed window.
Provider possession grouping is `hindsight` and is confined to the diagnostic
attribution calculation. The note is retrospective and makes no live-timing
claim for xG.

## Results

There are 10,264 eligible team-windows from all 800 matches. The first two
complete windows per team-match are excluded, along with incomplete half-end
windows and extra time. None of the retained shots lacks provider xG. The
analysis includes goals and penalties in the primary xG measure.

| Entry excess versus | Windows | Spearman ρ | Approximate 95% match-bootstrap interval |
|---|---:|---:|---:|
| Shot excess, all states | 10,264 | 0.25 | 0.23–0.27 |
| xG excess, all states | 10,264 | 0.15 | 0.13–0.17 |
| Shot excess, goal-free windows | 7,628 | 0.26 | 0.24–0.28 |
| xG excess, goal-free windows | 7,628 | 0.19 | 0.16–0.21 |

The score state before the window does not remove the association:

| State | Windows | ρ, shots | ρ, xG |
|---|---:|---:|---:|
| Level | 4,576 | 0.23 | 0.12 |
| Leading | 2,844 | 0.22 | 0.08 |
| Trailing | 2,844 | 0.21 | 0.11 |

The top entry-excess bin contains 2,035 windows, averaging 4.42 more entries,
0.58 more shots, and 0.050 more xG than their earlier-match averages. Yet 384
of those windows (18.9%) contain no shot. From the lowest to highest bin,
all-shot xG per entry falls from 0.052 to 0.018. Restricting to open-play shots
after an entry in the same possession and window also falls, from 0.025 to
0.012 xG per entry.

## Counterexamples and alternative interpretations

- The 384 high-entry-excess windows without a shot directly counter any claim
  that more territory necessarily brought immediate threat.
- Entry and shot counts both rise with time on the ball. This study does not
  control possession duration, opponent behaviour, or team strength.
- The falling xG-per-entry ratio persists with the narrower shot attribution,
  but dividing by a large entry count can itself make the ratio fall. A shot
  after an entry need not have been caused by that entry, and a shot separated
  by a window boundary is omitted from the diagnostic.
- The score-state proxy is taken from the first event in each clock window.
  Known provider clock regressions can misplace events. The goal-free subset
  limits one concern but does not repair those timestamps.
- Two 2015/16 leagues provide most windows. Single-team seasons and tournament
  development matches are not representative of entire leagues or knockout
  stages. The results describe this corpus, not football in general.

## Confidence

These are judgmental evidence scores, not calibrated probabilities.

- **0.85:** entry excess has a modest positive same-window association with
  shots in this development corpus; it survives the earlier-match and
  score-state comparisons.
- **0.75:** the corresponding xG association is positive but weaker.
- **0.45:** the falling xG-per-entry pattern represents a distinct sterile
  pressure phenomenon; denominator effects and possession differences remain.
- **Not assessed:** whether any such observation is useful or timely for a fan.

## Owner judgment

Kassahun's fan-usefulness judgment remains empty pending probe 01.

| Match, time | Observation | Correct? | Timely? | Added understanding? | Attention cost | Repetitive? | Keep or drop | Better at halftime or after? | Notes |
|---|---|---|---|---|---|---|---|---|---|---|

## Decision

**Investigate further; no detector change.** Territory and threat should
remain separately measured. Comparing with earlier play does not make entries
a strong threat proxy, and the top-bin counterexamples are common. Probe 01
must supply the fan judgment before any territory prototype is promoted.
The next technical comparison should control for time on the ball or possessions
before interpreting the declining xG-per-entry ratio as a tactical pattern.
