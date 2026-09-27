"""Provider-independent match events.

The event model is deliberately small: it carries only what the Phase 1
attacking-side shift detector needs (see
``docs/specs/phase-1-attacking-side-shift.md``), plus the original provider
record so later increments can reach fields that are not modeled yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from regista.domain.geometry import Point
from regista.domain.ids import EventId, MatchId, TeamId


class ActionType(Enum):
    """What an event records, collapsed to the kinds Regista reasons about.

    The list is the Regista event vocabulary from the Phase 2 specification.
    Each adapter maps every provider type onto one of these and fails loudly on
    a provider type it does not know.
    """

    PASS = "pass"
    CARRY = "carry"
    SHOT = "shot"
    PRESSURE = "pressure"
    DUEL = "duel"
    DRIBBLE = "dribble"
    BALL_RECOVERY = "ball_recovery"
    INTERCEPTION = "interception"
    CLEARANCE = "clearance"
    BLOCK = "block"
    FOUL = "foul"
    GOALKEEPER = "goalkeeper"
    SUBSTITUTION = "substitution"
    FORMATION_CHANGE = "formation_change"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"
    OTHER = "other"


BALL_MOVING_ACTIONS = frozenset({ActionType.PASS, ActionType.CARRY})


@dataclass(frozen=True, slots=True)
class MatchClock:
    """When an event happened, as recorded by the provider.

    ``minute`` runs continuously across periods (the second half starts at
    minute 45), so stoppage time at the end of one period can overlap the start
    of the next. Calculations must therefore always consider ``period`` too.
    """

    period: int
    minute: int
    second: int

    def __post_init__(self) -> None:
        if self.period < 1:
            message = f"period must be at least 1, got {self.period}"
            raise ValueError(message)
        if self.minute < 0:
            message = f"minute must not be negative, got {self.minute}"
            raise ValueError(message)
        if not 0 <= self.second < 60:
            message = f"second must be in [0, 60), got {self.second}"
            raise ValueError(message)

    @property
    def elapsed_seconds(self) -> int:
        """Return seconds since kickoff on the provider's continuous clock."""
        return self.minute * 60 + self.second


@dataclass(frozen=True, slots=True)
class Team:
    """A team as it appears on an event: stable identifier plus display name."""

    identifier: TeamId
    name: str


@dataclass(frozen=True, slots=True)
class BallMovement:
    """Where a pass or carry moved the ball, and whether it counts.

    Only passes and carries have a ball movement, so a shot or tackle can never
    carry an end location or a completion flag by accident.
    """

    start: Point
    end: Point
    completed: bool
    open_play: bool


@dataclass(frozen=True, slots=True)
class Event:
    """One provider event translated into Regista's own terms.

    ``sequence`` is the provider's ordering and is the only safe replay order:
    provider timestamps are not guaranteed to increase monotonically.
    ``source`` names the data source so insights can cite their evidence.
    """

    identifier: EventId
    sequence: int
    match_id: MatchId
    clock: MatchClock
    team: Team
    action: ActionType
    location: Point | None
    movement: BallMovement | None
    source: str
    provider_record: Mapping[str, object] = field(compare=False, repr=False)

    def __post_init__(self) -> None:
        moves_ball = self.action in BALL_MOVING_ACTIONS
        if moves_ball and self.movement is None:
            message = f"{self.action.value} event {self.identifier} needs a ball movement"
            raise ValueError(message)
        if not moves_ball and self.movement is not None:
            message = f"{self.action.value} event {self.identifier} cannot have a ball movement"
            raise ValueError(message)
