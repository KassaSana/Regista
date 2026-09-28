"""Whole-match StatsBomb normalization: type mapping, clocks, lineups, and derived goals."""

from __future__ import annotations

import json

import pytest
from synthetic_warehouse import HOME, standard_match

from regista.adapters.statsbomb.events import (
    ACTIONS_BY_TYPE_NAME,
    StatsBombFormatError,
    normalize_event,
)
from regista.adapters.statsbomb.lineups import (
    LineupFormatError,
    continuous_clock_to_period_seconds,
)
from regista.adapters.statsbomb.normalize import normalize_match, timestamp_seconds
from regista.domain.events import ActionType
from regista.domain.ids import MatchId


def _normalize(match_payload: object, lineups: object) -> object:
    match = standard_match()
    return normalize_match(
        match.record(), json.dumps(match_payload).encode(), json.dumps(lineups).encode()
    )


@pytest.mark.parametrize(
    "type_name",
    sorted(name for name in ACTIONS_BY_TYPE_NAME if name not in ("Pass", "Carry")),
)
def test_every_known_provider_type_maps_to_a_regista_type(type_name: str) -> None:
    record = {
        "id": "e",
        "index": 1,
        "period": 1,
        "minute": 0,
        "second": 0,
        "type": {"id": 0, "name": type_name},
        "team": HOME,
    }
    if type_name in ("Starting XI", "Tactical Shift"):
        record["tactics"] = {
            "formation": 433,
            "lineup": [
                {"player": {"id": identifier, "name": f"Player {identifier}"}}
                for identifier in range(1, 12)
            ],
        }
    elif type_name == "Substitution":
        record["player"] = {"id": 1, "name": "Player One"}
        record["substitution"] = {"replacement": {"id": 12, "name": "Player Twelve"}}
    elif type_name == "Shot":
        record["shot"] = {"type": {"id": 87, "name": "Open Play"}}

    assert normalize_event(record, MatchId(1)).action is ACTIONS_BY_TYPE_NAME[type_name]


@pytest.mark.parametrize(
    ("shot_type", "penalty"),
    [("Open Play", False), ("Free Kick", False), ("Corner", False), ("Penalty", True)],
)
def test_shot_type_marks_only_penalties(shot_type: str, penalty: bool) -> None:
    record = {
        "id": "e",
        "index": 1,
        "period": 1,
        "minute": 0,
        "second": 0,
        "type": {"id": 16, "name": "Shot"},
        "team": HOME,
        "location": [100.0, 40.0],
        "shot": {"type": {"id": 0, "name": shot_type}},
    }

    shot = normalize_event(record, MatchId(1)).shot
    assert shot is not None
    assert shot.penalty is penalty


def test_an_unknown_shot_type_fails_loudly() -> None:
    record = {
        "id": "e",
        "index": 1,
        "period": 1,
        "minute": 0,
        "second": 0,
        "type": {"id": 16, "name": "Shot"},
        "team": HOME,
        "shot": {"type": {"id": 0, "name": "Rabona Special"}},
    }

    with pytest.raises(StatsBombFormatError, match="unknown shot type"):
        normalize_event(record, MatchId(1))


def test_an_unknown_provider_type_fails_loudly() -> None:
    record = {
        "id": "e",
        "index": 1,
        "period": 1,
        "minute": 0,
        "second": 0,
        "type": {"id": 0, "name": "Teleport"},
        "team": HOME,
    }

    with pytest.raises(StatsBombFormatError, match="unknown event type 'Teleport'"):
        normalize_event(record, MatchId(1))


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("00:00:00.000", 0.0), ("00:47:13.580", 2833.58), ("01:02:03.5", 3723.5), ("00:00:01", 1.0)],
)
def test_timestamps_convert_to_period_seconds_to_the_millisecond(
    value: str, seconds: float
) -> None:
    assert timestamp_seconds(value) == seconds


@pytest.mark.parametrize("value", ["47:13.580", "00:47:13.5801", "00:aa:13.000", 12])
def test_malformed_timestamps_are_rejected(value: object) -> None:
    with pytest.raises(StatsBombFormatError):
        timestamp_seconds(value)


@pytest.mark.parametrize(
    ("clock", "period", "seconds"),
    [("00:00", 1, 0), ("47:10", 1, 2830), ("45:00", 2, 0), ("60:30", 2, 930), ("105:01", 4, 1)],
)
def test_continuous_lineup_clocks_become_period_seconds(
    clock: str, period: int, seconds: int
) -> None:
    assert continuous_clock_to_period_seconds(clock, period) == seconds


@pytest.mark.parametrize(
    ("clock", "period"), [("44:59", 2), ("10:61", 1), ("1:2:3", 1), ("00:00", 6)]
)
def test_impossible_lineup_clocks_are_rejected(clock: str, period: int) -> None:
    with pytest.raises(LineupFormatError):
        continuous_clock_to_period_seconds(clock, period)


def test_a_whole_match_normalizes_into_provider_neutral_rows() -> None:
    match = standard_match()
    normalized = normalize_match(
        match.record(), json.dumps(match.records()).encode(), json.dumps(match.lineups).encode()
    )

    assert len(normalized.events) == 1020
    assert [goal.kind for goal in normalized.goals] == ["shot", "own_goal"]
    # "Own Goal For" is credited to the team on that event (the away team here).
    assert [goal.scoring_team_id for goal in normalized.goals] == [1, 2]
    assert [(row.kind, row.formation) for row in normalized.formation_changes] == [
        ("starting", "442"),
        ("starting", "433"),
        ("tactical_shift", "4231"),
    ]
    (substitution,) = normalized.substitutions
    assert (substitution.player_off_id, substitution.player_on_id, substitution.reason) == (
        11,
        12,
        "Tactical",
    )
    corner = next(row for row in normalized.passes if row.set_piece_type == "Corner")
    assert not corner.open_play
    incomplete = next(row for row in normalized.passes if row.outcome == "Incomplete")
    assert not incomplete.completed
    (shot,) = normalized.shots
    assert (shot.provider_xg, shot.is_goal, shot.end_z) == (0.25, True, 1.0)
    started = {row.player_id: row.started for row in normalized.appearances}
    assert started == {10: True, 11: True, 12: False, 13: False, 20: True}
    spell = next(row for row in normalized.position_spells if row.player_id == 11)
    assert (spell.end_period, spell.end_period_seconds) == (2, 600)
    shot_row = next(row for row in normalized.events if row.provider_event_type == "Shot")
    assert (shot_row.event.action, shot_row.period_seconds, shot_row.player_id) == (
        ActionType.SHOT,
        130.0,
        11,
    )


def test_an_event_for_a_team_outside_the_match_is_rejected() -> None:
    match = standard_match()
    match.add(1, 5.0, "Pressure", {"id": 9, "name": "Intruders"})

    with pytest.raises(StatsBombFormatError, match="not in the match"):
        _normalize(match.records(), match.lineups)


def test_lineups_must_list_exactly_the_two_match_teams() -> None:
    match = standard_match()

    with pytest.raises(LineupFormatError, match="both teams"):
        _normalize(match.records(), match.lineups[:1])
    stranger: list[dict[str, object]] = [
        *match.lineups,
        {"team_id": 9, "team_name": "Intruders", "lineup": []},
    ]
    with pytest.raises(LineupFormatError, match="does not play"):
        _normalize(match.records(), stranger)
