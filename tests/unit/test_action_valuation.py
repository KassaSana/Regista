"""Movement valuation and expected-threat equation on synthetic actions."""

from __future__ import annotations

import pytest

from regista.domain.events import ActionType, BallMovement, Event, MatchClock, ShotDetail, Team
from regista.domain.geometry import Point
from regista.domain.ids import EventId, MatchId, TeamId
from regista.domain.replay import replay
from regista.valuation.expected_threat import (
    CellCounts,
    ExpectedThreatSurface,
    ExpectedThreatValuer,
    TransitionCount,
)
from regista.valuation.heuristic import HeuristicMovementValuer

START = Point(10, 40)
END = Point(100, 40)


def event(
    sequence: int,
    *,
    action: ActionType = ActionType.PASS,
    completed: bool = True,
    open_play: bool = True,
    start: Point = START,
    end: Point = END,
) -> Event:
    movement = (
        BallMovement(start, end, completed, open_play)
        if action in (ActionType.PASS, ActionType.CARRY)
        else None
    )
    return Event(
        EventId(f"action-{sequence}"),
        sequence,
        MatchId(1),
        MatchClock(1, sequence, 0),
        Team(TeamId(1), "Home"),
        action,
        start if movement else None,
        movement,
        "Synthetic source",
        {},
        shot=ShotDetail(penalty=False) if action is ActionType.SHOT else None,
    )


def surface() -> ExpectedThreatSurface:
    # Cell 1 scores from its only shot. Cell 0 shoots unsuccessfully half the
    # time and moves successfully to cell 1 half the time: V(0) = 0.5.
    return ExpectedThreatSurface.fit(
        [CellCounts(0, 1, 0, 1), CellCounts(1, 1, 1, 0)],
        [TransitionCount(0, 1, 1)],
        columns=2,
        rows=1,
    )


def test_expected_threat_solves_the_two_cell_equation_and_values_a_move() -> None:
    model = surface()
    assert model.values == pytest.approx((0.5, 1.0))
    assert model.iterations <= 4

    values = list(replay([event(1)], ExpectedThreatValuer(model)))
    assert len(values) == 1
    assert values[0].change == pytest.approx(0.5)
    assert values[0].event_id == EventId("action-1")
    assert values[0].source == "Synthetic source"


def test_failed_move_reduces_the_transition_probability() -> None:
    # Cell 0 has a missed shot, one completed move, and one failed move.
    # Only the completed move reaches the certain-goal cell: V(0) = 1/3.
    model = ExpectedThreatSurface.fit(
        [CellCounts(0, 1, 0, 2), CellCounts(1, 1, 1, 0)],
        [TransitionCount(0, 1, 1)],
        columns=2,
        rows=1,
    )
    assert model.values == pytest.approx((1 / 3, 1.0))


def test_heuristic_and_grid_share_the_same_replay_contract() -> None:
    actions = [event(1), event(2, action=ActionType.CARRY)]
    heuristic = list(replay(actions, HeuristicMovementValuer()))
    learned = list(replay(actions, ExpectedThreatValuer(surface())))

    assert [value.event_id for value in heuristic] == [value.event_id for value in learned]
    assert all(value.change > 0 for value in heuristic)
    assert all(value.change == pytest.approx(0.5) for value in learned)


@pytest.mark.parametrize(
    "action",
    [
        event(1, completed=False),
        event(1, open_play=False),
        event(1, action=ActionType.SHOT),
        event(1, end=Point(130, 40)),
    ],
)
def test_unsupported_or_invalid_moves_have_no_value(action: Event) -> None:
    assert list(replay([action], HeuristicMovementValuer())) == []
    assert list(replay([action], ExpectedThreatValuer(surface()))) == []


def test_fit_rejects_more_successes_than_attempts() -> None:
    with pytest.raises(ValueError, match="exceed attempted moves"):
        ExpectedThreatSurface.fit(
            [CellCounts(0, 1, 0, 1)],
            [TransitionCount(0, 1, 2)],
            columns=2,
            rows=1,
        )


def test_action_values_are_prefix_invariant() -> None:
    prefix = [event(1)]
    before = list(replay(prefix, ExpectedThreatValuer(surface())))
    after = list(replay(prefix + [event(2)], ExpectedThreatValuer(surface())))
    assert after[: len(before)] == before
