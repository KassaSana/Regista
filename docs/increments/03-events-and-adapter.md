# Increment 3 (Phase 1, step B): Events and the StatsBomb adapter

Last updated: 2026-09-27

This increment gives Regista its own event type and the adapter that translates
StatsBomb event files into it. Nothing detects insights yet; the goal is a
trustworthy event stream for the replay engine in step C (increment 4).

## The event model

`regista.domain.events` defines:

| Type | Meaning |
|---|---|
| `ActionType` | `PASS`, `CARRY`, or `OTHER`. Only the actions Phase 1 reasons about get their own value. |
| `MatchClock` | Period, minute, and second as the provider records them. |
| `Team` | Identifier plus display name, so templates can name the team. |
| `BallMovement` | Start, end, `completed`, and `open_play` for a pass or carry. |
| `Event` | Identifier, provider `sequence`, match, clock, team, action, optional location, optional ball movement, `source` (the data source the event came from, so insights can cite it), and the original provider record. |

### Why a nested ball movement instead of optional fields

A wide record with `end_location: Point | None` and `completed: bool` lets
nonsense exist: a tackle with an end location, or a "completed" shot. Grouping
the fields that only make sense together into `BallMovement`, and requiring it
exactly when the action is a pass or carry, makes those states impossible to
construct. `Event.__post_init__` enforces the rule and the unit tests pin it.

### What is deliberately missing

There is no player field, possession, or shot detail. The roadmap's minimal
event for Phase 1 needs identity and ordering, team, period and time, action,
start and end location, and completion. Players arrive with the involvement
detector. Everything else is still reachable through `provider_record`, which
is excluded from equality so it can never influence domain logic by accident.

### Ordering and time

`sequence` (StatsBomb's `index`) is the replay order. Timestamps restart and
can move backwards within the file, so they must never order events.
`MatchClock.minute` runs continuously across periods, so first-half stoppage
time overlaps the start of the second half; every time calculation must carry
the period as well.

## The adapter

`regista.adapters.statsbomb.events` is the anti-corruption layer: StatsBomb's
names and nesting stop there.

- **Completion:** a pass is completed when its record has no `outcome`. Any
  outcome, including "Unknown", means not completed: Regista never claims a
  completion the provider cannot confirm (match 3773497 has 4 "Unknown"
  passes). The contract test pins the observed outcome names. Carries never
  record an outcome and count as completed.
- **Open play:** decided per event from `pass.type`. Corner, Free Kick,
  Throw-in, Goal Kick, and Kick Off are set pieces; Recovery and Interception
  are open play; a pass with no type is a regular open-play pass. Any other
  type raises `StatsBombFormatError`, so a provider change forces an explicit
  decision instead of silently counting a new restart as open play.
- **Validation:** fields are checked by hand (strings, integers that are not
  booleans, two-number coordinates). Malformed data fails at the boundary with
  a message naming the field.
- **Ordering:** events are sorted by `index`, and a repeated `index` raises
  `StatsBombFormatError`, because replay order must be unambiguous.
- **Original record:** kept as a read-only mapping on every event (read-only
  at the top level; the domain never reads it).

On match 3773497, all 3,991 events normalize: 1,103 passes, 971 carries, and
1,917 other events.

## Enforcing the dependency rule

`tests/test_architecture.py` parses every domain module and fails if it imports
anything other than the standard library or `regista.domain`. Relative imports
count as violations, and the test fails if it finds no files, so it cannot pass
vacuously when run from another directory. The ports and adapters rule in
AGENTS.md is now checked on every test run, not just by review. Increment 4
extends the same check to detectors and templates.

## Tests

- `tests/unit/domain/test_events.py`: movement invariants, immutability, and
  clock validation.
- `tests/unit/adapters/test_statsbomb_normalizer.py`: completion, open play,
  set pieces, carries, other events, malformed input, "Unknown" outcomes,
  ordering, and repeated indexes, all on synthetic hand-built records (no
  provider data is copied).
- `tests/contract/test_statsbomb_event_contract.py`: the real match normalizes
  in strict order, pass outcomes only ever mean not completed, carries never
  record an outcome, and low y is the acting team's left
  (`test_low_y_is_the_acting_teams_left`: starting full-backs and wing-backs
  average y below 80/3 on the left and above 160/3 on the right in the first
  40 minutes).

Contract tests locate the data from the repository root, so they run the same
way from any working directory.
