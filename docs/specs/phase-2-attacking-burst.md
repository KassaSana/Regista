# Phase 2 Specification: Attacking Burst

Last updated: 2026-09-28

**Status: candidate under owner review; initial defaults to evaluate.** Chosen on development data in [research note 15](../research/15-second-detector-attacking-burst.md). Change thresholds only on development matches, and record every change here with its reason. The owner doubts that shot counts tell a fan anything the broadcast does not; [probe 02](../research/probe-02.md) tests that.

## What the fan sees
> "Real Madrid: 4 shots in the last 10 minutes, after 3 in the previous 24 minutes of play. Final-third entries in the last 10 minutes: 4."

The card cites every recent and earlier shot and every recent and earlier final-third entry by event identifier. It states counts only: never that the spell is unusual, dangerous, or likely to produce a goal.

## Definitions

| Term | Definition |
|---|---|
| Counted shot | A shot event whose provider shot type is not a penalty. Penalty kicks, including shootout kicks, never count. The adapter rejects unknown shot types. |
| Recent window | The team's counted shots in the last 10 minutes of the **current period**, half-open `(now − 600 s, now]`. A window never crosses a period boundary. |
| Earlier playing time | The span from each earlier period's first event to its latest event, plus the current period from its first event to the window start. It is learned in replay order. |
| Earlier rate | The team's counted shots before the window, divided by earlier playing time. |
| Final-third entries | The locked definition ([AGENTS.md](../../AGENTS.md)). Shown beside the shots, never used to decide firing. |

## Firing rule
The detector evaluates a team **only at that team's own counted shots**. It fires when all of these hold:
1. At least 10 minutes of the current period have elapsed.
2. Earlier playing time is at least **600 seconds**.
3. The recent window has at least **4** counted shots.
4. The recent rate is at least **3** times the earlier rate: `recent × earlier_seconds ≥ 3 × earlier × 600`, in exact integer arithmetic. With no earlier shots, condition 4 holds.

## Suppression
After a card, the team produces no burst card for **10 minutes** of match clock. The cooldown does not carry across a period boundary.

## Leakage guarantees
- The detector reads only events at or before the current replay position. It keeps no match-wide aggregate, and the earlier rate uses only time and shots already seen.
- Shot type and team are `known_at_event`. Carries, which appear only among the displayed entries, are `delayed`. Provider xG is not read.
- The property-based prefix-invariance test and a real-match prefix test must pass.

## Tests
| Required test | Where |
|---|---|
| Firing, quiet (steady rate), suppression, cooldown end, penalty exclusion, other team's shots, earlier-time minimum, period boundary, exact-ratio boundary | `tests/unit/detectors/test_attacking_burst.py` |
| Prefix invariance (synthetic, property-based) | `tests/unit/detectors/test_prefix_invariance.py` |
| Golden snapshot, prefix cut, and independent raw recomputation (match 3773497) | `tests/contract/test_attacking_burst_replay.py` |
| Shot-type mapping, including unknown types failing loudly | `tests/unit/adapters/test_statsbomb_match.py` |

## Golden snapshot (match 3773497)
File: `tests/golden/3773497-attacking-burst.json` (derived output only). Two cards:
- Period 1, 34:36: "Real Madrid: 4 shots in the last 10 minutes, after 3 in the previous 24 minutes of play. Final-third entries in the last 10 minutes: 4."
- Period 2, 93:56: "Barcelona: 5 shots in the last 10 minutes, after 12 in the previous 86 minutes of play. Final-third entries in the last 10 minutes: 9."

`test_cards_match_an_independent_recomputation` recomputes both from the raw file without the adapter, domain, or detector. The snapshot is reviewed for correctness, never tuned toward a result.

## Known limitations
- At a team's own shot volume, uniformly timed shots already produce about 74% as many cards (research note 15). The card reports what happened; it is not evidence of an unusual spell.
- Busier teams still get more cards: 28% of the lowest entry-volume quartile against 63% of the highest.
- Obviousness is the main open question. 29% of burst windows contain a goal, and shot runs are often visible on the broadcast. A "relative to other matches" variant would need baselines from earlier kickoffs only (AGENTS.md leakage rules).
