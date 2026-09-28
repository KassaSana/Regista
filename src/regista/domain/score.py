"""The score as it stands during replay.

The tracker observes events in provider order, like a detector, so the score it
reports after an event depends only on events at or before that event. Goals
come from scored shots (penalties included) and credited own goals. A penalty
shootout decides a tied match but does not change the score.
"""

from __future__ import annotations

from dataclasses import dataclass

from regista.domain.events import ActionType, Event, Team
from regista.domain.ids import TeamId

# The provider period that holds a penalty shootout.
SHOOTOUT_PERIOD = 5


@dataclass(frozen=True, slots=True)
class Score:
    """Goals for the home and away teams."""

    home: int
    away: int


def goal_scored_by(event: Event) -> Team | None:
    """Return the team credited with a goal at this event, or None if it is not a goal."""
    if event.clock.period == SHOOTOUT_PERIOD:
        return None
    if event.action is ActionType.SHOT and event.shot is not None and event.shot.scored:
        return event.team
    if event.own_goal_for:
        return event.team
    return None


class ScoreTracker:
    """Keeps the score while events are replayed in order."""

    def __init__(self, home: TeamId, away: TeamId) -> None:
        if home == away:
            raise ValueError("home and away must be different teams")
        self._home = home
        self._away = away
        self._score = Score(home=0, away=0)

    @property
    def score(self) -> Score:
        """Return the score after the last observed event."""
        return self._score

    def observe(self, event: Event) -> Score:
        """Observe one event and return the score after it."""
        scorer = goal_scored_by(event)
        if scorer is None:
            return self._score
        if scorer.identifier == self._home:
            self._score = Score(home=self._score.home + 1, away=self._score.away)
        elif scorer.identifier == self._away:
            self._score = Score(home=self._score.home, away=self._score.away + 1)
        else:
            message = (
                f"goal at event {event.identifier} credits team {scorer.identifier}, "
                "not in this match"
            )
            raise ValueError(message)
        return self._score
