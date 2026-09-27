"""Normalization of StatsBomb records, using synthetic hand-built fixtures only."""

import json
from pathlib import Path

import pytest

from regista.adapters.statsbomb.events import (
    StatsBombFormatError,
    load_events,
    normalize_event,
)
from regista.domain.events import ActionType
from regista.domain.geometry import Point
from regista.domain.ids import MatchId

MATCH = MatchId(1)


def record(
    type_name: str, index: int = 1, extra: dict[str, object] | None = None
) -> dict[str, object]:
    """Build a minimal synthetic StatsBomb-shaped event record."""
    base: dict[str, object] = {
        "id": f"synthetic-{index}",
        "index": index,
        "period": 1,
        "minute": 12,
        "second": 30,
        "type": {"id": 0, "name": type_name},
        "team": {"id": 7, "name": "Home"},
        "location": [70.0, 20.0],
    }
    base.update(extra or {})
    return base


def test_completed_regular_pass_is_open_play() -> None:
    event = normalize_event(record("Pass", extra={"pass": {"end_location": [85.0, 15.0]}}), MATCH)

    assert event.action is ActionType.PASS
    assert event.movement is not None
    assert event.movement.start == Point(x=70.0, y=20.0)
    assert event.movement.end == Point(x=85.0, y=15.0)
    assert event.movement.completed
    assert event.movement.open_play


@pytest.mark.parametrize("outcome", ["Incomplete", "Out", "Unknown"])
def test_pass_with_any_outcome_is_not_completed(outcome: str) -> None:
    details = {"end_location": [85.0, 15.0], "outcome": {"id": 9, "name": outcome}}
    event = normalize_event(record("Pass", extra={"pass": details}), MATCH)

    assert event.movement is not None
    assert not event.movement.completed


@pytest.mark.parametrize("pass_type", ["Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"])
def test_set_piece_passes_are_not_open_play(pass_type: str) -> None:
    details = {"end_location": [85.0, 15.0], "type": {"id": 0, "name": pass_type}}
    event = normalize_event(record("Pass", extra={"pass": details}), MATCH)

    assert event.movement is not None
    assert not event.movement.open_play


@pytest.mark.parametrize("pass_type", ["Recovery", "Interception"])
def test_recovery_and_interception_passes_are_open_play(pass_type: str) -> None:
    details = {"end_location": [85.0, 15.0], "type": {"id": 0, "name": pass_type}}
    event = normalize_event(record("Pass", extra={"pass": details}), MATCH)

    assert event.movement is not None
    assert event.movement.open_play


def test_unknown_pass_type_fails_loudly() -> None:
    details = {"end_location": [85.0, 15.0], "type": {"id": 0, "name": "Mystery Restart"}}

    with pytest.raises(StatsBombFormatError, match="unknown pass type"):
        normalize_event(record("Pass", extra={"pass": details}), MATCH)


def test_carry_is_a_completed_open_play_movement() -> None:
    event = normalize_event(record("Carry", extra={"carry": {"end_location": [82.0, 22.0]}}), MATCH)

    assert event.action is ActionType.CARRY
    assert event.movement is not None
    assert event.movement.completed
    assert event.movement.open_play


def test_other_event_types_keep_location_but_no_movement() -> None:
    event = normalize_event(record("Pressure"), MATCH)

    assert event.action is ActionType.PRESSURE
    assert event.location == Point(x=70.0, y=20.0)
    assert event.movement is None


def test_event_without_location_is_allowed_for_other_types() -> None:
    raw = record("Half Start")
    del raw["location"]

    assert normalize_event(raw, MATCH).location is None


def test_pass_without_location_is_rejected() -> None:
    raw = record("Pass", extra={"pass": {"end_location": [85.0, 15.0]}})
    del raw["location"]

    with pytest.raises(StatsBombFormatError, match="has no location"):
        normalize_event(raw, MATCH)


def test_malformed_coordinates_are_rejected() -> None:
    with pytest.raises(StatsBombFormatError, match="two numbers"):
        normalize_event(record("Pressure", extra={"location": [70.0]}), MATCH)


def test_normalized_fields_and_original_record() -> None:
    raw = record("Pressure", index=42)
    event = normalize_event(raw, MATCH)

    assert event.identifier == "synthetic-42"
    assert event.sequence == 42
    assert event.match_id == MATCH
    assert (event.clock.period, event.clock.minute, event.clock.second) == (1, 12, 30)
    assert event.team.name == "Home"
    assert event.source == "StatsBomb Open Data"
    assert event.provider_record == raw


def test_load_events_orders_by_provider_sequence(tmp_path: Path) -> None:
    path = tmp_path / "events.json"
    path.write_text(json.dumps([record("Pressure", index=3), record("Pressure", index=1)]))

    assert [event.sequence for event in load_events(path, MATCH)] == [1, 3]


def test_load_events_rejects_a_non_list_file(tmp_path: Path) -> None:
    path = tmp_path / "events.json"
    path.write_text(json.dumps({"not": "a list"}))

    with pytest.raises(StatsBombFormatError, match="JSON list"):
        load_events(path, MATCH)


def test_load_events_rejects_a_repeated_index(tmp_path: Path) -> None:
    first = record("Pressure", index=5)
    second = record("Pressure", index=5)
    second["id"] = "synthetic-duplicate"
    path = tmp_path / "events.json"
    path.write_text(json.dumps([first, second]))

    with pytest.raises(StatsBombFormatError, match="repeats index 5"):
        load_events(path, MATCH)
