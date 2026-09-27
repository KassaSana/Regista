"""Warehouse builds of a hand-computed synthetic match: quality, analytics, determinism."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path

import duckdb
import pytest
from synthetic_warehouse import (
    AWAY,
    HOME,
    Record,
    SyntheticMatch,
    build_warehouse,
    standard_match,
    without_player,
)

from regista.adapters.statsbomb.events import events_from_payload
from regista.cli import main
from regista.domain.entries import channel_of, is_final_third_entry
from regista.domain.ids import MatchId
from regista.warehouse.research import connect_research, fingerprint


def query(path: Path, sql: str) -> list[tuple[object, ...]]:
    with connect_research(path) as connection:
        return connection.execute(sql).fetchall()


@pytest.fixture(scope="module")
def standard(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_warehouse(tmp_path_factory.mktemp("standard"), [standard_match()]).path


# Quiet case ----------------------------------------------------------------------------------


def test_the_standard_match_passes_every_check_and_is_normalized(standard: Path) -> None:
    failed = query(standard, "SELECT check_name FROM normalized.dq_checks WHERE NOT passed")
    assert failed == []
    assert query(standard, "SELECT dq_status FROM normalized.matches") == [("passed",)]
    assert query(standard, "SELECT count(*) FROM normalized.events") == [(1020,)]
    counts = query(
        standard,
        "SELECT (SELECT count(*) FROM normalized.passes), (SELECT count(*) FROM normalized.shots),"
        " (SELECT count(*) FROM normalized.carries), (SELECT count(*) FROM normalized.goals),"
        " (SELECT count(*) FROM normalized.substitutions),"
        " (SELECT count(*) FROM normalized.formation_changes)",
    )
    assert counts == [(4, 1, 1, 2, 1, 3)]


def test_every_row_carries_the_run_and_original_records_are_kept(standard: Path) -> None:
    assert query(standard, "SELECT DISTINCT ingest_run_id FROM normalized.events") == [
        ("synthetic-run",)
    ]
    record = query(
        standard, "SELECT provider_record->>'$.type.name' FROM normalized.events WHERE sequence = 1"
    )
    assert record == [("Starting XI",)]


# Analytical values, computed by hand ---------------------------------------------------------


def test_final_third_and_box_entries(standard: Path) -> None:
    entries = query(
        standard,
        "SELECT team_id, period, time_bin, channel, event_type, player_id "
        "FROM analytical.final_third_entries ORDER BY period",
    )
    assert entries == [(1, 1, 0, "left", "pass", 11), (1, 2, 2, "right", "carry", 12)]
    box = query(standard, "SELECT period, period_seconds, end_x FROM analytical.box_entries")
    assert box == [(1, 120, 110.0)]


def test_team_time_bins_count_every_bin_and_field_tilt(standard: Path) -> None:
    assert query(standard, "SELECT count(*) FROM analytical.team_time_bins") == [(40,)]
    home = query(
        standard,
        "SELECT pass_attempts, completed_passes, entries_left, box_entries, tilt_passes, "
        "opponent_tilt_passes, field_tilt, shots, provider_xg, goals "
        "FROM analytical.team_time_bins WHERE team_id = 1 AND period = 1 AND time_bin = 0",
    )
    assert home == [(2, 2, 1, 1, 1, 0, 1.0, 1, pytest.approx(0.25), 1)]
    away = query(
        standard,
        "SELECT pass_attempts, set_piece_passes, tilt_passes, field_tilt "
        "FROM analytical.team_time_bins WHERE team_id = 2 AND period = 1 AND time_bin = 0",
    )
    # The corner starts in the final third but is a set piece, so it is not a tilt pass.
    assert away == [(1, 1, 0, 0.0)]
    empty = query(
        standard,
        "SELECT pass_attempts, field_tilt FROM analytical.team_time_bins "
        "WHERE team_id = 1 AND period = 1 AND time_bin = 5",
    )
    assert empty == [(0, None)]


def test_score_states_count_goals_before_each_event_including_own_goals(standard: Path) -> None:
    rows = query(
        standard,
        "SELECT e.provider_event_type, s.home_score_before, s.away_score_before "
        "FROM analytical.score_states AS s JOIN normalized.events AS e USING (event_id) "
        "WHERE e.provider_event_type IN ('Shot', 'Own Goal For', 'Carry') ORDER BY s.sequence",
    )
    assert rows == [("Shot", 0, 0), ("Own Goal For", 1, 0), ("Carry", 1, 1)]
    states = query(
        standard,
        "SELECT provider_event_type, score_state FROM analytical.event_context "
        "WHERE provider_event_type = 'Shot' OR (provider_event_type = 'Pass' AND team_id = 2) "
        "ORDER BY sequence",
    )
    # The away corner (3:20) comes after the home goal (2:10): away trails.
    assert states == [("Shot", "level"), ("Pass", "trailing")]


def test_player_minutes_and_involvement(standard: Path) -> None:
    rows = query(
        standard,
        "SELECT player_id, started, seconds_on_pitch, pass_attempts, team_pass_attempts_while_on, "
        "pass_share, shots, goals, final_third_entries, box_entries "
        "FROM analytical.player_match_involvement WHERE team_id = 1 ORDER BY player_id",
    )
    assert rows == [
        (10, True, 5500, 0, 3, 0.0, 0, 0, 0, 0),
        (11, True, 3300, 2, 2, 1.0, 1, 1, 1, 1),
        (12, False, 2200, 1, 1, 1.0, 0, 0, 1, 0),
        (13, False, 0, 0, 0, None, 0, 0, 0, 0),
    ]
    bins = query(
        standard,
        "SELECT sum(seconds_on_pitch) FROM analytical.player_time_bins WHERE player_id = 12",
    )
    assert bins == [(2200,)]


def test_team_match_summary_reconciles_with_the_final_score(standard: Path) -> None:
    rows = query(
        standard,
        "SELECT team_id, goals_for, goals_from_events, final_third_entries, box_entries, "
        "field_tilt, possessions FROM analytical.team_match_summary ORDER BY team_id",
    )
    assert rows == [(1, 1, 1, 2, 1, 1.0, 1), (2, 1, 1, 0, 0, 0.0, 0)]


# Firing cases: each check fails on a match built to break it ---------------------------------


def _mutated(mutate: Callable[[list[Record]], None]) -> SyntheticMatch:
    match = standard_match()
    match.mutate = mutate
    return match


def _index_gap(records: list[Record]) -> None:
    for record in records[500:]:
        record["index"] = int(str(record["index"])) + 1


def _clock_regression(records: list[Record]) -> None:
    records[900]["timestamp"] = "00:00:00.100"


def _off_pitch(records: list[Record]) -> None:
    records[900]["location"] = [121.0, 40.0]


def _score_mismatch() -> SyntheticMatch:
    match = standard_match()
    match.home_score = 2
    return match


def _few_events() -> SyntheticMatch:
    return standard_match(filler=0)


def _home_only() -> SyntheticMatch:
    match = standard_match()
    match.events = [item for item in match.events if item[2]["team"] == HOME]
    return match


def _substitute_missing() -> SyntheticMatch:
    match = standard_match()
    match.lineups = without_player(match.lineups, 12)
    return match


def _unlisted_player() -> SyntheticMatch:
    match = standard_match()
    match.add(1, 400.0, "Pressure", AWAY, player=99, location=(50.0, 40.0))
    return match


def _no_metadata() -> SyntheticMatch:
    match = standard_match()
    match.data_version = None
    return match


def _lineup_ignores_substitution() -> SyntheticMatch:
    match = standard_match()
    lineups = copy.deepcopy(match.lineups)
    player = lineups[0]["lineup"][1]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    player["positions"][0].update({"to": None, "to_period": None})  # pyright: ignore[reportUnknownMemberType]
    match.lineups = lineups
    return match


def _overlapping_spells() -> SyntheticMatch:
    match = standard_match()
    lineups = copy.deepcopy(match.lineups)
    player = lineups[0]["lineup"][0]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    player["positions"] = [  # pyright: ignore[reportIndexIssue]
        {**player["positions"][0], "to": "90:00", "to_period": 2},  # pyright: ignore[reportIndexIssue, reportUnknownMemberType]
        {**player["positions"][0], "from": "30:00", "from_period": 1},  # pyright: ignore[reportIndexIssue, reportUnknownMemberType]
    ]
    match.lineups = lineups
    return match


FIRING_CASES: dict[str, tuple[Callable[[], SyntheticMatch], str, str]] = {
    "score_reconciles": (_score_mismatch, "blocking", "events 1-1, match index 2-1"),
    "sequence_contiguous": (lambda: _mutated(_index_gap), "blocking", "sequence 1..1021"),
    "event_count_plausible": (_few_events, "blocking", "20 events"),
    "teams_present": (_home_only, "blocking", "1 teams"),
    "substitutes_in_lineup": (_substitute_missing, "blocking", "1 substitution players"),
    "clock_monotonic": (lambda: _mutated(_clock_regression), "warning", "1 backward steps"),
    "coordinates_on_pitch": (lambda: _mutated(_off_pitch), "warning", "1 events"),
    "provider_metadata_present": (_no_metadata, "warning", "data missing"),
    "substitution_ends_lineup_spell": (_lineup_ignores_substitution, "warning", "1 substituted"),
    "position_spells_consistent": (_overlapping_spells, "warning", "1 spells"),
    "event_players_in_lineup": (_unlisted_player, "warning", "1 event players"),
}


@pytest.mark.parametrize("check", sorted(FIRING_CASES))
def test_each_quality_check_fires_on_a_broken_match(tmp_path: Path, check: str) -> None:
    make, severity, detail = FIRING_CASES[check]
    path = build_warehouse(tmp_path, [make()]).path

    rows = query(
        path,
        f"SELECT severity, passed, detail FROM normalized.dq_checks WHERE check_name = '{check}'",
    )
    assert len(rows) == 1
    assert rows[0][:2] == (severity, False)
    assert detail in str(rows[0][2])
    status = query(path, "SELECT dq_status FROM normalized.matches")[0][0]
    included = query(path, "SELECT count(*) FROM analytical.team_matches")[0][0]
    if severity == "blocking":
        assert (status, included) == ("excluded", 0)
    else:
        assert (status, included) == ("passed_with_warnings", 2)


def test_a_lineup_that_ignores_a_substitution_is_cut_at_the_substitution(tmp_path: Path) -> None:
    path = build_warehouse(tmp_path, [_lineup_ignores_substitution()]).path

    rows = query(
        path,
        "SELECT end_period, end_period_seconds, cut_by_substitution "
        "FROM analytical.player_intervals WHERE player_id = 11",
    )
    assert rows == [(2, 600, True)]
    assert query(path, "SELECT lineup_consistent FROM analytical.team_matches LIMIT 1") == [
        (False,)
    ]


def test_overlapping_spells_are_merged_not_double_counted(tmp_path: Path) -> None:
    path = build_warehouse(tmp_path, [_overlapping_spells()]).path

    seconds = query(
        path,
        "SELECT seconds_on_pitch FROM analytical.player_match_involvement WHERE player_id = 10",
    )
    assert seconds == [(5500,)]


def test_checksum_and_adapter_failures_are_recorded_and_other_matches_still_load(
    tmp_path: Path,
) -> None:
    unknown = standard_match(match_id=102)
    unknown.add(1, 50.0, "Teleport", HOME)

    def corrupt(match_id: int, kind: str, contents: bytes) -> bytes:
        return contents + b" " if (match_id, kind) == (101, "lineups") else contents

    built = build_warehouse(
        tmp_path, [standard_match(100), standard_match(101), unknown], corrupt=corrupt
    )

    assert built.summary.normalized == 1
    assert sorted(built.summary.excluded) == [MatchId(101), MatchId(102)]
    failures = query(
        built.path,
        "SELECT match_id, check_name FROM normalized.dq_checks WHERE NOT passed ORDER BY match_id",
    )
    assert failures == [(101, "raw_checksum"), (102, "adapter_validation")]
    statuses = query(built.path, "SELECT match_id, dq_status FROM normalized.matches ORDER BY 1")
    assert statuses == [(100, "passed"), (101, "excluded"), (102, "excluded")]
    assert query(built.path, "SELECT DISTINCT match_id FROM analytical.team_matches") == [(100,)]


# Determinism, isolation, and the definition contract -----------------------------------------


def test_two_builds_from_the_same_inputs_have_identical_fingerprints(tmp_path: Path) -> None:
    matches = [standard_match(100), standard_match(101)]
    first = build_warehouse(tmp_path / "a", matches).path
    second = build_warehouse(tmp_path / "b", matches).path

    assert fingerprint(first) == fingerprint(second)
    assert main(["data", "fingerprint", "--warehouse", str(first), "--compare", str(second)]) == 0


def test_a_changed_input_changes_the_fingerprint(tmp_path: Path) -> None:
    first = build_warehouse(tmp_path / "a", [standard_match()]).path
    changed = standard_match()
    changed.add(1, 400.0, "Pressure", AWAY, player=20, location=(50.0, 40.0))
    second = build_warehouse(tmp_path / "b", [changed]).path

    assert fingerprint(first)["normalized.events"] != fingerprint(second)["normalized.events"]


def test_research_connections_cannot_read_outside_files(standard: Path, tmp_path: Path) -> None:
    outside = tmp_path / "held_out.json"
    outside.write_text(json.dumps([{"secret": 1}]))

    with connect_research(standard) as connection:
        with pytest.raises(duckdb.Error):
            connection.execute(f"SELECT * FROM read_json('{outside}')").fetchall()
        with pytest.raises(duckdb.Error):
            connection.execute("CREATE TABLE analytical.scratch (x INTEGER)")


def test_sql_final_third_entries_match_the_domain_definition(tmp_path: Path) -> None:
    match = standard_match()
    boundary = (
        ((79.9, 10.0), (80.0, 80 / 3)),  # ends exactly on x = 80 and the left/center boundary
        ((80.0, 40.0), (95.0, 40.0)),  # starts on x = 80: not an entry
        ((60.0, 40.0), (100.0, 160 / 3)),  # ends on the center/right boundary
        ((60.0, 40.0), (100.0, 53.34)),  # just right of the boundary
        ((79.99, 70.0), (80.01, 79.9)),
    )
    for number, (start, end) in enumerate(boundary):
        match.add(
            1,
            300.0 + number,
            "Pass",
            HOME,
            player=11,
            location=start,
            **{"pass": {"end_location": list(end)}},
        )
        match.add(
            1,
            310.0 + number,
            "Carry",
            AWAY,
            player=20,
            location=start,
            carry={"end_location": list(end)},
        )
    path = build_warehouse(tmp_path, [match]).path

    events = events_from_payload(match.records(), MatchId(100), "synthetic")
    expected = {
        (str(event.identifier), channel_of(event.movement.end).value)
        for event in events
        if event.movement is not None and is_final_third_entry(event)
    }
    actual = {
        (str(event_id), str(channel))
        for event_id, channel in query(
            path, "SELECT event_id, channel FROM analytical.final_third_entries"
        )
    }
    assert actual == expected
    assert len(expected) == 2 + 8


def test_quality_command_writes_a_readable_report(standard: Path, tmp_path: Path) -> None:
    assert (
        main(["data", "quality", "--warehouse", str(standard), "--report-directory", str(tmp_path)])
        == 0
    )

    report = (tmp_path / "latest.md").read_text()
    assert "passed: 1" in report
    summary = json.loads((tmp_path / "latest.json").read_text())
    assert summary["failures"] == []
