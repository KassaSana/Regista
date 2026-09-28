# Research note: Score against chance quality (candidate card)

Last updated: 2026-09-28

## Question

Can Regista say, at the moment it becomes true, that the scoreline does not reflect the difference in chance quality so far? How often would it fire, and how often would it say something the broadcast's shot count does not already suggest? This follows the owner's product direction and the sizing in [research note 16](16-chance-quality-direction.md). **No detector is added in this note.**

## Definitions

- **Chance quality:** a team's cumulative **non-penalty** provider xG (StatsBomb's `shot.statsbomb_xg`), summed over its shots so far. Penalties are excluded because one penalty alone is worth about 0.76.
- **Score:** goals so far, from shot outcomes marked Goal plus "Own Goal For" events. Penalty shootouts are excluded.
- **Candidate:** after each shot or own goal, a team's chance quality exceeds its opponent's by at least a margin `M`, while that team is not ahead. It fires at most **once per team per score state**, so a new card needs a goal to change the score first.
- **Obviousness proxies** (not judgments):
  - *comparable volume:* the team's non-penalty shots are at most 1.25 times its opponent's;
  - *better per shot:* its xG per shot is at least 1.5 times its opponent's.

  Comparable volume marks the cases where the shot count shown on a broadcast would not suggest the difference.

## Data

- All 800 acquired development matches. Each raw file was checked against its manifest SHA-256. No exclusions. No validation or test file was opened.
- StatsBomb Open Data commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.
- Code: repository commit `c8133f6` plus uncommitted increment 19 work and `scripts/research/phase2_chance_quality.py`. Output is kept locally in ignored `out/research/phase2-chance-quality.json`. A second run was byte-identical.

## Method

```console
cd scripts/research
uv run python phase2_chance_quality.py
```

The script replays each match in provider order and reads only events at or before the current one.

**Validation:** the reconstructed final score equals the provider's final score (`normalized.matches`) in all 800 matches.

**Point-in-time:**
- shot, shot type, and outcome: `known_at_event`;
- own-goal events: `known_at_event`;
- provider xG: `delayed`. A live card would appear once the provider's xG arrives, not at the shot itself.

No `hindsight` field is used. Provider xG comes from StatsBomb's model, which Regista did not train or tune.

## Results

| Margin M | Candidates | Matches with one | Trailing / level | Median minute | First half | Comparable volume | Better per shot | One shot > half the xG |
|---:|---:|---:|---|---:|---:|---:|---:|---:|
| 0.75 | 295 | 215 (27%) | 83 / 212 | 61 | 90 | 33 | 171 | 48 |
| **1.0** | **166** | **122 (15%)** | **51 / 115** | **68** | **30** | **12** | **105** | **19** |
| 1.25 | 97 | 71 (9%) | 33 / 64 | 71 | 13 | 1 | 59 | 7 |
| 1.5 | 51 | 42 (5%) | 17 / 34 | 79 | 4 | 0 | 32 | 4 |

At M = 1.0:
- **Volume:** 90 matches have one candidate, 21 have two, 10 have three, and 1 has four.
- **Penalties:** including them would leave 142 of the 166 still at the margin, so excluding them changes about one card in seven.
- **Clearly non-obvious cases:** the better-chance team had no more shots than its opponent in only 4 of 166 candidates, and comparable volume in 12.

Examples at M = 1.0, with comparable shot counts and no single chance dominating (development matches):

| Match | Time | Team (score) | Non-penalty xG | Shots |
|---|---|---|---|---|
| 3754013 | 61:57 | Chelsea (0–2 v Leicester City) | 1.51 to 0.40 | 6 to 6 |
| 3878552 | 86:18 | Inter Milan (1–1 v Carpi) | 1.89 to 0.73 | 10 to 10 |
| 3879743 | 89:29 | Udinese (0–1 v Bologna) | 1.73 to 0.66 | 10 to 11 |

A card in the owner's wording could read (template not yet written):

> Chelsea trail 0–2, but have created the better chances: 1.51 expected goals to 0.40, from 6 shots each (StatsBomb's chance-quality model, penalties excluded).

## Counterexamples and alternative interpretations

- **Most candidates are also volume stories.** In 162 of 166, the better-chance team also has more shots, often far more. A fan who sees the shot count already senses domination. The added value is the contrast with the score, and in 105 of 166 cases the better quality per shot. Only a dozen are the pure "quality not volume" case.
- **Game state.** A leading team that sits back concedes shots and often concedes chance quality. That explains part of the disagreement without any "misleading" score. A card must not imply the leader is lucky.
- **One big chance.** In 19 of 166, a single chance is over half the team's xG, so the "better chances" rest largely on one miss.
- **Timing.** The median candidate fires at 68 minutes; only 30 fire in the first half. That fits the owner's preference for breaks and after-match reading better than live alerts. A halftime or full-time summary version is the natural variant: note 16 counts 15 matches at halftime and 76 at full time with a gap of at least 1.0 xG.
- **Model dependence.** Another provider's xG would move these numbers. The card must name its model; agreement between providers would check the model, not fan usefulness.

Confidence: **0.97** in the counts and the score reconstruction for these pinned files. **0.85** that M = 1.0 gives a sparse card (122 of 800 matches). **0.6** that it passes the owner's "not obvious from the broadcast" test, given that most cases also show a shot-count advantage. **Not assessed** for fan usefulness. These are analytical confidence scores, not calibrated probabilities.

## Owner judgment

<!-- Pending. Suggested check: judge the three examples above and three volume-dominated candidates, for example as a small packet. Agents do not infer usefulness. -->

## Decision

**Investigate further. Do not add a detector yet.** Next, on development data only:
1. Build a small judging packet of about 8 candidates at M = 1.0, mixing comparable-volume and volume-dominated cases, shown at breaks and at full time. This tests whether the contrast with the score is the insight, or only the quality-over-volume subset is. (Done as [probe 03](probe-03.md): a pre-registered 12-example packet across four categories.)
2. If the owner values it, specify the detector in the Phase 2 detector format: carry provider xG and the goal outcome on `ShotDetail`, add a template naming the model, and write firing, quiet, and suppression tests. Freeze the margin before any validation comparison.

Data: StatsBomb
