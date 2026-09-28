# Research note: Automated attacking-side shift audit

Last updated: 2026-09-28

## Question

How often does the existing side-shift detector fire on the acquired development corpus, and which mechanically checkable card patterns might undermine clarity or attention value? The owner's requested review no longer requires watching full matches. This audit does not supply the owner's fan-usefulness judgment.

## Definitions

The detector and final-third entry definitions remain those in [AGENTS.md](../../AGENTS.md) and the [Phase 1 specification](../specs/phase-1-attacking-side-shift.md); no thresholds changed. One card is **not a recent plurality** when another channel has strictly more of the card team's entries in the 10-minute recent window. A **repeat** names the same channel for the same team again in one match. An **other-team trigger** fires at an event whose acting team differs from the card team; sliding-window expiry can make this valid.

For a retrospective persistence check only, a future window contains the card team's final-third entries in the same period, after the trigger and within the next 600 match-clock seconds. It is eligible with at least eight entries. A sustained shift means that channel's future share exceeds the card's earlier baseline share by at least 25 percentage points. Future events never feed the detector.

## Data

- 800 acquired matches, all marked **development** in `splits/v1.json` and the raw manifest. There were no exclusions. No validation or test match file was opened.
- StatsBomb Open Data source commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`; each event file's bytes were checked against its manifest SHA-256 receipt.
- Code: repository commit `1bae34d` plus `scripts/research/phase2_card_audit.py` in this increment. The script prints aggregate JSON; the run output is retained locally in ignored `out/phase2-card-audit.json`.

## Method

Run `uv run python scripts/research/phase2_card_audit.py` from the repository root. The script selects event receipts only after checking the frozen development assignments, loads each match through the production adapter, and runs the unchanged production detector in replay order. For every card it verifies the trigger, evidence identifiers, evidence counts, team, source, and that no supporting entry occurs after the trigger. It tallies card frequency, small recent samples, non-plurality directions, repeats, and other-team triggers. It then checks future-window shares separately as retrospective targets.

As a separate spot check, the read-only development warehouse's `analytical.final_third_entries` table was queried for match `3753979`, team `31`, period 1, with `period_seconds > 1279`, `period_seconds < 1880`, and `sequence <= 1115`. The warehouse stores fractional seconds while the replay card uses whole-second clocks, so the upper bound must include all of second 31:19. It independently returned center 3 and right 5, matching the card's eight recent entries. This checks one selected case, not all 1,591 cards.

Point-in-time fields used by the detector are event order, team, pass/carry type and completion, and start/end location (`known_at_event` or `delayed`, as detailed in [probe 01](probe-01.md)). The audit's full-match counts and future entries are retrospective only. The support checks share the production final-third classifier, so they establish internal consistency; the existing raw-record contract and independent golden-match recomputation test provide a separate check of that classifier on their stated scope.

## Results

The 800 matches produced **1,591 cards**, with **701 matches containing at least one**. Cards per match: 99 had zero, 211 had one, 229 had two, 155 had three, 77 had four, 25 had five, and four had six. The maximum was six. The detector named left 615 times, center 417, and right 559.

| Diagnostic | Cards | Share of all 1,591 cards |
|---|---:|---:|
| At most ten recent entries, against a minimum of eight | 1,364 | 85.7% |
| Named channel is not the most used recent channel | 112 | 7.0% |
| Repeats a team and channel within the match | 316 | 19.9% |
| Fires on an event by the other team | 316 | 19.9% |

For example, one Crystal Palace card names a shift toward the center with recent channel counts of left 0, center 3, right 5. This is mathematically consistent with an increase from its earlier center share, but the wording could imply that center was the main recent route. Match identifier `3753979`, period 1, minute 31, is in development. Other examples are in the local JSON output.

Only 446 of 1,591 cards (28.0%) had eight or more later same-period entries in the next ten minutes. Of those 446, 100 (22.4%) retained a share at least 25 points above the earlier baseline, and 70 (15.7%) matched or exceeded the card's recent share. The detector claims a change already observed, not a forecast, so these figures do **not** grade correctness. Windows overlap and matches, teams, and cards are dependent.

## Counterexamples and alternative interpretations

- A named channel can increase sharply without becoming the plurality; that is a genuine change but may require clearer wording. The audit does not decide whether those 112 cards are useful.
- Small recent samples meet the locked minimum and are not errors. A count of eight can still yield a volatile share, so the result warrants development-only sensitivity analysis before any threshold change.
- Other-team triggers can arise when an old entry leaves the sliding window. They need a timing review, but are not evidence of future leakage.
- Future-window sparsity and period endings exclude 1,145 cards from the persistence diagnostic. A short-lived shift may still be worth telling a fan about.
- [The public Wyscout event dataset](https://figshare.com/collections/Soccer_match_event_dataset/4415000/3) covers 2017/18 club seasons, the 2018 World Cup, and Euro 2016. The current pinned Regista corpus has none of those competition-seasons. A provider-to-provider card comparison would first require a separately scoped overlap corpus, definition alignment, and a frozen split; no Wyscout event file was opened here. Agreement between providers on an event count would check translation, not fan usefulness.

Confidence: **0.98** in the reported mechanical tallies and receipt checks for these 800 files; **0.90** that the diagnostics identify wording and timing questions worth examining; **not assessed** for fan usefulness. These scores describe this audit, not calibrated probabilities.

## Owner judgment

<!-- Pending. The owner declined full-match viewing; agents do not substitute a usefulness judgment. -->

## Decision

**Investigate further.** Keep the production thresholds and templates unchanged in this increment. The next automated development-only check should inspect non-plurality and other-team-trigger cases against independently calculated event windows, then compare any proposed wording or suppression variant on validation only after it is frozen. This audit supports backend signal review, not a claim that the companion experience is valuable.

Data: StatsBomb
