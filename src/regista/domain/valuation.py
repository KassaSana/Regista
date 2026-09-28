"""Provider-neutral contract for point-in-time action valuation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from regista.domain.events import ActionType, Event, MatchClock, Team
from regista.domain.geometry import Point
from regista.domain.ids import EventId, MatchId


@dataclass(frozen=True, slots=True)
class ValuedAction:
    """A supported action's value, with its location and source evidence."""

    match_id: MatchId
    event_id: EventId
    team: Team
    clock: MatchClock
    action: ActionType
    start: Point
    end: Point
    start_value: float
    end_value: float
    method: str
    source: str

    @property
    def change(self) -> float:
        return self.end_value - self.start_value


class ActionValuer(Protocol):
    """Observe one event in replay order; unsupported actions return no value."""

    def observe(self, event: Event) -> list[ValuedAction]: ...
