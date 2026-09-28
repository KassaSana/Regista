# Research note: Does a fair Phase 2 evaluation need a second detector?

Last updated: 2026-09-28

## Question

The Phase 2 gate asks whether a replayed match is worth watching with Regista. If the only card type covers mainly the team with more of the ball, a judge sees one side of most matches, and the verdict would be about one rule rather than the idea. Does the side-shift detector alone give a fair basis for judgment? If not, does the roadmap's "attacking burst" candidate cover the gap without flooding the stream?

## Definitions

- **Entry volume:** a team's completed open-play final-third entries in the whole match (locked definition). It is used only to group team performances retrospectively; no detector reads it.
- **Coverage:** the share of team performances (team × match) that get at least one card.
- **Attacking burst** (candidate, specified in [phase-2-attacking-burst.md](../specs/phase-2-attacking-burst.md)):
  - A team's non-penalty shots in the last 10 minutes of the current period are at least `S`.
  - Its recent shot rate is at least `R` times its rate over all earlier playing time.
  - There are at least 10 minutes of earlier play.
  - It is evaluated at the team's own shots, with a 10-minute team cooldown.
  - Final-third entries are shown beside the shots but never decide firing.
- **Uniform-time reference:** each team's counted shots are placed at uniformly random times over the playing time observed in that match (10 seeded draws per team performance) and replayed through the same detector. It shows how many cards chance clustering alone produces at a team's own shot volume. It is a reference distribution, not a false-alarm rate.

## Data

