# Increment 4 (Phase 1, step C): Replay engine and the attacking-side shift detector

Last updated: 2026-09-27

This increment turns the event stream from increment 3 into cards. It adds the
replay engine, the attacking-side shift detector, the template that words its
findings, the cooldown, the prefix-invariance tests, and a golden snapshot of
the real match. The detector's rules live in
[the specification](../specs/phase-1-attacking-side-shift.md); this document
explains how the code is shaped and why.

## Running it

```console
uv run regista replay --match 3773497
```

Each card prints its period and provider clock, the sentence, and the
identifiers of its recent and baseline entries. A match with no cards prints
`No cards.`. Output always ends with `Data: StatsBomb`.

To check a card by hand, add `--evidence`:

```console
uv run regista replay --match 3773497 --evidence
```

Each card then shows a channel table (recent and baseline counts and shares,
and the change in points), every recent entry with its clock, action, start and
end coordinates, and channel, and the baseline broken down by period. The
wording lives in `regista.templates.render_evidence`.

## Where each piece lives

| Module | Role |
|---|---|
| `regista.domain.entries` | `Channel`, `channel_of`, `is_final_third_entry`: the locked definitions as code |
| `regista.domain.insights` | `ChannelCounts` and `AttackingSideShift`: what a detector found, as data, not prose |
| `regista.domain.replay` | `Detector` protocol and `replay`, which feeds events in strict `sequence` order |
| `regista.detectors.attacking_side_shift` | `SideShiftSettings` and the incremental detector |
| `regista.templates` | The sentence and the clock format |
| `regista.cli` | Wires the adapter, replay, detector, and template together |

Detectors decide and templates render. The detector returns counts, channels,
and event identifiers; only the template produces words, and it only restates
those numbers.

## Why the detector is incremental

A detector is an object with one method, `observe(event)`. It never receives
the whole match, only the next event. Because of that shape it cannot read the
future: an insight emitted at a replay position is built only from events at or
before it. The "baseline" is everything the detector has seen so far, never a
match-wide aggregate. The same object could later receive a live feed unchanged.

The detector checks every team on every event, not just the team that acted.
The recent window slides with the clock, so a team's shares can change while
the other team has the ball.

## Why exact fractions

Shares are `fractions.Fraction`, not floats. The firing rule compares an
increase against 25 percentage points. With floats, an increase of exactly one
quarter could land a hair below it and fail to fire. Exact arithmetic makes the
boundary behave as written, and the tests can assert it.

## Periods and the clock

StatsBomb's minute runs continuously across periods, so first-half stoppage time
(minute 45–47 of period 1) overlaps the start of the second half (minute 45 of
period 2). The detector therefore:

- keeps the recent window inside the current period;
- learns each period's start from the first event it sees in that period (the
  Half Start event), so nothing fires until 10 minutes into a period;
- clears the cooldown when a new period starts.

## Replay order

`replay` raises `ReplayOrderError` if a `sequence` does not strictly increase.
The StatsBomb adapter already sorts events and rejects repeated indexes; the
replay engine checks again so any future adapter gets the same guarantee.

## Sources and evidence

Every event carries a `source` (the StatsBomb adapter sets
`"StatsBomb Open Data"`). A card lists the identifiers of every recent and
baseline entry, the event at which it fired, and the distinct sources of its
supporting events. The channels that lost share appear as supporting evidence
(`channels_losing_share`), never as their own card.

## Tests

- `tests/unit/domain/test_entries.py`: channel boundaries at exactly 80/3 and
  160/3, and the x = 80 boundary for entries.
- `tests/unit/detectors/test_attacking_side_shift.py`: firing, quiet,
  suppression (including firing again once the cooldown ends), minimum counts,
  both period cases, set pieces, split increases, largest increase, tie order,
  and incomplete passes. All use hand-built events from `synthetic_events.py`.
- `tests/unit/detectors/test_prefix_invariance.py`: a Hypothesis property. It
  generates random two-team, two-period streams with low thresholds so cards
  fire, cuts the stream at a random position, and changes every later event.
  Cards triggered before the cut must stay identical, and they must equal the
  cards from replaying only the prefix.
- `tests/unit/domain/test_replay.py`, `tests/unit/test_templates.py`, and
  `tests/test_cli.py`: ordering errors, exact wording, and the command end to
  end on synthetic files.
- `tests/contract/test_attacking_side_shift_replay.py`: the golden snapshot,
  real-match prefix invariance, and `test_cards_match_an_independent_recomputation`,
  which recomputes the cards from the raw file with separate plain code (no
  adapter, domain, or detector imports) and requires an exact match. Every event from minute 60 of the second half
  is mirrored across the pitch, and the earlier cards must not change.

`tests/test_architecture.py` now also checks that detectors and templates import
only the standard library and the domain.

## The real match

With the initial defaults, match 3773497 produces two cards, both for Barcelona:
a shift to the center at 23:11 of the first half and a shift to the left at
55:03 of the second. The independent recomputation test reproduces both. The snapshot is at
`tests/golden/3773497-attacking-side-shift.json`. Its review is Kassahun's, and
it is pending. Real Madrid produces no card, as the specification's known
limitation predicts.
