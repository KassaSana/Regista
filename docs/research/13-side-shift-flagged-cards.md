# Research note: Independent review of flagged side-shift cards

Last updated: 2026-09-28

## Question

Do the cards flagged by the [automated side-shift audit](12-side-shift-automated-audit.md) reflect incorrect event counts, and what observable timing changes cause a card to fire on the other team's event? These questions matter because a mathematically correct card can still be confusing or late.

## Definitions

The locked final-third entry, channel, recent-window, baseline, threshold, and cooldown definitions remain those in [AGENTS.md](../../AGENTS.md) and the [Phase 1 specification](../specs/phase-1-attacking-side-shift.md). A **non-plurality card** names a channel with fewer recent entries than another channel. An **other-team trigger** has a trigger event whose acting team differs from the card team.

For an other-team trigger, the audit checks three possible changes since the preceding provider-order event: an entry crossed out of the 600-second recent window; the team's 600-second cooldown ended; or the first complete 600-second window of the period became available. These can coincide. The gap from the team's most recent current-period final-third entry to the trigger is measured in whole match-clock seconds.

## Data

- The same 800 acquired development matches and frozen `splits/v1.json` assignments as [research note 12](12-side-shift-automated-audit.md). No matches were excluded; no validation or test event file was opened.
- StatsBomb Open Data commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`. Each input's SHA-256 was checked against its pinned manifest receipt before use.
- Code: repository commit `07c4b34` plus `scripts/research/phase2_flagged_card_audit.py` and the small public-helper rename in `phase2_card_audit.py`. Aggregate output is retained locally in ignored `out/phase2-flagged-card-audit.json`.

## Method

Run `uv run python scripts/research/phase2_flagged_card_audit.py` from the repository root. For each match, load the raw JSON separately from the production adapter, sort raw records by provider `index`, and independently classify completed open-play passes and carries that cross x = 80. For each production card, reconstruct every earlier and recent supporting event identifier and channel count from raw records at or before its trigger. Fail if any evidence set or count differs. Classify non-plurality cards and other-team triggers only after that check.

This is an independent recomputation of **emitted card evidence**, not a full independent search for missed cards across every replay position. The golden-match contract test does independently recompute firing decisions on its one development match. The raw audit uses only event-order, time, team, pass type and outcome, and movement locations, with the same `known_at_event` or `delayed` availability as the production detector. Full-match tallying and classification occur retrospectively; no future event is a detector input.

## Results

All **1,591 cards** matched the separately parsed raw records exactly: recent and baseline event identifiers, ordering, and left/center/right counts. The prior audit's **112 non-plurality cards** and **316 other-team triggers** reproduced.

| Named channel among 112 non-plurality cards | Cards |
|---|---:|
| Center | 91 |
| Left | 9 |
| Right | 12 |

The Crystal Palace example at 31:19 in match `3753979` has recent counts left 0, center 3, right 5 and earlier counts left 5, center 1, right 6. Center's share rose from 1/12 to 3/8, enough to fire, while right remained the plurality. Thus the count is correct; whether "shifted to the center" communicates that change well is unresolved.

Every one of the 316 other-team triggers had at least one of the checked timing changes. An entry aged out of the recent window for 263, a cooldown ended for 54, and the period's first full window became available for 38. **These counts overlap and must not be added.** None was unexplained by all three checks.

| Time since the card team's last current-period entry | Other-team triggers |
|---|---:|
| At most 30 seconds | 62 |
| 31–60 seconds | 83 |
| 61–180 seconds | 136 |
| Over 180 seconds | 35 |

The 35 cards after more than three minutes without a new entry are possible timeliness concerns, not arithmetic errors. The longest-gap examples and timing flags can be reproduced from the local JSON output.

## Counterexamples and alternative interpretations

- A non-plurality channel can be the largest *increase* even while another channel retains the most entries. Replacing the wording or suppressing such cards needs a development-only variant comparison; this audit does not determine fan preference.
- A card can reasonably fire on another team's event when an older entry leaves the rolling window. A cooldown boundary or initial full window can also make a card newly eligible. No future event was used.
- The time since the last own entry is a timing proxy, not a measured display delay or a judgment of whether the card was useful. Period clocks are recorded to whole seconds in replay and need not strictly increase by provider index.
- This audit checks cards that fired. It cannot establish how many meaningful changes the current detector missed or how often a different provider would record the same entry.

Confidence: **0.99** that the emitted-card evidence and the two flagged counts reproduce from these pinned raw files; **0.95** in the three observed trigger-mechanism classifications; **not assessed** for fan usefulness or acceptable timeliness. These are research confidence scores, not calibrated probabilities.

## Owner judgment

<!-- Pending. Agents do not infer the owner's fan-usefulness or timing judgment. -->

## Decision

**Investigate further.** Do not change production thresholds or wording from these counts alone. The next development-only comparison should test a precise, neutral share-change sentence for non-plurality cards and a rule that requires a new entry by the card team before firing. Measure how many cards each variant changes or suppresses, including quiet and missed-moment cases, before freezing a variant for validation.

Data: StatsBomb