- All 800 acquired development matches (1,600 team performances); raw files checked against manifest SHA-256 receipts. No validation or test file was opened.
- StatsBomb Open Data commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`. Every shot type in these files maps to the adapter's strict shot-type list; the run would fail on an unknown type.
- Code: repository commit `c8133f6` plus this increment's uncommitted changes (`ShotDetail`, `regista.detectors.attacking_burst`, `scripts/research/phase2_side_shift_variants.py`, `scripts/research/phase2_attacking_burst.py`). Outputs are kept locally in ignored `out/research/`.

## Method

```console
cd scripts/research
uv run python phase2_side_shift_variants.py   # side-shift coverage by entry volume
uv run python phase2_attacking_burst.py       # burst sweep, reference, combined stream
```

Point-in-time fields: shot events and their type (`known_at_event`), event order, team, period and clock (`known_at_event`), pass type, outcome and locations (`known_at_event`), and carries (`delayed`). Provider xG is not used. Goals in a burst window are counted afterwards from shot outcomes, for description only.

## Results

**Side-shift coverage depends on entry volume.** The quartile edges of whole-match entries are 33, 43, and 56.

| Entry-volume quartile | Performances | With a side-shift card (Phase 1 rule) | With a side-shift card (`own_entry` rule) |
|---|---:|---:|---:|
| Q1 (≤ 33 entries) | 401 | 37 (9%) | 33 (8%) |
| Q2 | 405 | 157 (39%) | 130 (32%) |
| Q3 | 395 | 301 (76%) | 261 (66%) |
| Q4 (> 56) | 399 | 385 (96%) | 371 (93%) |

Under the Phase 1 rule, only one team received any card in 522 of 800 matches (65%), both teams in 179, and neither in 99. This confirms standing risk 6 and [research note 02](02-share-based-bias.md) at corpus scale. A judge of the side-shift stream alone would mostly see the busier team.

**Burst sweep.** Cards per match (both teams), the uniform-time reference, and coverage of the lowest entry quartile:

| Shots ≥ S | Rate ratio ≥ R | Cards / match | Reference cards / match | Real ÷ reference | Q1 coverage | Q4 coverage |
|---:|---:|---:|---:|---:|---:|---:|
| 3 | 1 | 3.43 | 3.24 | 1.06 | 236/401 | 383/399 |
| 3 | 2 | 2.67 | 2.34 | 1.14 | 229/401 | 361/399 |
| 3 | 3 | 1.77 | 1.39 | 1.27 | 207/401 | 292/399 |
| 4 | 1 | 1.75 | 1.53 | 1.14 | 120/401 | 330/399 |
| 4 | 2 | 1.54 | 1.27 | 1.22 | 120/401 | 313/399 |
| **4** | **3** | **1.08** | **0.81** | **1.35** | **112/401** | **250/399** |
| 5 | 2 | 0.71 | 0.56 | 1.28 | 50/401 | 215/399 |
| 5 | 3 | 0.55 | 0.39 | 1.44 | 48/401 | 176/399 |

(Ratios 3/2 are in the JSON output and fall between the neighbouring rows.) Mean counted shots per performance rise from 8.5 in Q1 to 17.1 in Q4, so shot bursts also favour busier teams, but much less than entry shares do.

**Chosen initial defaults: S = 4, R = 3.**

- **Sparsity:** it is the sparsest setting that keeps low-volume coverage. It gives 1.08 cards per match against the side-shift's 1.65.
- **Coverage:** it covers 112 of 401 lowest-volume performances (28%), against 33 (8%) for the side shift.
- **Size of effect:** real play produces 35% more cards than the uniform-time reference at this setting. That is higher than any setting with S ≤ 4 and R ≤ 2.
- **Rejected neighbours:** S = 3 is close to the reference (6–27% above) and busy. S = 5 gives up most of the low-volume coverage.

At the defaults: 867 burst cards. Four shots in the window in 683 cards; five or more in 184. In 248 cards (29%) the window includes a goal.

**Combined stream** (side shift with `own_entry`, plus burst):

| Cards in a match | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Matches | 40 | 134 | 208 | 186 | 129 | 65 | 27 | 10 | 1 |

That is 2.74 cards per match. Both teams get at least one card in 327 matches (41%), against 179 (22%) before. 54 pairs of consecutive cards fall within 60 seconds of each other in the same period.

On the golden match 3773497, the burst detector produces a Real Madrid card at 34:36, "Real Madrid: 4 shots in the last 10 minutes, after 3 in the previous 24 minutes of play." Real Madrid never receives a side-shift card in that match.

## Counterexamples and alternative interpretations

- A burst card is mostly what chance clustering would produce at the team's shot volume: the reference yields 74% as many cards. A burst of shots is still an observable, true event that a fan may notice or miss, but the card must not claim it is unusual or predictive. The template states counts only.
- Coverage is not usefulness. The owner may find bursts obvious from the broadcast; 29% already contain a goal.
- The uniform-time reference ignores game state, substitutions, and period effects, which makes real clustering more likely. The comparison therefore overstates how much of the card volume is chance.
- Other candidates could also cover the quieter team: field tilt, which awaits an owner-set minimum, and the involvement or chances prototypes from probe 01. Burst was chosen because it is already a roadmap candidate, needs no pending owner definition such as box entries, and uses only `known_at_event` fields.
- Thresholds were chosen on development data using sparsity, coverage, and the reference. None of these is a fan judgment.

Confidence: **0.97** in the reported counts for these pinned files. **0.9** that a side-shift-only packet would give an unrepresentative, one-sided basis for the gate. **0.7** that S = 4, R = 3 is a reasonable initial default (the sweep supports it, but sparsity preference belongs to the owner). **Not assessed** for fan usefulness. These are analytical confidence scores, not calibrated probabilities.

## Owner judgment

Preliminary comment from Kassahun (2026-09-28, in chat, before seeing any burst card). This is not the packet judgment:

- A considerably higher or lower number of shots is probably obvious, or called out by the broadcasters, so it may not be worth showing.
- It might be useful if a spell is especially high or low **relative to other matches**, though they were unsure.
- "More shots in the final" (period) might be useful.
- During play, they picture a small light-bulb indicator that opens to something insightful (tactics, coaches, or something people have not noticed), with cards available after the match.

The packet now asks directly whether the broadcast would already have said each card ([probe 02](probe-02.md)). The formal judgment remains pending.

## Decision

**Add the attacking burst detector as the second Phase 2 card type**, with initial defaults S = 4 shots and R = 3, specified in [phase-2-attacking-burst.md](../specs/phase-2-attacking-burst.md). It ships with firing, quiet, suppression, penalty, period, and threshold-boundary tests, a property-based prefix-invariance test, and a real-match golden snapshot with an independent raw recomputation. `regista replay` now shows both card types in one stream.

Do not add a third detector before the owner judges this stream. Given the owner's preliminary doubt, the burst detector is a candidate under test, not a settled card type. If the packet confirms that bursts are obvious from the broadcast, the next development-only step is the owner's "relative to other matches" variant: compare a spell with the distribution of 10-minute spells in matches that kicked off earlier (the `team_window_distributions` design in the Phase 2 specification), never the current match's full file.

Data: StatsBomb
