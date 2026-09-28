"""Smoke tests for the command-line composition root, on synthetic event files."""

import json
from pathlib import Path

import pytest

from regista.cli import build_parser, main
from regista.pipeline.catalog import load_corpus


def statsbomb_record(index: int, minute: int, second: int, **extra: object) -> dict[str, object]:
    """Build a minimal synthetic StatsBomb-shaped record (no provider data is copied)."""
    record: dict[str, object] = {
        "id": f"synthetic-{index}",
        "index": index,
        "period": 1,
        "minute": minute,
        "second": second,
        "type": {"id": 0, "name": "Pressure"},
        "team": {"id": 7, "name": "Home"},
    }
    record.update(extra)
    return record


def entry_record(index: int, minute: int, second: int, end_y: float) -> dict[str, object]:
    return statsbomb_record(
        index,
        minute,
        second,
        type={"id": 30, "name": "Pass"},
        location=[70.0, end_y],
        **{"pass": {"end_location": [85.0, end_y]}},
    )


def shot_record(index: int, minute: int) -> dict[str, object]:
    return statsbomb_record(
        index,
        minute,
        0,
        type={"id": 16, "name": "Shot"},
        location=[105.0, 40.0],
        shot={"type": {"id": 87, "name": "Open Play"}},
    )


def write_match(directory: Path, records: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "1.json").write_text(json.dumps(records))


def test_parser_uses_product_name() -> None:
    assert build_parser().prog == "regista"


def test_empty_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])

    assert exit_code == 0
    assert "Evidence-backed soccer match insights" in capsys.readouterr().out


def test_replay_of_a_quiet_match_says_so_with_attribution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_match(tmp_path, [statsbomb_record(1, 0, 0), statsbomb_record(2, 30, 0)])

    exit_code = main(["replay", "--match", "1", "--events-dir", str(tmp_path)])

    assert exit_code == 0
    assert capsys.readouterr().out == "No cards.\nData: StatsBomb\n"


def test_replay_defaults_to_pinned_corpus_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = Path(__file__).resolve().parents[1] / "catalog/corpus.toml"
    destination = tmp_path / "catalog/corpus.toml"
    destination.parent.mkdir()
    destination.write_bytes(corpus.read_bytes())
    events = (
        tmp_path
        / "data/raw/statsbomb-open-data"
        / load_corpus(corpus).source_commit
        / "data/events"
    )
    write_match(events, [statsbomb_record(1, 0, 0), statsbomb_record(2, 30, 0)])
    monkeypatch.chdir(tmp_path)

    assert main(["replay", "--match", "1"]) == 0
    assert capsys.readouterr().out == "No cards.\nData: StatsBomb\n"


def test_replay_prints_each_card_with_its_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    channel_y = [10.0, 40.0, 70.0]
    baseline = [entry_record(1 + i, *divmod(40 * i, 60), channel_y[i % 3]) for i in range(12)]
    recent = [entry_record(20 + i, 11 + i, 0, 10.0) for i in range(8)]
    write_match(tmp_path, baseline + recent)

    main(["replay", "--match", "1", "--events-dir", str(tmp_path)])

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == (
        "[period 1, 18:00] More of Home's final-third entries are ending on the left: "
        "8 of the last 8 (100%), up from 4 of 12 (33%) earlier."
    )
    assert lines[1] == "  recent entries: " + ", ".join(f"synthetic-{20 + i}" for i in range(8))
    assert lines[2].startswith("  baseline entries: synthetic-1, ")
    assert lines[-1] == "Data: StatsBomb"


def test_replay_merges_burst_and_side_shift_cards_in_replay_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    channel_y = [10.0, 40.0, 70.0]
    baseline = [entry_record(1 + i, *divmod(40 * i, 60), channel_y[i % 3]) for i in range(12)]
    recent = [entry_record(20 + i, 11 + i, 0, 10.0) for i in range(8)]
    shots = [shot_record(40 + i, minute) for i, minute in enumerate((21, 23, 25, 27))]
    write_match(tmp_path, [statsbomb_record(0, 0, 0), *baseline, *recent, *shots])

    main(["replay", "--match", "1", "--events-dir", str(tmp_path)])

    cards = [line for line in capsys.readouterr().out.splitlines() if line.startswith("[")]
    assert cards == [
        "[period 1, 18:00] More of Home's final-third entries are ending on the left: "
        "8 of the last 8 (100%), up from 4 of 12 (33%) earlier.",
        "[period 1, 27:00] Home: 4 shots in the last 10 minutes, after none in the previous "
        "17 minutes of play. Final-third entries in the last 10 minutes: 1.",
    ]


