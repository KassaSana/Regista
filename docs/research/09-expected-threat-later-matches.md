# Research note: Expected threat on later development matches

Last updated: 2026-09-28

## Question

Does an expected-threat surface fitted on earlier development matches rank a
completed move's location before a subsequent shot or goal better than a
transparent distance-to-goal heuristic? This tests one retrospective spatial
proxy; it does not test whether a dangerous-spell card helps a fan.

## Definitions

The two scores are the learned expected-threat value and normalized
goal-distance value **at the end location** of a completed open-play pass or
carry. They are compared as rankings, so their different units do not affect
area under the receiver-operating curve (AUC). Each target is whether the same
team takes an open-play shot, or scores from one, later in the provider's same
possession. Ties receive average ranks. AUC of 0.5 is chance ranking.

The same-possession target uses hindsight possession grouping only for
evaluation. Neither valuer reads that grouping or future shots at replay time.
This evaluation does not compare the action-value *change* (end minus start),
which is the quantity a dangerous-spell detector might accumulate.

## Data

- Development split version 1 only. The 16-by-12 surface trained on 673 matches
  dated before 2023-01-01, from warehouse run `72e2ced0e72fc4eb` and source
  commit `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.
- Evaluation: 127 later development matches (2023–2024), from five
  competition-seasons. No match used for this evaluation entered the surface
  fitting query.
- Code: `scripts/research/train_expected_threat.py` at commit `acd7e2e`
  and `scripts/research/evaluate_expected_threat.py` in this increment.
- No validation or test match was opened.

## Method

```console
uv run python scripts/research/train_expected_threat.py --before-date 2023-01-01 --output out/valuation/expected-threat-before-2023.json
uv run python scripts/research/evaluate_expected_threat.py
```

The evaluator refuses an undated surface. It reads only the development
warehouse, joins normalized events to retrospective possession identifiers,
finds later same-possession open-play shots and goals, and calculates AUC for
both location scores. For each match with both outcomes present, it also
calculates the paired AUC difference. The training date is strictly earlier
than every evaluated match date. The model JSON is git-ignored; its SHA-256 was
`a9bae153f38ebcf3fc5fcf966d2525d86d2f85080bd29d46b44f84a58ae3db3`.

Point-in-time check: start and end location, pass/carry type, completion, and
open-play status are known at the event or shortly after it. The model's
training counts are from earlier match dates. Provider possession grouping and
later shots or goals are retrospective outcome labels only. The provider's
historical publication timestamps have not been verified against each target
kickoff, so this is an out-of-training research test, not a live deployment
claim.

## Results

There are 194,503 eligible completed moves in the 127 later matches. A later
same-possession open-play shot follows 31,510 moves; a goal follows 3,282.
Multiple moves in one possession can share the same outcome.

| Target | Expected-threat end AUC | Goal-distance end AUC | Match comparison |
|---|---:|---:|---|
| Later shot | 0.6632 | 0.6650 | Expected threat higher in 45 of 127 matches; goal distance higher in 82; median paired difference −0.00184 |
| Later goal | 0.6458 | 0.6464 | Expected threat higher in 57 of 106 evaluable matches; goal distance higher in 48; one tie; median paired difference +0.00089 |

The pooled difference is small and favors the heuristic for both targets.
Match-level goal results are mixed. These results do not show an improvement
from the learned surface on this proxy.

## Counterexamples and alternative interpretations

- AUC for the end location measures spatial ranking after a completed move,
  not the value added by that move or precision of a spell card.
- Goals are rare; 21 matches lack both outcome classes and cannot contribute
  to the within-match goal comparison.
- Moves within a possession share targets and are not independent. The pooled
  AUC gives long possessions and high-event matches more weight. Match-level
  counts show the direction varies.
- The later sample draws from only five competition-seasons and is not a
  general football benchmark. Historical provider records may have been
  published after match kickoff.
- The heuristic may work well because distance to goal already captures much
  spatial signal. The learned grid may still differ usefully for lateral moves,
  but this test does not establish where either is right for a fan.

## Confidence

These are judgmental evidence scores, not calibrated probabilities.

- **0.9:** the date cutoff excludes evaluation matches from fitting and the
  calculations reproduce from the development warehouse.
- **0.75:** the learned grid gives no material ranking improvement on this
  specific end-location proxy in the later development sample. The paired
  match directions and small pooled differences support that narrow result.
- **Not assessed:** action-gain quality, dangerous-spell card precision,
  explorer usefulness, live deployability, or fan value.

## Owner judgment

Pending. No subjective usefulness judgment is inferred from the AUC result.

## Decision

Do not promote the learned surface into a card detector on this evidence.
Next compare action-value changes on development-only spell outcomes and inspect
specific disagreements. A player explorer could still be worthwhile if it
answers questions that aggregate cards cannot, but that remains unjudged.
