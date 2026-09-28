# Research note: Probe 03 (what chance quality reveals beyond the score)

Last updated: 2026-09-28

**Status: packet `f24cfbf787c2` generated under the pre-registered rules; owner judgment pending.** The sampling rules below were written before any example was generated or viewed.

## Question
When does chance-quality information reveal something the scoreline, the broadcast, and a basic shot count would not already make obvious? [Research note 17](17-score-against-chance-quality.md) found that in 162 of 166 candidates the better-chance team also had more shots. This probe separates that obvious case from the cases the owner finds most promising.

## Definitions
- **Candidate pool:** the exact rule of research note 17. After each shot or own goal, a team's cumulative non-penalty provider xG exceeds its opponent's by at least **M = 1.0**, while that team is not ahead. It fires at most once per team per score state, and shootouts are excluded. Development matches only.
- **Shot ratio:** the team's non-penalty shots divided by its opponent's, at the candidate moment.
- **Categories**, mutually exclusive and assigned in this order:
  1. **D, finishing or goalkeeping distorts the score:** the candidate team is trailing, and the leading team's non-penalty goals exceed its non-penalty xG by at least 1.0.
  2. **C, one dominant chance:** the candidate team's largest single non-penalty chance is more than 50% of its non-penalty xG.
  3. **B, similar volume, different quality:** the shot ratio is between 0.8 and 1.25 inclusive.
  4. **A, more shots and better chances (baseline):** the shot ratio is at least 1.5.

  Candidates in no category (ratio between 1.25 and 1.5, or below 0.8) are counted, not sampled.

## Sampling (pre-registered, 2026-09-28)
- **Seed:** `2026092803`.
- **Excluded matches:**
  - the four already-inspected matches (`catalog/corpus.toml`);
  - the five probe 02 matches (3754020, 3879570, 3773656, 3939984, 3920416);
  - the three examples named in research note 17 (3754013, 3878552, 3879743).
- **Draw, in the order D, C, B, A:**
  - list the eligible matches that have a candidate in the category and were not used by an earlier category;
  - shuffle them with the seed;
  - take the first three;
  - from each, use the earliest candidate of that category.
- **Fallback:** if fewer than three matches qualify at M = 1.0, fill the category from the M = 0.75 pool under the same rules and label those examples as such. There is no other fallback.
- **Display order:** the twelve examples are shuffled with the same seed. Category labels are hidden from the judge and recorded only in `selection.json`.
- Nothing is re-drawn after viewing. No threshold changes because of which examples look good.

## Data
- Development matches only; no validation or test file is opened.
- StatsBomb Open Data commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.
- Code: repository commit `c8133f6` plus the uncommitted increment 19 work, `scripts/research/phase2_chance_quality.py`, and `scripts/research/phase2_chance_quality_packet.py`.

## Method
```console
cd scripts/research
uv run python phase2_chance_quality_packet.py
```
This writes `out/phase2-chance-quality/packet.html` and `selection.json` (git-ignored).

Each example shows only what was known at that moment:
- the match, clock, and score at that moment;
- non-penalty shots, cumulative non-penalty xG, xG per shot, and non-penalty goals, for each team;
- penalties **separately** (count, goals, xG);
- a strip of every chance's value from 0 to 1 xG, with its outcome;
- the sorted chance values;
- a shot map in each team's attacking frame;
- a neutral draft sentence.

Point-in-time: shots and their outcomes are `known_at_event`; provider xG is `delayed`.

The judge answers for each example:
1. Is the statement factually supported by what is shown?
2. Is it interesting?
3. Would you have understood this from the score and basic shot count alone?
4. When would it be most useful: live, at halftime or a stoppage, after the match, or not at all?
5. Does one chance or a penalty make the summary misleading?

## Results
Generation, before any judgment:
- **Pool at M = 1.0 after exclusions:** 161 candidates. By category: A 120, C 17, D 17, **B 5**, uncategorized 2.
  - The pure "similar volume, different quality" case is rare: 5 candidates in the whole development pool.
  - Every category filled at M = 1.0, so the fallback was not used.
- **Packet `f24cfbf787c2`:** 12 examples, 3 per category, in shuffled order. The mapping from example to category is in `out/phase2-chance-quality/selection.json`; read it only after judging.
- **Checks:**
  - Each example's score, non-penalty xG, and shot counts were rebuilt from events up to the candidate moment, and the script asserted they equal the note 17 candidate.
  - Two runs gave an identical selection.
  - Penalties are shown separately; 2 examples contain them.
  - In the browser: 12 examples, 24 strips, and 24 shot maps rendered, and export works.
  - In the app's preview pane the page cannot save answers, and it now says so.

Owner answers: pending.

## Owner judgment
<!-- Pending. Transfer the exported answers verbatim. Agents do not infer judgments. -->

## Decision
Pending. No detector is built before this judgment.

Data: StatsBomb
