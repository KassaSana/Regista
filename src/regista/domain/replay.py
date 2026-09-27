"""The replay engine: feed events to a detector strictly in provider order.

A detector sees one event at a time and can only use what it has already seen,
so an insight emitted at a replay position depends only on events at or before
that position (prefix invariance holds by construction).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol

from regista.domain.events import Event
from regista.domain.insights import AttackingSideShift


class Detector(Protocol):
    """An incremental detector: observes one event, returns any insights it produces."""

    def observe(self, event: Event) -> list[AttackingSideShift]: ...


class ReplayOrderError(ValueError):
    """Raised when events do not arrive in strictly increasing provider sequence."""


def replay(events: Iterable[Event], detector: Detector) -> Iterator[AttackingSideShift]:
    """Feed events to a detector in order and yield insights as soon as they fire."""
    previous: Event | None = None
    for event in events:
        if previous is not None and event.sequence <= previous.sequence:
            message = (
                f"event {event.identifier} has sequence {event.sequence}, "
                f"not after {previous.sequence} (event {previous.identifier})"
            )
            raise ReplayOrderError(message)
        previous = event
        yield from detector.observe(event)
