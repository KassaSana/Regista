"""Who was named for a match, and which position each player held when."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from regista.domain.ids import MatchId, PlayerId, TeamId


@dataclass(frozen=True, slots=True)
class Appearance:
    """A player named in a team's match lineup, whether or not they played."""

    match_id: MatchId
    team_id: TeamId
    player_id: PlayerId
    player_name: str
    player_nickname: str | None
    jersey_number: int | None
    started: bool
    provider_record: Mapping[str, object] = field(compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class PositionSpell:
    """One uninterrupted spell in one position.

    Times are period-relative seconds. An open end (``end_period is None``)
    means the player stayed on until the final whistle.
    """

    match_id: MatchId
    team_id: TeamId
    player_id: PlayerId
    spell_number: int
    position: str
    start_period: int
    start_period_seconds: int
    end_period: int | None
    end_period_seconds: int | None
    start_reason: str
    end_reason: str
