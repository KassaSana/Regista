"""Invariants of Regista's provider-independent event model."""

from dataclasses import FrozenInstanceError

import pytest

from regista.domain.events import ActionType, BallMovement, Event, MatchClock, Team
from regista.domain.geometry import Point
from regista.domain.ids import EventId, MatchId, TeamId

TEAM = Team(identifier=TeamId(1), name="Home")
CLOCK = MatchClock(period=1, minute=10, second=30)
MOVEMENT = BallMovement(
    start=Point(x=70.0, y=20.0),
    end=Point(x=85.0, y=15.0),
    completed=True,
    open_play=True,
)


def make_event(action: ActionType, movement: BallMovement | None) -> Event:
    return Event(
        identifier=EventId("event-1"),
        sequence=1,
        match_id=MatchId(1),
        clock=CLOCK,
        team=TEAM,
        action=action,
        location=Point(x=70.0, y=20.0),
        movement=movement,
        source="Synthetic",
        provider_record={},
    )


def test_pass_and_carry_carry_a_ball_movement() -> None:
    for action in (ActionType.PASS, ActionType.CARRY):
        assert make_event(action, MOVEMENT).movement == MOVEMENT


def test_ball_moving_action_without_movement_is_rejected() -> None:
    with pytest.raises(ValueError, match="needs a ball movement"):
        make_event(ActionType.PASS, None)


def test_other_action_with_movement_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot have a ball movement"):
        make_event(ActionType.OTHER, MOVEMENT)


def test_events_are_immutable() -> None:
    event = make_event(ActionType.CARRY, MOVEMENT)

    with pytest.raises(FrozenInstanceError):
        event.sequence = 2  # type: ignore[misc]


def test_provider_record_does_not_affect_equality() -> None:
    first = make_event(ActionType.OTHER, None)
    second = Event(
        identifier=first.identifier,
        sequence=first.sequence,
        match_id=first.match_id,
        clock=first.clock,
        team=first.team,
        action=first.action,
        location=first.location,
        movement=first.movement,
        source=first.source,
        provider_record={"extra": "provider detail"},
    )

    assert first == second


def test_clock_counts_seconds_on_the_continuous_provider_clock() -> None:
    assert MatchClock(period=2, minute=47, second=5).elapsed_seconds == 47 * 60 + 5


@pytest.mark.parametrize(
    ("period", "minute", "second"),
    [(0, 10, 0), (1, -1, 0), (1, 10, 60), (1, 10, -1)],
)
def test_clock_rejects_impossible_values(period: int, minute: int, second: int) -> None:
    with pytest.raises(ValueError):
        MatchClock(period=period, minute=minute, second=second)
