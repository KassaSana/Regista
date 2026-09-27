"""Contract checks pinning StatsBomb event assumptions the adapter relies on.

These read the locally downloaded match file and skip when it is missing.
They never copy provider records into the repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import fmean
from typing import cast

import pytest

from regista.adapters.statsbomb.events import load_events
from regista.domain.ids import MatchId

pytestmark = pytest.mark.contract

MATCH_ID = MatchId(3_773_497)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVENTS_PATH = REPOSITORY_ROOT / "data/statsbomb/data/events" / f"{MATCH_ID}.json"

# Every pass outcome observed means the pass did not complete, including "Unknown":
# Regista never claims a completion the provider cannot confirm. A completed pass has none.
OUTCOMES_MEANING_NOT_COMPLETED = frozenset(
    {"Incomplete", "Out", "Pass Offside", "Unknown", "Injury Clearance"}
)

LEFT_SIDED_POSITIONS = frozenset({"Left Back", "Left Wing Back"})
RIGHT_SIDED_POSITIONS = frozenset({"Right Back", "Right Wing Back"})
# The first substitution in this match happens at minute 42.
BEFORE_SUBSTITUTIONS_MINUTE = 40


def _raw_events() -> list[dict[str, object]]:
    if not EVENTS_PATH.exists():
        pytest.skip(f"download StatsBomb match {MATCH_ID} to run the event contract")
    with EVENTS_PATH.open(encoding="utf-8") as event_file:
        return cast(list[dict[str, object]], json.load(event_file))


def _details(event: dict[str, object], key: str) -> dict[str, object]:
    return cast(dict[str, object], event.get(key, {}))


def _type_name(event: dict[str, object]) -> str:
    return cast(str, _details(event, "type")["name"])


def test_every_event_normalizes_in_strict_provider_order() -> None:
    raw_events = _raw_events()

    events = load_events(EVENTS_PATH, MATCH_ID)

    assert len(events) == len(raw_events)
    sequences = [event.sequence for event in events]
    assert all(earlier < later for earlier, later in zip(sequences, sequences[1:], strict=False))


def test_pass_outcomes_only_ever_mark_a_pass_as_not_completed() -> None:
    passes = [_details(event, "pass") for event in _raw_events() if _type_name(event) == "Pass"]
    outcome_names = {
        cast(str, cast(dict[str, object], details["outcome"])["name"])
        for details in passes
        if "outcome" in details
    }

    assert outcome_names <= OUTCOMES_MEANING_NOT_COMPLETED


def test_carries_never_record_an_outcome() -> None:
    carries = [_details(event, "carry") for event in _raw_events() if _type_name(event) == "Carry"]

    assert carries
    assert all("outcome" not in details for details in carries)


def test_low_y_is_the_acting_teams_left() -> None:
    """Pin channel orientation: low y must be the acting team's left.

    Channels are defined from y, with left being y < 80/3. That only holds if
    StatsBomb's y axis runs from the acting team's left touchline to its right
    one. Full-backs and wing-backs from the starting lineups show it: their
    average y must sit in their own channel. Only the first 40 minutes count,
    before substitutions reshuffle positions.
    """
    raw_events = _raw_events()
    side_by_player: dict[int, str] = {}
    for event in raw_events:
        if _type_name(event) != "Starting XI":
            continue
        lineup = cast(list[dict[str, object]], _details(event, "tactics")["lineup"])
        for entry in lineup:
            player_id = cast(int, _details(entry, "player")["id"])
            position = cast(str, _details(entry, "position")["name"])
            if position in LEFT_SIDED_POSITIONS:
                side_by_player[player_id] = "left"
            elif position in RIGHT_SIDED_POSITIONS:
                side_by_player[player_id] = "right"

    y_values: dict[str, list[float]] = {"left": [], "right": []}
    for event in raw_events:
        location = cast(list[float] | None, event.get("location"))
        player = event.get("player")
        minute = cast(int, event["minute"])
        if location is None or player is None or minute >= BEFORE_SUBSTITUTIONS_MINUTE:
            continue
        side = side_by_player.get(cast(int, _details(event, "player")["id"]))
        if side is not None:
            y_values[side].append(location[1])

    assert y_values["left"]
    assert y_values["right"]
    assert fmean(y_values["left"]) < 80 / 3
    assert fmean(y_values["right"]) > 160 / 3
