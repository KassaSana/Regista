"""Learn an expected-threat grid from development-only action counts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from regista.domain.events import ActionType, Event
from regista.domain.geometry import Pitch, Point
from regista.domain.valuation import ValuedAction


@dataclass(frozen=True, slots=True)
class CellCounts:
    cell: int
    shots: int
    goals: int
    move_attempts: int


@dataclass(frozen=True, slots=True)
class TransitionCount:
    start_cell: int
    end_cell: int
    completed_moves: int


@dataclass(frozen=True, slots=True)
class ExpectedThreatSurface:
    """A grid of goal probabilities from repeated shot-or-move decisions."""

    columns: int
    rows: int
    values: tuple[float, ...]
    iterations: int
    residual: float

    def __post_init__(self) -> None:
        if self.columns < 1 or self.rows < 1 or len(self.values) != self.columns * self.rows:
            raise ValueError("expected-threat surface dimensions do not match its values")
        if any(not 0 <= value <= 1 for value in self.values):
            raise ValueError("expected-threat values must be probabilities")

    def cell(self, point: Point, pitch: Pitch | None = None) -> int:
        field = pitch or Pitch()
        if not field.contains(point):
            raise ValueError("expected-threat location is outside the pitch")
        x = min(int(point.x / field.length * self.columns), self.columns - 1)
        y = min(int(point.y / field.width * self.rows), self.rows - 1)
        return y * self.columns + x

    def at(self, point: Point, pitch: Pitch | None = None) -> float:
        return self.values[self.cell(point, pitch)]

    @classmethod
    def fit(
        cls,
        cell_counts: list[CellCounts],
        transitions: list[TransitionCount],
        *,
        columns: int = 16,
        rows: int = 12,
        tolerance: float = 1e-8,
        maximum_iterations: int = 500,
    ) -> ExpectedThreatSurface:
        """Solve shot reward plus successful-move transitions until convergence."""
        if columns < 1 or rows < 1 or not 0 < tolerance < 1 or maximum_iterations < 1:
            raise ValueError("invalid expected-threat grid or solver settings")
        cells = columns * rows
        shots = np.zeros(cells, dtype=np.float64)
        goals = np.zeros(cells, dtype=np.float64)
        moves = np.zeros(cells, dtype=np.float64)
        seen: set[int] = set()
        for counts in cell_counts:
            if (
                not 0 <= counts.cell < cells
                or counts.cell in seen
                or counts.shots < 0
                or not 0 <= counts.goals <= counts.shots
                or counts.move_attempts < 0
            ):
                raise ValueError("invalid or duplicate expected-threat cell counts")
            seen.add(counts.cell)
            shots[counts.cell] = counts.shots
            goals[counts.cell] = counts.goals
            moves[counts.cell] = counts.move_attempts
        matrix = np.zeros((cells, cells), dtype=np.float64)
        for transition in transitions:
            if (
                not 0 <= transition.start_cell < cells
                or not 0 <= transition.end_cell < cells
                or transition.completed_moves < 0
            ):
                raise ValueError("invalid expected-threat transition")
            matrix[transition.start_cell, transition.end_cell] += transition.completed_moves
        if np.any(matrix.sum(axis=1) > moves):
            raise ValueError("completed transitions exceed attempted moves")
        total = shots + moves
        reward = np.divide(goals, total, out=np.zeros_like(goals), where=total > 0)
        move_probability = np.divide(moves, total, out=np.zeros_like(moves), where=total > 0)
        transition_probability = np.divide(
            matrix, moves[:, None], out=np.zeros_like(matrix), where=moves[:, None] > 0
        )
        values = np.zeros(cells, dtype=np.float64)
        for iteration in range(1, maximum_iterations + 1):
            updated = reward + move_probability * (transition_probability @ values)
            residual = float(np.max(np.abs(updated - values)))
            values = updated
            if residual <= tolerance:
                return cls(
                    columns, rows, tuple(float(value) for value in values), iteration, residual
                )
        raise ValueError("expected-threat grid did not converge")


class ExpectedThreatValuer:
    """Value a completed open-play pass or carry from a fitted surface."""

    def __init__(self, surface: ExpectedThreatSurface, pitch: Pitch | None = None) -> None:
        self._surface = surface
        self._pitch = pitch or Pitch()

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
                self._surface.at(movement.start, self._pitch),
                self._surface.at(movement.end, self._pitch),
                "expected_threat",
                event.source,
            )
        ]
