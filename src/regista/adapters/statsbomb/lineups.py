"""Translate StatsBomb lineup files into appearances and position spells."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from regista.domain.ids import MatchId, PlayerId, TeamId
from regista.domain.lineups import Appearance, PositionSpell
from regista.domain.matches import MatchRecord
from regista.pipeline.catalog import integer, object_list, object_record, text

# StatsBomb's continuous minute restarts each period at these values (checked on
# every development match; pinned by a contract test). Extra time is periods 3
# and 4; a penalty shootout is period 5.
PERIOD_START_MINUTES = {1: 0, 2: 45, 3: 90, 4: 105, 5: 120}


class LineupFormatError(ValueError):
    """Raised when a lineup record does not match the shape Regista expects."""


def normalize_lineups(
    payload: object, match: MatchRecord
) -> tuple[tuple[Appearance, ...], tuple[PositionSpell, ...]]:
    """Return every named player and each position they held, in provider order."""
    appearances: list[Appearance] = []
    spells: list[PositionSpell] = []
    seen_teams: set[TeamId] = set()
    for value in object_list(payload, "lineups"):
        team_record = object_record(value, "lineup team")
        team_id = TeamId(integer(team_record.get("team_id"), "team_id"))
        if team_id not in match.team_ids:
            raise LineupFormatError(f"lineup team {team_id} does not play match {match.match_id}")
        if team_id in seen_teams:
            raise LineupFormatError(f"lineup repeats team {team_id}")
        seen_teams.add(team_id)
        for player_value in object_list(team_record.get("lineup"), "lineup"):
            player = object_record(player_value, "lineup player")
            player_id = PlayerId(integer(player.get("player_id"), "player_id"))
            positions = [
                object_record(position, "position")
                for position in object_list(player.get("positions"), "positions")
            ]
            for number, position in enumerate(positions, 1):
                spells.append(_spell(position, match.match_id, team_id, player_id, number))
            nickname = player.get("player_nickname")
            jersey = player.get("jersey_number")
            appearances.append(
                Appearance(
                    match_id=match.match_id,
                    team_id=team_id,
                    player_id=player_id,
                    player_name=text(player.get("player_name"), "player_name"),
                    player_nickname=nickname if isinstance(nickname, str) else None,
                    jersey_number=None if jersey is None else integer(jersey, "jersey", minimum=0),
                    started=any(
                        position.get("start_reason") == "Starting XI" for position in positions
                    ),
                    provider_record=MappingProxyType(dict(player)),
                )
            )
    if frozenset(seen_teams) != match.team_ids:
        raise LineupFormatError(f"lineups for match {match.match_id} must list both teams")
    return tuple(appearances), tuple(spells)


def continuous_clock_to_period_seconds(clock: str, period: int) -> int:
    """Convert a continuous ``MM:SS`` clock (minutes may exceed 99) to period seconds."""
    if period not in PERIOD_START_MINUTES:
        raise LineupFormatError(f"unknown period {period}")
    minutes_text, separator, seconds_text = clock.partition(":")
    if not separator or not minutes_text.isdigit() or not seconds_text.isdigit():
        raise LineupFormatError(f"clock must look like MM:SS, got {clock!r}")
    seconds = int(minutes_text) * 60 + int(seconds_text) - PERIOD_START_MINUTES[period] * 60
    if seconds < 0 or int(seconds_text) >= 60:
        raise LineupFormatError(f"clock {clock!r} is not inside period {period}")
    return seconds


def _spell(
    position: Mapping[str, object],
    match_id: MatchId,
    team_id: TeamId,
    player_id: PlayerId,
    number: int,
) -> PositionSpell:
    start_period = integer(position.get("from_period"), "from_period")
    end_clock = position.get("to")
    end_period_value = position.get("to_period")
    if (end_clock is None) != (end_period_value is None):
        raise LineupFormatError("a position spell end needs both a clock and a period")
    end_period = None if end_period_value is None else integer(end_period_value, "to_period")
    return PositionSpell(
        match_id=match_id,
        team_id=team_id,
        player_id=player_id,
        spell_number=number,
        position=text(position.get("position"), "position"),
        start_period=start_period,
        start_period_seconds=continuous_clock_to_period_seconds(
            text(position.get("from"), "from"), start_period
        ),
        end_period=end_period,
        end_period_seconds=(
            None
            if end_period is None
            else continuous_clock_to_period_seconds(text(end_clock, "to"), end_period)
        ),
        start_reason=text(position.get("start_reason"), "start_reason"),
        end_reason=text(position.get("end_reason"), "end_reason"),
    )
