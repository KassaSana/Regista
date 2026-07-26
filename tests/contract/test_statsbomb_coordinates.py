"""Contract checks for assumptions made about StatsBomb's coordinate frame."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import fmean
from typing import TypedDict, cast

import pytest

from regista.domain.geometry import Pitch, Point

pytestmark = pytest.mark.contract

MATCH_ID = 3_773_497
EVENTS_PATH = Path("data/statsbomb/data/events") / f"{MATCH_ID}.json"


class _NamedObject(TypedDict):
    name: str


class _RawEvent(TypedDict, total=False):
    location: list[float]
    period: int
    team: _NamedObject
    type: _NamedObject


def _event_location(event: _RawEvent) -> Point:
    location = event.get("location")
    assert location is not None
    assert len(location) == 2
    return Point(x=location[0], y=location[1])


def test_both_teams_attack_toward_increasing_x() -> None:
    """A provider change must not silently invert Regista's spatial model."""
    if not EVENTS_PATH.exists():
        pytest.skip("download StatsBomb match 3773497 to run the coordinate contract")

    with EVENTS_PATH.open(encoding="utf-8") as event_file:
        events = cast(list[_RawEvent], json.load(event_file))

    shots = [event for event in events if event.get("type", {}).get("name") == "Shot"]
    expected_team_periods = {
        (team, period) for team in ("Barcelona", "Real Madrid") for period in (1, 2)
    }
    shots_by_team_period = {
        key: [
            event
            for event in shots
            if (event.get("team", {}).get("name"), event.get("period")) == key
        ]
        for key in expected_team_periods
    }
    pitch = Pitch()

    assert all(shots_by_team_period.values())
    for team_shots in shots_by_team_period.values():
        locations = [_event_location(event) for event in team_shots]
        assert all(pitch.contains(location) for location in locations)
        assert fmean(location.x for location in locations) > 100.0
