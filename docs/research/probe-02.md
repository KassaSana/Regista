# Research note: Fan-value probe 02 (card judging packet)

Last updated: 2026-09-28

**Status: first packet judged by Kassahun on 2026-09-28 (all 14 cards); gate decision pending.** This replaces full-match viewing (probe 01, declined on 2026-09-28) as the method for the Phase 2 fan-value gate.

## Question
Does Regista's combined card stream tell a fan something worth opening during play, which the broadcast and their own eyes would not already have told them? Is it better during play or after the match? This is the Phase 2 gate question in a form the owner can answer in about 30–45 minutes.

## Why this form
Full-match viewing asked for 90+ minutes per match beside an official replay, and was declined. A card packet keeps what that method needed: cards in match order, the score at that moment, and evidence to check. It drops the video. It is framed around the experience the owner proposed on 2026-09-28: during play, a small light-bulb indicator that opens to the insight; every card available after the match.

What this method **cannot** measure: missed moments (nothing Regista stayed silent about can be judged without watching), live timing against the broadcast, and attention cost while watching. The gate records these as limitations, not as passed.

## Data
- Five **development** matches, drawn with seed `20260928`, one per stratum: Premier League 2015/16, Serie A 2015/16, a recent club season, an international tournament, and any development match. The four already-inspected matches are excluded.
- Selection is among matches with at least one card. Matches with no cards (40 of 800 in the combined stream) cannot be judged card by card.
- Packet `be4eec07f144`: 14 cards (11 attacking burst, 3 attacking side). The mix follows the random draw, not the corpus ratio (867 burst to 1,322 side-shift cards).
- Code: repository commit `c8133f6` plus this increment's uncommitted changes. StatsBomb Open Data commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.

## Method
```console
cd scripts/research
uv run python phase2_judging_packet.py
```
This writes `out/phase2-judging/packet.html` and `selection.json` (git-ignored, because they describe provider events). Generation is deterministic: the same seed and code give the same packet identifier.

Each card shows its type, match clock, period, the score at that moment (the final result is never shown), the template sentence, a pitch map in the card team's attacking frame, and a count table. The questions for each card are:
1. If a light bulb lit up at this moment, would opening it have been worth it? (yes / maybe / no)
2. Would the broadcast or your own eyes probably have told you this already? (yes / no / not sure)
3. When is this most useful? (during play / after the match / neither)
4. Is the sentence clear on first read?
5. Does the evidence support the sentence?

For each match the packet asks about repetition and prior knowledge. At the end it asks whether you would use Regista again, which card you would have tapped for, and what was missing. Answers stay in the browser while you work; **Export answers** produces JSON to send back.

Point-in-time: the packet uses only fields the detectors already use. The score comes from shot outcomes and own goals at or before the trigger event (`known_at_event`).

## Pass bar (owner, set before opening the packet)
<!-- Placeholder: Kassahun sets the bar. Agents do not choose it. -->
- [ ] Pass bar recorded by Kassahun.

The first packet was judged before a bar was recorded, so any bar set now is set after seeing the answers. Record it as such.

## Results
The first judged version used the earlier questions: interrupt during the match, clear, and supported, plus per-match occasion and repetition. The light-bulb and "broadcast already told you" questions were added after this version was opened. Raw export: `out/phase2-judging/owner-answers-2026-09-28.json` (git-ignored).

| Card type | Cards | Would want it during the match (yes / maybe / no) | Clear (yes / no) | Evidence supports it (yes / no) |
|---|---:|---|---|---|
| Attacking side | 3 | 2 / 1 / 0 | 3 / 0 | 2 / 1 |
| Attacking burst | 11 | 5 / 0 / 6 | 10 / 1 | 10 / 1 |

- "Afterwards" was chosen for all four matches where occasion was answered. The fifth was left blank.
- No match had a repeated card.
- All five burst "yes" answers fall in the first nine cards; all six burst cards after card 9 are "no". Order and fatigue cannot be separated in one sitting.

Small, dependent sample: counts, not rates.

## Counterexamples and alternative interpretations
To be filled in after judging. Known in advance:
- Fourteen cards from five matches is a small, dependent sample. Report counts and quotes, never percentages (roadmap evaluation rule).
- Reading cards without video overstates how much attention a fan can give them, and cannot show whether the broadcast actually said the same thing.

