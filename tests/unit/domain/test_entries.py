"""Final-third entry and channel definitions, including their exact boundaries."""

import pytest

from regista.domain.entries import Channel, channel_of, is_final_third_entry
from regista.domain.events import ActionType, BallMovement, Event, MatchClock, Team
from regista.domain.geometry import Point
from regista.domain.ids import EventId, MatchId, TeamId


def movement_event(
    action: ActionType,
    start_x: float,
    end_x: float,
    *,
    completed: bool = True,
    open_play: bool = True,
) -> Event:
    start = Point(x=start_x, y=40.0)
    return Event(
        identifier=EventId("event-1"),
        sequence=1,
        match_id=MatchId(1),
        clock=MatchClock(period=1, minute=10, second=0),
        team=Team(identifier=TeamId(1), name="Home"),
        action=action,
        location=start,
        movement=BallMovement(
            start=start, end=Point(x=end_x, y=40.0), completed=completed, open_play=open_play
        ),
        source="Synthetic",
        provider_record={},
    )


@pytest.mark.parametrize(
    ("y", "channel"),
    [
        (0.0, Channel.LEFT),
        (80 / 3 - 0.001, Channel.LEFT),
        (80 / 3, Channel.CENTER),
        (40.0, Channel.CENTER),
        (160 / 3, Channel.CENTER),
        (160 / 3 + 0.001, Channel.RIGHT),
        (80.0, Channel.RIGHT),
    ],
)
def test_channels_split_the_width_in_thirds_with_the_boundaries_in_the_center(
    y: float, channel: Channel
) -> None:
    assert channel_of(Point(x=90.0, y=y)) is channel


@pytest.mark.parametrize("action", [ActionType.PASS, ActionType.CARRY])
def test_a_completed_open_play_move_across_x_80_is_an_entry(action: ActionType) -> None:
    assert is_final_third_entry(movement_event(action, start_x=79.9, end_x=80.0))


def test_a_move_starting_at_x_80_is_already_in_the_final_third() -> None:
    assert not is_final_third_entry(movement_event(ActionType.PASS, start_x=80.0, end_x=95.0))


def test_a_move_ending_before_x_80_is_not_an_entry() -> None:
    assert not is_final_third_entry(movement_event(ActionType.PASS, start_x=60.0, end_x=79.9))


def test_an_incomplete_pass_is_not_an_entry() -> None:
    event = movement_event(ActionType.PASS, start_x=70.0, end_x=85.0, completed=False)

    assert not is_final_third_entry(event)


def test_a_set_piece_pass_is_not_an_entry() -> None:
    event = movement_event(ActionType.PASS, start_x=70.0, end_x=85.0, open_play=False)

    assert not is_final_third_entry(event)
