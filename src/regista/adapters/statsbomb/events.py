"""Translate StatsBomb open-data event files into Regista events.

This module is an anti-corruption layer: StatsBomb's names, nesting, and
conventions stop here, and everything past it speaks in domain types. Parsing is
validated by hand so a provider change fails loudly at the boundary instead of
quietly producing wrong insights later.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import cast

from regista.domain.events import ActionType, BallMovement, Event, MatchClock, Team
from regista.domain.geometry import Point
from regista.domain.ids import EventId, MatchId, TeamId

# Pass types (``pass.type.name``) that restart play. Regular passes have no type.
SET_PIECE_PASS_TYPES = frozenset({"Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"})
# Pass types that happen during open play.
OPEN_PLAY_PASS_TYPES = frozenset({"Recovery", "Interception"})

# Every StatsBomb event type (open-data specification v4) mapped onto Regista's
# vocabulary. An unlisted type fails loudly: it must be classified on purpose.
ACTIONS_BY_TYPE_NAME = {
    "Pass": ActionType.PASS,
    "Carry": ActionType.CARRY,
    "Shot": ActionType.SHOT,
    "Pressure": ActionType.PRESSURE,
    "Duel": ActionType.DUEL,
    "50/50": ActionType.DUEL,
    "Dribble": ActionType.DRIBBLE,
    "Ball Recovery": ActionType.BALL_RECOVERY,
    "Interception": ActionType.INTERCEPTION,
    "Clearance": ActionType.CLEARANCE,
    "Block": ActionType.BLOCK,
    "Foul Committed": ActionType.FOUL,
    "Foul Won": ActionType.FOUL,
    "Goal Keeper": ActionType.GOALKEEPER,
    "Substitution": ActionType.SUBSTITUTION,
    "Starting XI": ActionType.FORMATION_CHANGE,
    "Tactical Shift": ActionType.FORMATION_CHANGE,
    "Half Start": ActionType.PERIOD_START,
    "Half End": ActionType.PERIOD_END,
    "Ball Receipt*": ActionType.OTHER,
    "Miscontrol": ActionType.OTHER,
    "Dispossessed": ActionType.OTHER,
    "Dribbled Past": ActionType.OTHER,
    "Shield": ActionType.OTHER,
    "Error": ActionType.OTHER,
    "Offside": ActionType.OTHER,
    "Bad Behaviour": ActionType.OTHER,
    "Injury Stoppage": ActionType.OTHER,
    "Referee Ball-Drop": ActionType.OTHER,
    "Player On": ActionType.OTHER,
    "Player Off": ActionType.OTHER,
    "Own Goal For": ActionType.OTHER,
    "Own Goal Against": ActionType.OTHER,
    "Camera On": ActionType.OTHER,
    "Camera off": ActionType.OTHER,
}

# Recorded on every event so each insight can name where its evidence came from.
SOURCE = "StatsBomb Open Data"


class StatsBombFormatError(ValueError):
    """Raised when a StatsBomb record does not match the shape Regista expects."""


def load_events(path: Path, match_id: MatchId) -> list[Event]:
    """Read one StatsBomb event file and return its events in provider order.

    Provider order must be unambiguous, so a repeated ``index`` is rejected.
    """
    with path.open(encoding="utf-8") as event_file:
        payload: object = json.load(event_file)
    return events_from_payload(payload, match_id, str(path))


def events_from_payload(payload: object, match_id: MatchId, description: str) -> list[Event]:
    """Normalize a parsed event list and return it in unambiguous provider order."""
    if not isinstance(payload, list):
        message = f"{description} must contain a JSON list of events"
        raise StatsBombFormatError(message)
    records = cast(list[object], payload)
    events = [normalize_event(_as_mapping(record, "event"), match_id) for record in records]
    events.sort(key=lambda event: event.sequence)
    for earlier, later in zip(events, events[1:], strict=False):
        if earlier.sequence == later.sequence:
            message = (
                f"{description} repeats index {later.sequence} "
                f"(events {earlier.identifier} and {later.identifier})"
            )
            raise StatsBombFormatError(message)
    return events


def normalize_event(record: Mapping[str, object], match_id: MatchId) -> Event:
    """Translate one StatsBomb event record into a Regista event."""
    identifier = EventId(_string_field(record, "id"))
    type_name = _name_of(record.get("type"), "type")
    action = ACTIONS_BY_TYPE_NAME.get(type_name)
    if action is None:
        message = f"unknown event type {type_name!r}: map it onto a Regista event type"
        raise StatsBombFormatError(message)
    raw_location = record.get("location")
    location = None if raw_location is None else _point(raw_location, "location")
    return Event(
        identifier=identifier,
        sequence=_integer_field(record, "index"),
        match_id=match_id,
        clock=MatchClock(
            period=_integer_field(record, "period"),
            minute=_integer_field(record, "minute"),
            second=_integer_field(record, "second"),
        ),
        team=_team(record.get("team")),
        action=action,
        location=location,
        movement=_ball_movement(record, identifier, action, location),
        source=SOURCE,
        provider_record=MappingProxyType(dict(record)),
    )


def _ball_movement(
    record: Mapping[str, object],
    identifier: EventId,
    action: ActionType,
    start: Point | None,
) -> BallMovement | None:
    if action not in (ActionType.PASS, ActionType.CARRY):
        return None
    if start is None:
        message = f"{action.value} event {identifier} has no location"
        raise StatsBombFormatError(message)
    if action is ActionType.PASS:
        details = _as_mapping(record.get("pass"), "pass")
        return BallMovement(
            start=start,
            end=_point(details.get("end_location"), "pass.end_location"),
            # StatsBomb records an outcome only when a pass does not complete. Any
            # outcome, including "Unknown", means not completed: Regista never
            # claims a completion the provider cannot confirm.
            completed="outcome" not in details,
            open_play=_is_open_play_pass(details),
        )
    details = _as_mapping(record.get("carry"), "carry")
    return BallMovement(
        start=start,
        end=_point(details.get("end_location"), "carry.end_location"),
        completed=True,
        open_play=True,
    )


def _is_open_play_pass(details: Mapping[str, object]) -> bool:
    pass_type = details.get("type")
    if pass_type is None:
        return True
    name = _name_of(pass_type, "pass.type")
    if name in OPEN_PLAY_PASS_TYPES:
        return True
    if name in SET_PIECE_PASS_TYPES:
        return False
    message = f"unknown pass type {name!r}: classify it as open play or set piece"
    raise StatsBombFormatError(message)


def _team(value: object) -> Team:
    team = _as_mapping(value, "team")
    return Team(identifier=TeamId(_integer_field(team, "id")), name=_string_field(team, "name"))


def _point(value: object, description: str) -> Point:
    if not isinstance(value, list):
        message = f"{description} must be a list of two numbers, got {value!r}"
        raise StatsBombFormatError(message)
    coordinates = cast(list[object], value)
    if len(coordinates) != 2:
        message = f"{description} must be a list of two numbers, got {value!r}"
        raise StatsBombFormatError(message)
    x, y = coordinates
    return Point(x=_number(x, description), y=_number(y, description))


def _number(value: object, description: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        message = f"{description} must contain numbers, got {value!r}"
        raise StatsBombFormatError(message)
    return float(value)


def _name_of(value: object, description: str) -> str:
    return _string_field(_as_mapping(value, description), "name")


def _as_mapping(value: object, description: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        message = f"{description} must be a JSON object, got {value!r}"
        raise StatsBombFormatError(message)
    return cast(Mapping[str, object], value)


def _string_field(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        message = f"field {key!r} must be a string, got {value!r}"
        raise StatsBombFormatError(message)
    return value


def _integer_field(record: Mapping[str, object], key: str) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        message = f"field {key!r} must be an integer, got {value!r}"
        raise StatsBombFormatError(message)
    return value
