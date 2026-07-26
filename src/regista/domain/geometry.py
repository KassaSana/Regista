"""Provider-independent geometry for Regista's attacking coordinate frame."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, hypot


@dataclass(frozen=True, slots=True)
class Point:
    """A location on a two-dimensional pitch, compared by value."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Pitch:
    """A pitch where the acting team always attacks toward increasing x."""

    length: float = 120.0
    width: float = 80.0

    def __post_init__(self) -> None:
        if self.length <= 0.0 or self.width <= 0.0:
            message = "pitch dimensions must be positive"
            raise ValueError(message)

    @property
    def opponent_goal_center(self) -> Point:
        """Return the center of the opponent's goal line."""
        return Point(x=self.length, y=self.width / 2.0)

    def contains(self, point: Point) -> bool:
        """Return whether a point lies on or within the pitch boundary."""
        return 0.0 <= point.x <= self.length and 0.0 <= point.y <= self.width

    def distance_to_opponent_goal(self, point: Point) -> float:
        """Return straight-line distance from a point to the opponent goal center."""
        self._require_on_pitch(point)
        goal = self.opponent_goal_center
        return hypot(goal.x - point.x, goal.y - point.y)

    def angle_to_opponent_goal(self, point: Point) -> float:
        """Return the unsigned angle from the forward axis to the goal center.

        Zero is directly central. Values grow toward either touchline and are
        bounded by pi/2 for points in the verified attacking coordinate frame.
        """
        self._require_on_pitch(point)
        goal = self.opponent_goal_center
        return atan2(abs(goal.y - point.y), goal.x - point.x)

    def _require_on_pitch(self, point: Point) -> None:
        if not self.contains(point):
            message = f"point {point!r} is outside the pitch"
            raise ValueError(message)
