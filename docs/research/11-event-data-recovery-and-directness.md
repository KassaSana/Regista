# Research note: Event-data recovery location and movement directness

Last updated: 2026-09-28

## Question

Do the development events support precise, reproducible recovery-location and
directness measures that can precede Phase 6 positional experiments? These
measures describe ball actions, not defensive-line position or tactical intent.

## Definitions

For each team-match in periods 1–4:

- **Recovery location:** median attacking-frame x of valid `Ball Recovery`
  events. The attacking-third recovery share counts such events at x ≥ 80
  divided by all valid `Ball Recovery` events. Interceptions are not silently
  merged with recoveries.
- **Movement directness:** `100 × Σ max(end_x − start_x, 0) / Σ Euclidean
  movement distance`, using completed open-play passes and carries with valid
  pitch coordinates. It is bounded from zero to 100. Backward and lateral
  movements add path length but no positive x gain. This is a path-shape ratio,
  not speed, possession directness, threat, or an overall style label.
- **Research coverage rule:** at least ten valid recoveries and 100 valid
  movements for a team-match. This is not a detector threshold.

The locked open-play and completion definitions in [AGENTS.md](../../AGENTS.md)
apply. `analytical.event_context` supplies the normalized attacking frame.

## Data

- 800 development matches, 1,600 team-matches; split version 1 only.
- Warehouse ingest run `72e2ced0e72fc4eb`, built from commit `1aa2425a66cf`.
- StatsBomb Open Data source commit
  `b0bc9f22dd77c206ddedc1d742893b3bbe64baec`.
- Research code: `scripts/research/phase6_event_metrics.py`, on repository
  commit `80bbed5` plus this increment's uncommitted script.
- No validation or test data was opened.

## Method

Run `uv run python scripts/research/phase6_event_metrics.py`. The script uses
the read-only development warehouse connection, joins the existing team-match
spine to period 1–4 events, checks pitch bounds, aggregates each team-match,
and prints rounded descriptive summaries. The full SQL and definitions are in
the script. No thresholds are tuned against outcomes.

Point-in-time check: a recovery's event location is known at the event; pass
completion and a carry's derived end location are known at or shortly after
the action. A completed whole-match aggregate is retrospective and cannot be
read by a detector during that same match. A future in-match version would
update incrementally from the prefix only. No possession grouping, provider
`play_pattern`, or later shot is an input to these two definitions.

## Results

All 1,600 team-matches met the research coverage rule. The query counted
80,963 `Ball Recovery` events and 1,182,493 completed open-play passes/carries
in periods 1–4. No selected recovery or movement was excluded for invalid
coordinates.

| Team-match measure | Minimum | Median | Maximum |
|---|---:|---:|---:|
| Median recovery x (0–120) | 20.35 | 50.50 | 85.60 |
| Attacking-third recovery share | 0.029 | 0.226 | 0.579 |
| Movement directness (0–100) | 30.53 | 43.34 | 63.63 |

These are distributions of 1,600 team-match aggregates, not event-level
distributions or confidence intervals. Team-matches from the same season and
team are dependent.

## Counterexamples and alternative interpretations

- A recovery at x ≥ 80 describes where a ball-recovery event was recorded. It
  does not locate the back line or prove a press; the other defenders may be
  anywhere. Defensive-line height requires positional frames.
- The directness numerator ignores backward progress, while the denominator
  includes it. A team with many sideways completed passes can score low even
  if its occasional attacks are very direct. Failed passes are excluded, so
  this metric does not capture the cost of ambitious attempts.
- Match state, opponents, possession opportunities, and the mix of passes and
  carries can change both measures. The corpus overrepresents two 2015/16
  leagues, with later single-team and tournament samples; these ranges are not
  league norms or timeless tactical benchmarks.
- A full-match measure may hide meaningful short spells. No fan-facing
  timeliness or repeatability test has been done.

## Confidence

These are judgmental evidence scores, not calibrated probabilities.

- **0.9:** the two measures and coverage counts are reproducible from the
  development warehouse under the stated event and coordinate filters.
- **0.7:** the distributions show real variation in recorded ball-action
  locations and paths across this corpus; provider coding and match mix limit
  interpretation.
- **Not assessed:** tactical causality, defensive-line height, card usefulness,
  or whether a short-window detector would be stable and timely.

## Owner judgment

Pending. No tactical or fan-usefulness judgment is inferred.

## Decision

Keep these as precisely defined event-data descriptors for future comparison
with positional samples. Do not turn them into a defensive-line or pressing
card. Next inspect half-to-half or short-window stability on development
matches, and compare positional frames when a legal sample is available.
