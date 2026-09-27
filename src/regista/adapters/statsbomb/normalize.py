"""Translate one StatsBomb match (events and lineups) into Regista's normalized rows.

StatsBomb names stop here. The warehouse receives only provider-neutral rows,
each event still carrying its original provider record.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from regista.adapters.statsbomb.events import (
    SET_PIECE_PASS_TYPES,
    StatsBombFormatError,
    events_from_payload,
)
from regista.adapters.statsbomb.lineups import normalize_lineups
from regista.domain.events import ActionType, Event
from regista.domain.geometry import Point
from regista.domain.ids import EventId, PlayerId, TeamId
from regista.domain.matches import MatchRecord
from regista.domain.normalized import (
    EventRow,
    FormationChangeRow,
    GoalRow,
    NormalizedMatch,
    PassRow,
    ShotRow,
    SubstitutionRow,
)

# Increase when a change alters any normalized value, so rebuilt rows say which rules made them.
ADAPTER_VERSION = "statsbomb-normalize-1"
SHOOTOUT_PERIOD = 5


def normalize_match(
    match: MatchRecord, events_payload: bytes, lineups_payload: bytes
) -> NormalizedMatch:
    """Validate and translate one match. Any unexpected provider shape raises."""
    appearances, spells = normalize_lineups(json.loads(lineups_payload), match)
    events = events_from_payload(
        json.loads(events_payload), match.match_id, f"events for match {match.match_id}"
    )
    rows: list[EventRow] = []
    passes: list[PassRow] = []
    shots: list[ShotRow] = []
    substitutions: list[SubstitutionRow] = []
    formations: list[FormationChangeRow] = []
    goals: list[GoalRow] = []
    for event in events:
        record = event.provider_record
        if event.team.identifier not in match.team_ids:
            raise StatsBombFormatError(
                f"event {event.identifier} team {event.team.identifier} is not in the match"
            )
        rows.append(_event_row(event, record))
        type_name = rows[-1].provider_event_type
        if event.action is ActionType.PASS:
            passes.append(_pass_row(event, _mapping(record.get("pass"), "pass")))
        elif event.action is ActionType.SHOT:
            shot = _shot_row(event.identifier, _mapping(record.get("shot"), "shot"))
            shots.append(shot)
            if shot.is_goal:
                goals.append(_goal(event, "shot"))
        elif event.action is ActionType.SUBSTITUTION:
            details = _mapping(record.get("substitution"), "substitution")
            substitutions.append(
                SubstitutionRow(
                    event_id=event.identifier,
                    team_id=event.team.identifier,
                    player_off_id=_required_player(record.get("player"), "substitution.player"),
                    player_on_id=_required_player(
                        details.get("replacement"), "substitution.replacement"
                    ),
                    reason=_optional_name(details.get("outcome")),
                )
            )
        elif event.action is ActionType.FORMATION_CHANGE:
            tactics = _mapping(record.get("tactics"), "tactics")
            formation = tactics.get("formation")
            if isinstance(formation, bool) or not isinstance(formation, int | str):
                raise StatsBombFormatError(f"formation must be a number, got {formation!r}")
            formations.append(
                FormationChangeRow(
                    event_id=event.identifier,
                    team_id=event.team.identifier,
                    formation=str(formation),
                    kind="starting" if type_name == "Starting XI" else "tactical_shift",
                )
            )
        elif type_name == "Own Goal For":
            # StatsBomb records "Own Goal For" on the team credited with the goal
            # (checked against every development final score; pinned by a contract test).
            goals.append(_goal(event, "own_goal"))
    return NormalizedMatch(
        match=match,
        appearances=appearances,
        position_spells=spells,
        events=tuple(rows),
        passes=tuple(passes),
        shots=tuple(shots),
        substitutions=tuple(substitutions),
        formation_changes=tuple(formations),
        goals=tuple(goals),
    )


def timestamp_seconds(value: object) -> float:
    """Convert a period-relative ``HH:MM:SS.mmm`` timestamp to seconds, exact to the millisecond."""
    if not isinstance(value, str):
        raise StatsBombFormatError(f"timestamp must be a string, got {value!r}")
    parts = value.split(":")
    whole, _, fraction = parts[-1].partition(".") if len(parts) == 3 else ("", "", "")
    digits = [*parts[:2], whole]
    if len(parts) != 3 or not all(part.isdigit() for part in digits):
        raise StatsBombFormatError(f"timestamp must look like HH:MM:SS.mmm, got {value!r}")
    if fraction and (not fraction.isdigit() or len(fraction) > 3):
        raise StatsBombFormatError(f"timestamp must have at most milliseconds, got {value!r}")
    hours, minutes, seconds = (int(part) for part in digits)
    milliseconds = int(fraction.ljust(3, "0")) if fraction else 0
    total_milliseconds = ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds
    return total_milliseconds / 1000


def _event_row(event: Event, record: Mapping[str, object]) -> EventRow:
    possession = record.get("possession")
    possession_team = record.get("possession_team")
    position = record.get("position")
    return EventRow(
        event=event,
        period_seconds=timestamp_seconds(record.get("timestamp")),
        provider_event_type=_name(record.get("type"), "type"),
        player_id=_optional_player(record.get("player")),
        position=None if position is None else _name(position, "position"),
        possession=possession if isinstance(possession, int) else None,
        possession_team_id=(
            None if possession_team is None else TeamId(_identifier(possession_team, "team"))
        ),
        under_pressure=record.get("under_pressure") is True,
    )


def _pass_row(event: Event, details: Mapping[str, object]) -> PassRow:
    assert event.movement is not None  # guaranteed by Event for passes
    pass_type = _optional_name(details.get("type"))
    return PassRow(
        event_id=event.identifier,
        recipient_player_id=_optional_player(details.get("recipient")),
        completed=event.movement.completed,
        outcome=_optional_name(details.get("outcome")),
        pass_type=pass_type,
        set_piece_type=pass_type if pass_type in SET_PIECE_PASS_TYPES else None,
        open_play=event.movement.open_play,
        height=_optional_name(details.get("height")),
        is_cross=details.get("cross") is True,
        is_shot_assist=details.get("shot_assist") is True,
        is_goal_assist=details.get("goal_assist") is True,
    )


def _shot_row(identifier: EventId, details: Mapping[str, object]) -> ShotRow:
    outcome = _name(details.get("outcome"), "shot.outcome")
    xg = details.get("statsbomb_xg")
    if xg is not None and (isinstance(xg, bool) or not isinstance(xg, int | float)):
        raise StatsBombFormatError(f"shot xG must be a number, got {xg!r}")
    end = details.get("end_location")
    end_location: Point | None = None
    end_z: float | None = None
    if end is not None:
        if not isinstance(end, list):
            raise StatsBombFormatError(f"shot end_location must be a list, got {end!r}")
        values = cast(list[object], end)
        if len(values) not in (2, 3):
            raise StatsBombFormatError(f"shot end_location must have 2 or 3 numbers, got {end!r}")
        coordinates = [_number(value, "shot.end_location") for value in values]
        end_location = Point(x=coordinates[0], y=coordinates[1])
        end_z = coordinates[2] if len(coordinates) == 3 else None
    key_pass = details.get("key_pass_id")
    return ShotRow(
        event_id=identifier,
        provider_xg=None if xg is None else float(xg),
        outcome=outcome,
        is_goal=outcome == "Goal",
        shot_type=_name(details.get("type"), "shot.type"),
        body_part=_optional_name(details.get("body_part")),
        key_pass_event_id=EventId(key_pass) if isinstance(key_pass, str) else None,
        end_location=end_location,
        end_z=end_z,
    )


def _goal(event: Event, kind: str) -> GoalRow:
    return GoalRow(
        event_id=event.identifier,
        scoring_team_id=event.team.identifier,
        kind="shot" if kind == "shot" else "own_goal",
        in_shootout=event.clock.period == SHOOTOUT_PERIOD,
    )


def _mapping(value: object, description: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise StatsBombFormatError(f"{description} must be a JSON object, got {value!r}")
    return cast(Mapping[str, object], value)


def _name(value: object, description: str) -> str:
    name = _mapping(value, description).get("name")
    if not isinstance(name, str):
        raise StatsBombFormatError(f"{description}.name must be a string, got {name!r}")
    return name


def _optional_name(value: object) -> str | None:
    return None if value is None else _name(value, "named value")


def _identifier(value: object, description: str) -> int:
    identifier = _mapping(value, description).get("id")
    if isinstance(identifier, bool) or not isinstance(identifier, int):
        raise StatsBombFormatError(f"{description}.id must be an integer, got {identifier!r}")
    return identifier


def _optional_player(value: object) -> PlayerId | None:
    return None if value is None else PlayerId(_identifier(value, "player"))


def _required_player(value: object, description: str) -> PlayerId:
    return PlayerId(_identifier(value, description))


def _number(value: object, description: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise StatsBombFormatError(f"{description} must contain numbers, got {value!r}")
    return float(value)
