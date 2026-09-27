# Increment 2: Domain geometry

Last updated: 2026-09-27

This increment introduces Regista's first domain values: nominal IDs, points,
and a pitch with distance and angle calculations.

## Verified data contract

The local sparse checkout of StatsBomb open data contains:

- the complete open-data specifications;
- the competition catalog and La Liga 2020/21 match index;
- events and lineups for match `3773497`.

The specification's location diagram defines a 120 by 80 pitch. The acting
team's opponent goal is centered at `(120, 40)`. The real Clásico fixture
confirms that both teams remain in that attacking frame rather than switching
orientation:

| Team | Shots | Mean shot x |
| --- | ---: | ---: |
| Barcelona | 18 | 105.57 |
| Real Madrid | 14 | 103.01 |

The contract test recomputes this from the real event file independently for
each team in each half. It asserts that every group of shots is on the pitch
and averages beyond `x=100`, proving there is no half-time flip. If provider
data is not installed locally, the contract test skips with setup guidance;
unit tests remain self-contained and never access the network.

The empirical plot required by Phase 0 is reproducible without adding a
plotting library:

```console
uv run python scripts/plot_shot_locations.py \
  data/statsbomb/data/events/3773497.json \
  docs/assets/3773497-shot-locations.svg
```

The rendered plot was visually inspected. All 32 shots cluster in the attacking
quarter near `x=120`, with markers from both teams and both halves occupying the
same orientation.

The plotter and contract test intentionally read a very small view of the raw
event schema directly. Increment 3 introduced the real provider adapter, but
these two keep their own view on purpose: a contract test that checks the
provider's coordinates should not depend on the adapter whose assumptions it
is checking.

## Value objects and entities

`Point` and `Pitch` are frozen value objects. Two points with the same
coordinates mean the same thing; neither has a lifecycle or identity. Freezing
them lets code safely share instances without wondering whether another part of
the pipeline changed their values.

A future match is different. `MatchId(3773497)` identifies the same match even
as the match moves from scheduled to completed or gains calculated ratings.
That makes the match an entity. `MatchId`, `PlayerId`, and `TeamId` use
`NewType` so the type checker rejects accidentally passing one kind of integer
where another is required without adding runtime wrapper objects.

## Geometry semantics

`distance_to_opponent_goal` is Euclidean distance to `(length, width / 2)`.

`angle_to_opponent_goal` is the unsigned deviation between the forward pitch
axis and the line to the goal center. It is zero on the center line and grows
symmetrically toward either touchline, up to `pi / 2`. It is not the opening
angle subtended by the two goalposts; that would answer a different question
and should receive a distinct method if the learned valuation model needs it.

Both calculations reject off-pitch points. That turns a provider or
normalization error into an explicit failure instead of letting invalid
coordinates quietly influence action values.
