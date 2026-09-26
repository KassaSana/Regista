# Phase 1 Specification: Attacking-Side Shift

**Status: initial defaults to evaluate.** These numbers are starting points, not tuned values. Change them only on development matches (see [AGENTS.md](../../AGENTS.md), leakage rules), and record every change here with its reason.

## What the fan sees
> "Barcelona's final-third entries have shifted to the left: 9 of the last 14 (64%), up from 12 of 41 (29%) earlier."

The card links to the supporting event identifiers for both the recent window and the baseline. (This example sentence is illustrative, not a detector result.)

## Definitions

| Term | Definition |
|---|---|
| Final-third entry | A completed pass or a carry that starts at x < 80 and ends at x ≥ 80, in the acting team's attacking frame. |
| Completed pass | A pass whose provider record has no outcome. (StatsBomb records an outcome only for unsuccessful passes. A contract test must pin this.) |
| Carry | Every carry counts as completed. |
| Channel | Taken from the entry's **end** location. Left: y < 80/3. Center: 80/3 ≤ y ≤ 160/3. Right: y > 160/3. Which side of y is the team's "left" is **pending a contract test**. |
| Match clock | Provider minute and second. Every calculation also carries the period. |
| Recent window | The team's entries in the last 10 minutes of the **current period**. A window never crosses a period boundary, so the detector cannot fire until 10 minutes into a period. This avoids the overlap between first-half stoppage time and the start of the second half. |
| Baseline | All of the team's entries in the match before the recent window starts, across periods. |

## Firing rule
For one team, at the current replay position, the detector fires when all of these hold:
1. The recent window has at least **8** entries.
2. The baseline has at least **12** entries.
3. One channel's share in the recent window exceeds its share in the baseline by at least **25 percentage points**.

If more than one channel qualifies, report the channel with the largest increase.

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
- Contract tests: completion status (pass outcome absent means completed) and channel orientation.

## Open questions (owned by Kassahun)
- `TODO(Kassahun)`: Do set pieces (free kicks, corners, throw-ins) count as entries, or only open play?
- `TODO(Kassahun)`: Should a sharp **decrease** in a channel also fire, or only increases?

## Known limitations
- Share-based rules favor the team with more of the ball. In a rough check of match 3773497, Real Madrid never exceeded 9 entries in any 10-minute window, so the minimums make them nearly invisible to this detector. Record this; do not lower the minimums to fix it on this match.
- A card says where entries went. It does not say why. No causal wording (for example "after the formation change") belongs in this template.
