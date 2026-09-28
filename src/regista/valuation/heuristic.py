"""Transparent geometric baseline for completed open-play ball movements."""

from __future__ import annotations

from math import hypot

from regista.domain.events import ActionType, Event
from regista.domain.geometry import Pitch, Point
from regista.domain.valuation import ValuedAction


class HeuristicMovementValuer:
    """Value movement by reduction in distance to the opponent goal center.

    The scale is normalized pitch distance, not a goal probability. It is an
    untuned comparison baseline for the learned expected-threat model.
    """

    def __init__(self, pitch: Pitch | None = None) -> None:
        self._pitch = pitch or Pitch()
        self._max_distance = hypot(self._pitch.length, self._pitch.width / 2)

    def _location_value(self, point: Point) -> float:
        return 1 - self._pitch.distance_to_opponent_goal(point) / self._max_distance

    def observe(self, event: Event) -> list[ValuedAction]:
        movement = event.movement
        if (
            event.action not in (ActionType.PASS, ActionType.CARRY)
            or movement is None
            or not movement.open_play
            or not movement.completed
        ):
            return []
        if not self._pitch.contains(movement.start) or not self._pitch.contains(movement.end):
            return []
        return [
            ValuedAction(
                event.match_id,
                event.identifier,
                event.team,
                event.clock,
                event.action,
                movement.start,
                movement.end,
                self._location_value(movement.start),
                self._location_value(movement.end),
                "goal_distance",
                event.source,
            )
        ]