## Owner judgment
Verbatim from the export (Kassahun, 2026-09-28). Sentences are the card text as shown.

| # | Match, time | Card | During match? | Clear? | Supported? | Note |
|---|---|---|---|---|---|---|
| 1 | Liverpool v Bournemouth, 30:14 (1–0) | Liverpool: 4 shots in the last 10 minutes, after 1 in the previous 20 | Yes | Yes | Yes | |
| 2 | same, 64:47 (1–0) | Bournemouth: 4 shots, after 4 in the previous 55 | Yes | Yes | Yes | |
| 3 | same, 68:57 (1–0) | More of Liverpool's entries ending on the right: 7 of 8, up from 11 of 33 | Yes | Yes | Yes | |
| 4 | same, 85:03 (1–0) | Bournemouth: 4 shots, after 8 in the previous 76 | Yes | Yes | Yes | |
| 5 | Genoa v Chievo, 21:22 (2–1) | Genoa: 4 shots, after none in the previous 11 | Yes | Yes | Yes | |
| 6 | same, 57:26 (2–1) | Chievo: 5 shots, after 7 in the previous 49 | No | Yes | Yes | |
| 7 | same, 64:02 (2–1) | More of Chievo's entries ending on the right: 8 of 11, up from 11 of 26 | Yes | Yes | Yes | |
| 8 | Atlético v Barcelona, 39:10 (0–0) | More of Barcelona's entries ending on the left: 6 of 8, up from 2 of 22 | Maybe | Yes | No | |
| 9 | same, 64:28 (1–0) | Barcelona: 4 shots, after 2 in the previous 57 | Yes | No | Yes | |
| 10 | same, 87:59 (1–0) | Barcelona: 4 shots, after 8 in the previous 81 | No | Yes | Yes | "this seems dumb hart to think its like 8 for 81 vs 4 for 10 liek its a diference but idk" |
| 11 | Colombia v Costa Rica, 33:01 (1–0) | Colombia: 4 shots, after 3 in the previous 23 | No | Yes | Yes | "this seems normal nothing craz like 3 for a lil while then 4 in 10 minutes is normal in a soccer game" |
| 12 | same, 81:09 (3–0) | Colombia: 5 shots, after 12 in the previous 73 | No | Yes | Yes | "i hate this bc 5 in 10 is 1 every 2 min and 12 pervios of like 73 is def lower but not like crazy loewr if tha makes sense also it dones't esem that much of differece i guess in teh human mind?" |
| 13 | South Africa v Tunisia, 80:10 (0–0) | South Africa: 4 shots, after 6 in the previous 72 | No | Yes | No | "hate this simliar probelms to what i mentioned in some of the earileir ones" |
| 14 | same, 94:42 (0–0) | Tunisia: 4 shots, after 7 in the previous 86 | No | Yes | Yes | "similar thing to what i said ealier ," |

Match note (Liverpool v Bournemouth and Genoa v Chievo): "These cards would be useful during play (but we can use a different approach for that), at halftime or any break or thing where someone has to wait befcaues of an injury or something idk anything that stops play for a good minute + , then afterwards of coures works great."

Agent observations (facts, not judgments):
- Card 8's counts reproduce from the raw events. All eight recent entries end within 6 units of x = 80, and three end on the touchline (y ≤ 2). Why the owner judged it unsupported is not recorded; ask rather than infer.
- The burst notes object to the rate comparison itself: a count over a long earlier span does not read as a meaningful difference.

## Decision
**Gate decision pending Kassahun** (no pre-set pass bar). What the judgments point to, for the owner to confirm or overrule:
- The burst card in its current form did not hold up: 6 of 11 "no", with notes rejecting the rate comparison.
- The side shift was received better (2 yes, 1 maybe of 3), but three cards are too few to rely on.
- Occasion: after the match and during stoppages, not live play. The roadmap rule for this case: "consider changing the usage occasion before adding capabilities".

Options once decided:
- **Pass:** freeze the detector variants, then compare them on validation (roadmap item 10).
- **Fail:** fix detection before anything else (the Phase 2 gate rule).

Data: StatsBomb
