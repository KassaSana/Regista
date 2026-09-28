"""The replay score: goals, own goals, penalties, shootouts, and prefix invariance."""

from __future__ import annotations

from dataclasses import replace

import pytest
from synthetic_events import AWAY, HOME, EventStream

from regista.domain.events import ActionType, Event, MatchClock, Team
from regista.domain.ids import TeamId
from regista.domain.score import Score, ScoreTracker


def _scores(events: list[Event]) -> list[Score]:
    tracker = ScoreTracker(HOME.identifier, AWAY.identifier)
    return [tracker.observe(event) for event in events]


def test_a_scored_shot_counts_for_the_shooting_team() -> None:
    stream = EventStream()
    stream.shot(HOME, 1, 10, scored=True)
    stream.shot(AWAY, 1, 20, scored=True)
    stream.shot(AWAY, 1, 30, scored=True)

    assert _scores(stream.events) == [Score(1, 0), Score(1, 1), Score(1, 2)]


def test_a_missed_shot_does_not_change_the_score() -> None:
    stream = EventStream()
    stream.shot(HOME, 1, 10)
    stream.other(AWAY, 1, 11)

    assert _scores(stream.events) == [Score(0, 0), Score(0, 0)]


def test_a_penalty_goal_counts() -> None:
    stream = EventStream()
    stream.shot(AWAY, 2, 80, penalty=True, scored=True)

    assert _scores(stream.events) == [Score(0, 1)]


def test_an_own_goal_counts_once_for_the_credited_team() -> None:
    stream = EventStream()
    # The conceding side's own-goal record is a plain event; only the credit counts.
    stream.other(HOME, 1, 30)
    stream.own_goal_for(AWAY, 1, 30)

    assert _scores(stream.events) == [Score(0, 0), Score(0, 1)]


def test_a_penalty_shootout_does_not_change_the_score() -> None:
    stream = EventStream()
    stream.shot(HOME, 2, 60, scored=True)
    stream.shot(AWAY, 4, 115, scored=True)
    stream.shot(HOME, 5, 121, penalty=True, scored=True)
    stream.shot(AWAY, 5, 122, penalty=True, scored=True)

    assert _scores(stream.events)[-1] == Score(1, 1)


def test_a_goal_for_a_team_outside_the_match_is_rejected() -> None:
    stranger = Team(identifier=TeamId(99), name="Stranger")
    stream = EventStream()
    stream.shot(stranger, 1, 10, scored=True)

    with pytest.raises(ValueError, match="not in this match"):
        _scores(stream.events)


def test_only_an_other_event_can_credit_an_own_goal() -> None:
    shot = EventStream().shot(HOME, 1, 10)

    with pytest.raises(ValueError, match="cannot credit an own goal"):
        replace(shot, own_goal_for=True)


def test_later_events_never_change_an_earlier_score() -> None:
    stream = EventStream()
    stream.shot(HOME, 1, 10, scored=True)
    stream.other(AWAY, 1, 20)
    stream.shot(AWAY, 2, 50)
    stream.shot(AWAY, 2, 70)
    original = _scores(stream.events)
    cut = 2
    # Replace everything after the cut with goals for the other team.
    altered_tail = [
        replace(
            event,
            team=AWAY,
            action=ActionType.OTHER,
            shot=None,
            location=None,
            own_goal_for=True,
            clock=MatchClock(2, 90, 0),
        )
        for event in stream.events[cut:]
    ]

    altered = _scores([*stream.events[:cut], *altered_tail])

    assert altered[:cut] == original[:cut]
    assert altered[-1] != original[-1]
