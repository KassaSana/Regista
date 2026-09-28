"""Evidence-backed facts recorded directly in a match event stream."""

from __future__ import annotations

from dataclasses import dataclass

from regista.domain.events import MatchClock, NamedPlayer, Team
from regista.domain.ids import EventId, MatchId


@dataclass(frozen=True, slots=True)
class StartingLineupFact:
    match_id: MatchId
    team: Team
    fired_at: MatchClock
    formation: str
    players: tuple[NamedPlayer, ...]
    evidence_event_id: EventId
    source: str


@dataclass(frozen=True, slots=True)
class SubstitutionFact:
    match_id: MatchId
    team: Team
    fired_at: MatchClock
    departing: NamedPlayer
    entering: NamedPlayer
    evidence_event_id: EventId
    source: str


@dataclass(frozen=True, slots=True)
class FormationChangeFact:
    match_id: MatchId
    team: Team
    fired_at: MatchClock
    previous_formation: str
    formation: str
    previous_event_id: EventId
    previous_source: str
    evidence_event_id: EventId
    source: str


MatchFact = StartingLineupFact | SubstitutionFact | FormationChangeFact
