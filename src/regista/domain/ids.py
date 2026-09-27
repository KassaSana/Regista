"""Nominal identifiers used across the Regista domain."""

from typing import NewType

EventId = NewType("EventId", str)
MatchId = NewType("MatchId", int)
PlayerId = NewType("PlayerId", int)
TeamId = NewType("TeamId", int)
