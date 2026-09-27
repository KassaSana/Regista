# Phase 1 Specification: Attacking-Side Shift

Last updated: 2026-09-27

**Status: initial defaults to evaluate.** These numbers are starting points, not tuned values. Change them only on development matches (see [AGENTS.md](../../AGENTS.md), leakage rules), and record every change here with its reason.

## What the fan sees
> "Barcelona's final-third entries have shifted to the left: 9 of the last 14 (64%), up from 12 of 41 (29%) earlier."

The card links to the supporting event identifiers for both the recent window and the baseline. (This example sentence is illustrative, not a detector result.)

## Definitions

| Term | Definition |
|---|---|
| Final-third entry | An **open-play** completed pass or a carry that starts at x < 80 and ends at x ≥ 80, in the acting team's attacking frame. |
| Open play | Decided per event from the pass type. Corner, Free Kick, Throw-in, Goal Kick, and Kick Off passes are set pieces and excluded. Recovery and Interception passes count. Carries always count. The possession-level `play_pattern` is never used: it labels whole possessions and may be assigned with hindsight. The adapter rejects any other pass type, so the contract test `test_every_event_normalizes_in_strict_provider_order` pins the values. |
| Completed pass | A pass whose provider record has no outcome. Any recorded outcome, including "Unknown", means not completed: Regista never claims a completion the provider cannot confirm. (StatsBomb records an outcome only for passes that did not complete; `test_pass_outcomes_only_ever_mark_a_pass_as_not_completed` pins this. Match 3773497 has 4 "Unknown" passes.) |
| Carry | Every carry counts as completed. |
| Channel | Taken from the entry's **end** location. Left: y < 80/3. Center: 80/3 ≤ y ≤ 160/3. Right: y > 160/3. Low y is the acting team's left: in match 3773497, left-sided defenders average y ≈ 11–13 and right-sided ones y ≈ 59–68. Pinned by the contract test `test_low_y_is_the_acting_teams_left`. |
| Match clock | Provider minute and second. Every calculation also carries the period. |
| Recent window | The team's entries in the last 10 minutes of the **current period**. A window never crosses a period boundary, so the detector cannot fire until 10 minutes into a period. This avoids the overlap between first-half stoppage time and the start of the second half. |
| Baseline | All of the team's entries in the match before the recent window starts, across periods. |

## Firing rule
For one team, at the current replay position, the detector fires when all of these hold:
1. The recent window has at least **8** entries.
2. The baseline has at least **12** entries.
3. One channel's share in the recent window exceeds its share in the baseline by at least **25 percentage points**.

If more than one channel qualifies, report the channel with the largest increase. Only increases produce a card; the channels that lost share appear in the card as supporting evidence. An increase split across two channels that reaches the threshold in neither produces no card.

## Suppression
After a card fires for a team, that team produces no side-shift card for **10 minutes** of match clock, whatever the channel. The cooldown does not carry across a period boundary.

## Leakage guarantees
- The detector reads only events at or before the current replay position.
- There are no match-wide aggregates; the baseline is "everything so far," never "the whole file."
- The prefix-invariance test (replay to minute N, alter everything after N) must leave earlier cards unchanged.

## Required tests
- Synthetic firing case: hand-built events that must produce exactly one card.
- Quiet case: balanced channels produce no card.
- Suppression case: a second qualifying shift inside the cooldown produces no card.
- Minimum-count case: a large share change with too few entries produces no card.
- Period case: a window never includes events from the previous period.
- Real-match golden snapshot for match 3773497, reviewed for correctness, not tuned toward.
- Set-piece case: a qualifying shift made only of set-piece passes produces no card.
- Contract tests: completion status (pass outcome absent means completed), pass type values, and channel orientation.

## Implementation notes
Code: `src/regista/detectors/attacking_side_shift.py` (settings in `SideShiftSettings`), with definitions in `src/regista/domain/entries.py` and wording in `src/regista/templates.py`.
- **Evaluation:** the detector checks every team on every event, because the window slides even when a team has the ball rarely.
- **Period start:** the clock of the first event seen in that period (StatsBomb's Half Start events). It is learned during replay, never read from the whole file.
- **Window bounds:** the recent window is half-open, `(now − 600 s, now]`. An entry exactly 10 minutes old belongs to the baseline.
- **Exact arithmetic:** shares are exact fractions, so an increase of exactly 25 points fires and never depends on floating-point rounding.
- **Ties:** equal qualifying increases go to the first channel in left, center, right order.
- **Cooldown boundary:** a team fires again at exactly 10 minutes after its last card, not before.
- **Percentages in the sentence:** rounded to whole numbers, halves rounding up.

## Test map
| Required test | Where |
|---|---|
| Firing, quiet, suppression, minimum-count, period, and set-piece cases | `tests/unit/detectors/test_attacking_side_shift.py` |
| Prefix invariance (synthetic, property-based) | `tests/unit/detectors/test_prefix_invariance.py` |
| Prefix invariance, golden snapshot, and independent recomputation (match 3773497) | `tests/contract/test_attacking_side_shift_replay.py` |
| Completion status, pass type values, channel orientation | `tests/contract/test_statsbomb_event_contract.py` |

## Golden snapshot (match 3773497)
File: `tests/golden/3773497-attacking-side-shift.json` (derived output only). Generated 2026-09-27 with the initial defaults. It produced two cards, both for Barcelona:
- Period 1, 23:11: "Barcelona's final-third entries have shifted to the center: 6 of the last 11 (55%), up from 3 of 13 (23%) earlier."
- Period 2, 55:03: "Barcelona's final-third entries have shifted to the left: 10 of the last 14 (71%), up from 13 of 54 (24%) earlier."

Inspect them with `uv run regista replay --match 3773497 --evidence`, which prints each card's channel table, every recent entry with its coordinates, and the baseline by period.

**Mechanical verification: passed (agent, 2026-09-27).** `test_cards_match_an_independent_recomputation` recomputes the cards from the raw file with separate, plain code (no adapter, domain, or detector imports), and the detector's cards match it exactly. `test_replay_matches_the_golden_snapshot` pins the full output. As a check that the test can fail, lowering the increase threshold to 20 points gives 4 cards and breaks the match.

Observations for review (facts, not tuning):
- Card 1 (center) is mostly a move away from the right: the baseline was 8 of 13 on the right (62%), and the recent window has 2 of 11 there. Its baseline of 13 is just above the minimum of 12.
- Card 2 (left) is a clear concentration: 10 of the 14 recent entries end on the left, against 24% before.

The snapshot is reviewed for correctness, never tuned toward an attractive result.
- [ ] Kassahun inspected the two cards with `--evidence`.

## Decisions (Kassahun, 2026-09-26)
- Set pieces are excluded. Open-play and set-piece entry counts may be kept separately later, but this detector uses open play only.
- Only increases produce cards; decreases are supporting evidence. This avoids two cards describing the same shift.
- A pass with any recorded outcome, including "Unknown", is not completed.

## Known limitations
- Share-based rules favor the team with more of the ball. In a rough check of match 3773497, Real Madrid never exceeded 9 entries in any 10-minute window, so the minimums make them nearly invisible to this detector. Record this; do not lower the minimums to fix it on this match.
- A card says where entries went. It does not say why. No causal wording (for example "after the formation change") belongs in this template.
