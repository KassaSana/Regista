# Phase 1 Specification: Attacking-Side Shift

Last updated: 2026-09-28

**Status: initial defaults to evaluate.** These numbers are starting points, not tuned values. Change them only on development matches (see [AGENTS.md](../../AGENTS.md), leakage rules), and record every change here with its reason.

## What the fan sees
> "More of Barcelona's final-third entries are ending on the left: 9 of the last 14 (64%), up from 12 of 41 (29%) earlier."

When another channel still has more recent entries, the sentence adds it, for example "The right has more: 5." (Changed on 2026-09-28; see [research note 14](../research/14-side-shift-timing-and-wording.md). The Phase 1 wording "have shifted to the left" could suggest the named channel became the main route.)

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
The detector evaluates a team **only at that team's own final-third entries** (changed on 2026-09-28, [research note 14](../research/14-side-shift-timing-and-wording.md); Phase 1 evaluated every team at every event, which let 316 of 1,591 development cards fire on the other team's event and 65 more than three minutes after the team's last entry). At such an entry, it fires when all of these hold:
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
- **Evaluation:** the detector checks a team only at that team's own final-third entries (`fire_on_own_entry = True`). A shift that becomes visible because older entries leave the window is reported at the team's next entry. The Phase 1 rule, which checked every team on every event, remains available as `fire_on_own_entry = False`, and a research-only recency variant as `maximum_seconds_since_own_entry`; both exist for the frozen variant comparison on validation.
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
File: `tests/golden/3773497-attacking-side-shift.json` (derived output only). First generated 2026-09-27. Regenerated on 2026-09-28 for the own-entry timing and new wording, and reviewed: the same two Barcelona cards, each fired at Barcelona's next entry, about one minute later than before:
- Period 1, 24:14: "More of Barcelona's final-third entries are ending in the center: 7 of the last 11 (64%), up from 3 of 14 (21%) earlier." (Phase 1: 23:11, 6 of 11 from 3 of 13.)
- Period 2, 56:02: "More of Barcelona's final-third entries are ending on the left: 11 of the last 15 (73%), up from 13 of 54 (24%) earlier." (Phase 1: 55:03, 10 of 14 from 13 of 54.)

Inspect them with `uv run regista replay --match 3773497 --evidence`. It prints each card's channel table, every recent entry with its coordinates, and the baseline by period, together with any attacking burst cards ([specification](phase-2-attacking-burst.md)).

**Mechanical verification: passed (agent, 2026-09-27; rechecked 2026-09-28).** `test_cards_match_an_independent_recomputation` recomputes the cards from the raw file with separate, plain code (no adapter, domain, or detector imports), now evaluating a team only at its own entry, and the detector's cards match it exactly. `test_replay_matches_the_golden_snapshot` pins the full output. As a check that the test can fail, lowering the increase threshold to 20 points gave 4 cards and broke the match (2026-09-27).

Observations for review (facts, not tuning):
- Card 1 (center) is mostly a move away from the right: the baseline was 9 of 14 on the right (64%), and the recent window has 1 of 11 there.
- Card 2 (left) is a clear concentration: 11 of the 15 recent entries end on the left, against 24% before.

The snapshot is reviewed for correctness, never tuned toward an attractive result.
- [ ] Kassahun inspected the two cards with `--evidence`.

## Decisions (Kassahun, 2026-09-26)
- Set pieces are excluded. Open-play and set-piece entry counts may be kept separately later, but this detector uses open play only.
- Only increases produce cards; decreases are supporting evidence. This avoids two cards describing the same shift.
- A pass with any recorded outcome, including "Unknown", is not completed.

## Changes from development evidence (agent, 2026-09-28, pending owner review)
- Timing: evaluate a team only at its own final-third entries. This removes other-team triggers and stale cards, and loses 285 of 1,591 development cards, which were rarely sustained afterwards (3 of 65 eligible). See [research note 14](../research/14-side-shift-timing-and-wording.md).
- Wording: "More of X's final-third entries are ending ..." with a "has more" clause, and "Netherlands'" rather than "Netherlands's".
- Thresholds are unchanged.

## Known limitations
- Share-based rules favor the team with more of the ball. In a rough check of match 3773497, Real Madrid never exceeded 9 entries in any 10-minute window, so the minimums make them nearly invisible to this detector. Record this; do not lower the minimums to fix it on this match.
- A card says where entries went. It does not say why. No causal wording (for example "after the formation change") belongs in this template.
