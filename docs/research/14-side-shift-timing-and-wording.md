# Research note: Side-shift timing and wording variants

Last updated: 2026-09-28

## Question

Research note 13 found two ways a correct side-shift card can still mislead or arrive late. First, 112 cards name a channel that is not the most used recent channel. Second, 316 cards fire on the other team's event, including 35 fired more than three minutes after the card team's last entry. Which timing rule removes stale and other-team triggers without losing timely cards? And which sentence states a share increase without implying that the named channel became the main route? A fan cares because a card that seems late or wrong costs trust (standing risk 3).

## Definitions

The final-third entry, channel, window, baseline, threshold, and cooldown definitions are unchanged ([AGENTS.md](../../AGENTS.md), [Phase 1 specification](../specs/phase-1-attacking-side-shift.md)). Only the **evaluation moment** varies:

| Variant | A team is evaluated at |
|---|---|
| `current` (Phase 1) | every event, whoever acted |
| `own_entry` | only the team's own final-third entries |
| `own_entry_within_Ns` | any event, while the team's latest current-period entry is at most N seconds old (N = 30, 60, 120) |

A variant card is **paired** with a `current` card when team, channel, and period agree and they fire at most 600 seconds apart. Pairing is nearest-first and one-to-one. **Lost** cards are unpaired `current` cards; **new** cards are unpaired variant cards. A card is **stale** when its team's last current-period entry came more than 180 seconds before it fired.

**Retrospective persistence** (the note 12 target, used only for evaluation): a card is eligible when at least eight same-period entries by its team follow within ten minutes. It is **sustained** when the named channel's later share is at least 25 points above the card's baseline share. Future events never feed a card.

## Data

- All 800 acquired development matches under `splits/v1.json`, with raw files checked against their manifest SHA-256 receipts. No exclusions. No validation or test file was opened.
- StatsBomb Open Data commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.
- Code: repository commit `c8133f6` plus this increment's uncommitted changes (the `fire_on_own_entry` and `maximum_seconds_since_own_entry` settings, and `scripts/research/phase2_side_shift_variants.py`). Output is kept locally in ignored `out/research/phase2-side-shift-variants.json`.

## Method

```console
cd scripts/research
uv run python phase2_side_shift_variants.py
```

Every variant runs through the production detector with one setting changed, so cooldown interactions are real rather than simulated by filtering `current` cards. Point-in-time fields: event order, team, pass type and outcome, and movement locations (`known_at_event`); carries (`delayed`). The persistence target reads later events only after the replay, for evaluation.

Reproducibility check: the `current` variant reproduces the audits exactly: 1,591 cards, 112 non-plurality, 316 other-team triggers, and 100 of 446 eligible cards sustained. A second full run gave byte-identical output.

## Results

| Variant | Cards | Matches with a card | Non-plurality | Other-team triggers | Stale (> 180 s) | Sustained / eligible |
|---|---:|---:|---:|---:|---:|---:|
| `current` | 1,591 | 701 | 112 | 316 | 65 | 100 / 446 (22%) |
| `own_entry` | 1,322 | 658 | 83 | 0 | 0 | 86 / 372 (23%) |
| `own_entry_within_30s` | 1,398 | 666 | 92 | 69 | 0 | 93 / 402 (23%) |
| `own_entry_within_60s` | 1,445 | 677 | 99 | 145 | 0 | 92 / 414 (22%) |
| `own_entry_within_120s` | 1,528 | 690 | 102 | 248 | 0 | 94 / 436 (22%) |

Compared with `current`:

| Variant | Paired | Same second | Later (median delay) | Later by > 120 s | Lost | New | Lost that were sustained |
|---|---:|---:|---:|---:|---:|---:|---:|
| `own_entry` | 1,306 | 944 | 342 (55 s) | 93 | 285 | 16 | 3 / 65 eligible |
| `own_entry_within_30s` | 1,379 | 1,097 | 271 (49 s) | 57 | 212 | 19 | 1 / 45 |
| `own_entry_within_60s` | 1,434 | 1,252 | 173 (51 s) | 32 | 157 | 11 | 0 / 31 |
| `own_entry_within_120s` | 1,524 | 1,450 | 70 (58 s) | 15 | 67 | 4 | 0 / 9 |

For comparison, the `current` cards that `own_entry` keeps were sustained in 97 of 381 eligible cases (25%).

- `own_entry` is the only variant that removes other-team triggers entirely. It removes every stale card, has no parameter to tune, and a card always appears on the attacking action that completes the shift.
- It loses 285 cards (18%). 143 of them were other-team triggers. The lost cards were rarely sustained: 3 of 65 eligible (5%), against 25% for kept cards. By this retrospective target, the dropped cards were mostly shifts that faded before the team's next entry.
- 342 cards arrive later, with a median delay of 55 seconds and 93 more than two minutes late. These are cards that the Phase 1 rule fired on an event that did not involve the team's own attacking. Whether a card at the next entry feels timelier to a fan than one on an aging-out event is an owner judgment.
- The recency variants keep more cards but keep some other-team triggers and need a time limit chosen without fan evidence.

**Wording.** The Phase 1 sentence "X's final-third entries have shifted to the center" can suggest the center became the main route. For example, a Crystal Palace card in match 3753979 reads that way with recent counts left 0, center 3, right 5. The replacement sentence says that more entries are ending in a channel and gives the same counts. When another channel still has more recent entries, it adds that fact. Here it is rendered from that card's Phase 1 counts:

> More of Crystal Palace's final-third entries are ending in the center: 3 of the last 8 (38%), up from 1 of 12 (8%) earlier. The right has more: 5.

It also fixes the possessive for team names ending in "s" ("Netherlands'", previously "Netherlands's"; probe 01). Under `own_entry`, 83 of 1,322 cards (6%) carry the added clause.

## Counterexamples and alternative interpretations

- Persistence is a proxy, not correctness or usefulness. A short-lived shift can still be worth seeing, and 65 eligible lost cards is a small sample. Windows overlap, and cards within one match are dependent.
- A 55-second median delay is small against a 10-minute window, but 93 cards wait more than two minutes. A fan might prefer an earlier card on an aging-out event. The owner packet, not this note, can judge that.
- Pairing within 600 seconds could pair two genuinely different moments. It changes the paired/lost split, not the variant totals.
- The added clause makes non-plurality cards longer. Suppressing those cards instead would lose 6% of cards whose share increase is real.

Confidence: **0.97** in the reported counts and pairings for these pinned files. **0.8** that `own_entry` removes the timing issue note 13 identified without removing many persistent shifts. **0.85** that the new sentence cannot be read as claiming the named channel has the most entries. **Not assessed** for fan usefulness or preferred timing. These are analytical confidence scores, not calibrated probabilities.

## Owner judgment

<!-- Pending. The Phase 2 judging packet (probe 02) shows cards under the new rule and wording; agents do not infer the owner's judgment. -->

## Decision

**Change the detector and template, provisionally.**

- The side-shift detector now evaluates a team only at its own final-third entries (`fire_on_own_entry = True`). The template now uses the neutral sentence with the "has more" clause.
- Both are development-evidence choices, recorded in the [Phase 1 specification](../specs/phase-1-attacking-side-shift.md). The golden snapshot was regenerated and reviewed: the same two cards, each about one minute later at Barcelona's next entry, with the new wording. The independent recomputation matches.
- The Phase 1 rule stays available as `fire_on_own_entry = False`, for the frozen variant comparison on validation that the roadmap requires once the gate allows it.
- Thresholds are unchanged.

Data: StatsBomb
