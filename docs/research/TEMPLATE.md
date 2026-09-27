# Research note: <short title>

Last updated: YYYY-MM-DD

Copy this file to `docs/research/<number>-<short-name>.md` for each question. Keep it short. A note that ends in "drop this idea" is as valuable as one that ends in a detector.

## Question
The fan question in one sentence, and why a fan would care.

## Definitions
Exact metric definitions, with their `definition_version` where one exists. Link locked definitions in AGENTS.md instead of restating them.

## Data
- Matches: which ones, and how many.
- Split bucket: development only (see AGENTS.md leakage rules).
- Provider source commit and ingest run, or how the files were fetched.
- Code version: the git commit, plus uncommitted changes if any.

## Method
The queries or scripts used (paths or inline SQL), so the result can be reproduced.

Point-in-time check: list every field used, with its availability (`known_at_event`, `delayed`, or `hindsight`; see the Phase 2 specification). A candidate observation shown during a match may use only the first two.

## Results
- Sample size, exclusions, and coverage limitations (for example, single-team seasons).
- The numbers, with their denominators.
- Overlapping windows are not independent observations. Say so wherever it matters.

## Counterexamples and alternative interpretations
Cases where the pattern fails, and other explanations for it. "It preceded shots" shows neither cause nor usefulness to a fan.

## Owner judgment
Kassahun's judgment of fan usefulness. Agents leave this section empty.

For each observation shown during a probe or review, record:

| Match, time | Observation | Correct? | Timely? | Added understanding? | Attention cost | Repetitive? | Keep or drop | Better at halftime or after? | Notes |
|---|---|---|---|---|---|---|---|---|---|

## Decision
One of: change a detector (which one, and how), drop the idea, or investigate further (what next). Give the reason.
