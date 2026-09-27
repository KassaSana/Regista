"""Final-third entries and the channels they end in.

Definitions are locked in AGENTS.md and
``docs/specs/phase-1-attacking-side-shift.md``. All coordinates are in the
acting team's attacking frame on the 120 by 80 pitch.
"""

from __future__ import annotations

from enum import Enum

from regista.domain.events import Event
from regista.domain.geometry import Pitch, Point

_PITCH = Pitch()

# The final third starts two thirds of the way up the pitch (x = 80).
FINAL_THIRD_START_X = _PITCH.length * 2 / 3
# Channel boundaries split the width into thirds. Low y is the acting team's left.
LEFT_CHANNEL_END_Y = _PITCH.width / 3
RIGHT_CHANNEL_START_Y = _PITCH.width * 2 / 3


class Channel(Enum):
    """A third of the pitch width, from the acting team's point of view."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


def channel_of(point: Point) -> Channel:
    """Return the channel containing a point; both boundaries belong to the center."""
    if point.y < LEFT_CHANNEL_END_Y:
        return Channel.LEFT
    if point.y > RIGHT_CHANNEL_START_Y:
        return Channel.RIGHT
    return Channel.CENTER


def is_final_third_entry(event: Event) -> bool:
    """Return whether an event is an open-play completed pass or carry into the final third."""
    movement = event.movement
    if movement is None or not movement.completed or not movement.open_play:
        return False
    return movement.start.x < FINAL_THIRD_START_X <= movement.end.x