def test_replay_with_evidence_prints_the_channel_table_instead_of_identifiers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    channel_y = [10.0, 40.0, 70.0]
    baseline = [entry_record(1 + i, *divmod(40 * i, 60), channel_y[i % 3]) for i in range(12)]
    recent = [entry_record(20 + i, 11 + i, 0, 10.0) for i in range(8)]
    write_match(tmp_path, baseline + recent)

    main(["replay", "--match", "1", "--events-dir", str(tmp_path), "--evidence"])

    lines = capsys.readouterr().out.splitlines()
    assert lines[1] == "  channel recent          baseline        change"
    assert lines[2] == "  left    8 of 8   100%   4 of 12  33%    +67 points"
    assert "  recent window entries (period 1):" in lines
    assert not any("synthetic-" in line for line in lines)
    assert lines[-1] == "Data: StatsBomb"


def test_provisional_facts_mode_reports_recorded_changes_and_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    players = [{"player": {"id": number, "name": f"Player {number}"}} for number in range(1, 12)]
    records = [
        statsbomb_record(
            1,
            0,
            0,
            type={"id": 0, "name": "Starting XI"},
            tactics={"formation": 433, "lineup": players},
        ),
        statsbomb_record(
            2,
            20,
            0,
            type={"id": 0, "name": "Tactical Shift"},
            tactics={"formation": 433},
        ),
        statsbomb_record(
            3,
            30,
            0,
            type={"id": 0, "name": "Substitution"},
            player={"id": 1, "name": "Player 1"},
            substitution={"replacement": {"id": 12, "name": "Replacement"}},
        ),
        statsbomb_record(
            4,
            31,
            0,
            type={"id": 0, "name": "Tactical Shift"},
            tactics={"formation": 442},
        ),
    ]
    write_match(tmp_path, records)

    assert (
        main(["replay", "--match", "1", "--events-dir", str(tmp_path), "--facts", "--evidence"])
        == 0
    )
    output = capsys.readouterr().out
    assert output.count("[period 1,") == 3
    assert "Home started in a recorded 4-3-3 shape." in output
    assert "Replacement replaced Player 1 for Home." in output
    assert "changed from 4-3-3 to 4-4-2." in output
    assert "starting players: Player 1" in output
    assert "previous formation event: synthetic-2" in output
    assert output.endswith("Data: StatsBomb\n")


def test_replay_of_a_missing_match_exits_with_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["replay", "--match", "99", "--events-dir", str(tmp_path)])

    assert exit_info.value.code == 2
    assert "no event file for match 99" in capsys.readouterr().err


def test_export_refuses_a_held_out_match_before_reading_any_provider_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def must_not_read(*_: object, **__: object) -> None:
        raise AssertionError("a held-out match must be refused before any provider file is read")

    monkeypatch.setattr("regista.cli.load_catalog", must_not_read)
    monkeypatch.setattr("regista.cli.load_events", must_not_read)
    split = tmp_path / "v1.json"
    split.write_text(
        json.dumps(
            {
                "assignments": [
                    {"match_id": 1, "bucket": "development"},
                    {"match_id": 3, "bucket": "test"},
                ]
            }
        )
    )
    output = tmp_path / "exports"

    # A held-out match refuses the whole request, even beside a development match.
    for match in ("3", "404"):
        with pytest.raises(SystemExit):
            main(
                [
                    "export",
                    "--match",
                    "1",
                    "--match",
                    match,
                    "--split-file",
                    str(split),
                    "--output-directory",
                    str(output),
                ]
            )
        assert "development only" in capsys.readouterr().err
    assert not output.exists()
