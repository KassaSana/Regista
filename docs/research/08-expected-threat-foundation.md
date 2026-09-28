# Research note: Expected-threat foundation

Last updated: 2026-09-28

## Question

Can a transparent action-value baseline and a learned expected-threat surface share
one replay contract, and does our expected-threat equation agree with an
independent implementation on identical inputs? This is a foundation for a
possible dangerous-spell trigger and player explorer, not evidence of fan value.

## Definitions

The heuristic gives each location one minus its normalized Euclidean distance
to the opponent goal center. A completed open-play pass or carry receives end
value minus start value. This is a geometric score, not a goal probability.

Expected threat uses a 16-column, 12-row attacking-frame pitch grid. For cell
`i`, the value is `goals_i / (shots_i + moves_i)` plus the sum, over destination
cells `j`, of `completed_moves_ij / (shots_i + moves_i) * value_j`. Failed moves
remain in the denominator and create no successful transition. Iteration starts
at zero and stops when the maximum change is at most `1e-8`, with a 500-iteration
limit. An action receives destination minus origin cell value only when it is a
completed open-play pass or carry with on-pitch coordinates. Shots are training
rewards, not valued actions in this first interface. Values can be negative.

The equation follows the [original expected-threat explanation](https://karun.in/blog/expected-threat.html).
The independent comparison uses [socceraction's documented xT model](https://socceraction.readthedocs.io/en/latest/api/generated/socceraction.xthreat.ExpectedThreat.html)
and [implementation](https://github.com/ML-KULeuven/socceraction/blob/master/socceraction/xthreat.py).
Our open-play StatsBomb action selection differs from socceraction's SPADL
selection, so corpus grids are not compared cell for cell.

## Data

- Development split version 1 only: 800 normalized matches in warehouse run
  `72e2ced0e72fc4eb`, built from commit `1aa2425a66cf`.
- StatsBomb Open Data source commit
  `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.
- Code: repository commit `912a13d` plus the uncommitted Phase 4 files in this
  increment. The script SHA-256 is stored in the ignored output JSON.
- No validation or test event file or held-out warehouse was opened.

## Method

Run `uv run python scripts/research/train_expected_threat.py`. The script reads
only the development warehouse through its read-only research connection. The
SQL in that script selects period 1–4 open-play shots and pass/carry attempts
with valid start and end coordinates; successful moves supply transitions. It
writes a provenance record, counts, solver information, and grid to the ignored
`out/valuation/expected-threat.json`. The output SHA-256 on this checkout was
`096d75d996aafe5f7411ae5a4eadb71e41e29eccb04f7f0f6ab618f0255dd167`.

The script also accepts `--before-date 2023-01-01 --output
out/valuation/expected-threat-before-2023.json`. It restricts training to
matches dated strictly before the supplied date. On this corpus that selected
673 matches, 16,297 shots, and 1,113,180 move attempts; it converged in 83
iterations. The resulting grid SHA-256 was
`a9bae153f38ebcf3fc5fcf966d2525d86d2f85080bd29d46b44f84a58ae3db3`.
The remaining 127 development matches dated 2023 or 2024 are candidates for
out-of-training evaluation. A live-style deployment would also need to verify
that the training records were published before each target kickoff.

For an equation cross-check, two synthetic two-cell cases were run in a
throwaway Python 3.12 environment with `socceraction` and `multimethod<2`:
one missed shot and one successful move toward a certain-goal shot gives
`(0.5, 1.0)`; adding one failed move at the first cell gives `(1/3, 1.0)`.
Our synthetic tests reproduce both. The compatibility pin is only for the
throwaway comparison; the Regista project remains on Python 3.13.

Point-in-time check: action type, team, start/end locations, pass outcome, and
pass type are available at the action or shortly afterward. Goals are training
outcomes, never an input to an in-match action's value. The fitted surface is
fixed during replay. However, fitting on the full development corpus includes
the replayed match and its future events when valuing any of those same 800
matches. It is therefore **not valid for live-style evaluation on this corpus**.
A chronological training cutoff is now available. An out-of-training replay
evaluation and enforcement that a surface predates the target match are still
needed before a detector uses it or any precision claim is made.

## Results

- 19,255 eligible open-play shots, including 1,784 goals.
- 1,326,570 move attempts, of which 1,182,493 completed transitions.
- Zero shot or move attempts were excluded for coordinates by this query.
- Converged in 85 iterations with maximum residual below `1e-8`.
- Cell values range approximately from 0.0019 to 0.2743. These are fitted
  conditional values for this action selection, not calibrated match forecasts.
- The synthetic independent-equation comparisons agree. The full project suite
  and type/style checks are recorded in [increment 14](../increments/14-action-value-foundation.md).

## Counterexamples and alternative interpretations

- A forward movement can lose expected threat if it ends in a less useful cell.
  The heuristic and learned grid have different units; comparing raw sums or
  magnitudes would be misleading.
- Completed-move-only action ratings omit failed moves, shots, defensive work,
  and possession loss. They cannot yet support an overall player rating.
- The grid pools club and international matches from 2015–2024; two 2015/16
  leagues dominate the development corpus. It cannot establish contemporary
  calibration or individual-team baselines.
- The held-out evaluation and owner viewing probe are pending, so neither
  precision improvement nor fan usefulness has been shown.

## Confidence

These are judgmental evidence scores, not calibrated probabilities.

- **0.95:** the implemented equation agrees with socceraction on the two
  matched synthetic examples, including a failed-move denominator.
- **0.85:** the fitted grid is reproducible from the recorded development
  warehouse and specified filters.
- **Not assessed:** predictive quality, card precision, player-explorer value,
  and fan usefulness.

## Owner judgment

Pending. No fan-usefulness judgment is inferred from model fit or tests.

## Decision

Investigate further. Keep the full-development grid as a research artifact.
Next evaluate the chronological surface on later development matches and
enforce the training boundary when loading it for replay, before wiring it to
in-match cards or a player explorer.
