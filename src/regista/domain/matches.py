"""Provider-independent match metadata, as recorded before or at kickoff.

The final score is known only after the match. It is kept for data-quality
reconciliation and retrospective research, never for an in-match detector.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, time

from regista.domain.ids import MatchId, TeamId


@dataclass(frozen=True, slots=True)
class TeamRecord:
    """A team's identifier and display name. No crests or logos."""

    identifier: TeamId
    name: str


@dataclass(frozen=True, slots=True)
class MatchRecord:
    """One match from a provider's match index."""

    provider: str
    match_id: MatchId
    competition_id: int
    season_id: int
    competition_name: str
    season_name: str
    match_date: date
    kickoff: time
    home_team: TeamRecord
    away_team: TeamRecord
    home_score: int
    away_score: int
    match_week: int | None
    stage: str | None
    stadium: str | None
    data_version: str | None
    xy_fidelity_version: str | None
    shot_fidelity_version: str | None
    provider_last_updated: str | None
    has_three_sixty: bool
    provider_record: Mapping[str, object] = field(compare=False, repr=False)

    @property
    def team_ids(self) -> frozenset[TeamId]:
        return frozenset({self.home_team.identifier, self.away_team.identifier})
