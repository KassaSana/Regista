"""Prefix invariance: cards up to a replay position never depend on later events."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from hypothesis import event as note_event
from hypothesis import given, settings
from hypothesis import strategies as st
from synthetic_events import AWAY, HOME, EventStream

from regista.detectors.attacking_side_shift import AttackingSideShiftDetector, SideShiftSettings
from regista.domain.entries import Channel
from regista.domain.events import ActionType, BallMovement, Event, Team
from regista.domain.geometry import Point
from regista.domain.insights import AttackingSideShift
from regista.domain.replay import replay

# Low thresholds so random streams actually produce cards.
EAGER = SideShiftSettings(
    window_seconds=300,
    minimum_recent_entries=3,
    minimum_baseline_entries=3,
    minimum_share_increase=Fraction(1, 4),
    cooldown_seconds=180,
)
PERIOD_STARTS = {1: 0, 2: 45 * 60}
PERIOD_LENGTH_SECONDS = 48 * 60

event_specifications = st.tuples(
    st.sampled_from([1, 2]),  # period
    st.integers(0, PERIOD_LENGTH_SECONDS - 1),  # seconds into the period
    st.sampled_from([HOME, AWAY]),
    st.sampled_from(list(Channel)),
    st.sampled_from([ActionType.PASS, ActionType.CARRY, ActionType.OTHER]),
)
mutations = st.tuples(
    st.sampled_from([HOME, AWAY]),
    st.floats(0.0, 80.0),
    st.booleans(),  # completed
    st.booleans(),  # open play
)


def build_stream(
    specifications: list[tuple[int, int, Team, Channel, ActionType]],
) -> list[Event]:
    stream = EventStream()
    ordered = sorted(specifications, key=lambda item: (item[0], item[1]))
    for period in (1, 2):
        stream.other(HOME, period, *divmod(PERIOD_STARTS[period], 60))
        for spec_period, offset, team, channel, action in ordered:
            if spec_period != period:
                continue
            minute, second = divmod(PERIOD_STARTS[period] + offset, 60)
            if action is ActionType.OTHER:
                stream.other(team, period, minute, second)
            else:
                stream.entry(team, period, minute, second, channel, action=action)
    return stream.events


def mutate(event: Event, mutation: tuple[Team, float, bool, bool]) -> Event:
    """Change what happened while keeping the event's place in the replay."""
    team, end_y, completed, open_play = mutation
    movement = event.movement
    if movement is not None:
        movement = BallMovement(
            start=movement.start,
            end=Point(x=movement.end.x, y=end_y),
            completed=completed,
            open_play=open_play,
        )
    return replace(event, team=team, movement=movement)


def cards_up_to(events: list[Event], cut: int) -> list[AttackingSideShift]:
    """Replay everything, keeping cards triggered by the first ``cut`` events."""
    early_identifiers = {event.identifier for event in events[:cut]}
    return [
        card
        for card in replay(events, AttackingSideShiftDetector(EAGER))
        if card.trigger_event_id in early_identifiers
    ]


@settings(max_examples=200, deadline=None)
@given(data=st.data())
def test_cards_before_a_cut_ignore_every_later_event(data: st.DataObject) -> None:
    events = build_stream(data.draw(st.lists(event_specifications, min_size=60, max_size=200)))
    cut = data.draw(st.integers(0, len(events)))
    altered = events[:cut] + [mutate(event, data.draw(mutations)) for event in events[cut:]]

    original = cards_up_to(events, cut)
    note_event(f"cards before the cut: {'some' if original else 'none'}")

    assert cards_up_to(altered, cut) == original
    assert list(replay(events[:cut], AttackingSideShiftDetector(EAGER))) == original
