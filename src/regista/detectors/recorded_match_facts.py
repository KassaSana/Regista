"""Emit factual lineup, substitution, and changed-formation observations."""

from __future__ import annotations

from regista.domain.events import Event, FormationDetail, SubstitutionDetail
from regista.domain.ids import EventId, TeamId
from regista.domain.match_facts import (
    FormationChangeFact,
    MatchFact,
    StartingLineupFact,
    SubstitutionFact,
)


class RecordedMatchFactsDetector:
    """Observe provider-neutral event details in replay order."""

    def __init__(self) -> None:
        self._formations: dict[TeamId, tuple[str, EventId, str]] = {}

    def observe(self, event: Event) -> list[MatchFact]:
        detail = event.match_fact
        if isinstance(detail, SubstitutionDetail):
            return [
                SubstitutionFact(
                    event.match_id,
                    event.team,
                    event.clock,
                    detail.departing,
                    detail.entering,
                    event.identifier,
                    event.source,
                )
            ]
        if not isinstance(detail, FormationDetail):
            return []
        if detail.starting:
            self._formations[event.team.identifier] = (
                detail.formation,
                event.identifier,
                event.source,
            )
            return [
                StartingLineupFact(
                    event.match_id,
                    event.team,
                    event.clock,
                    detail.formation,
                    detail.starting_players,
                    event.identifier,
                    event.source,
                )
            ]
        previous = self._formations.get(event.team.identifier)
        self._formations[event.team.identifier] = (detail.formation, event.identifier, event.source)
        if previous is None or previous[0] == detail.formation:
            return []
        return [
            FormationChangeFact(
                event.match_id,
                event.team,
                event.clock,
                previous[0],
                detail.formation,
                previous[1],
                previous[2],
                event.identifier,
                event.source,
            )
        ]
