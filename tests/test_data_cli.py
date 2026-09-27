"""The CLI freezes only verified metadata and reports failures without partial split output."""

import json
from pathlib import Path

import pytest

from regista.adapters.statsbomb.catalog import load_catalog
from regista.cli import main
from regista.domain.catalog import CorpusConfiguration, IndexCatalog


def test_catalog_and_split_commands_end_to_end_on_synthetic_indexes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    corpus = tmp_path / "corpus.toml"
    corpus.write_text(
        'provider = "statsbomb"\ndataset = "open-data"\nsource_commit = "' + "a" * 40 + '"\n'
        "inspected_match_ids = []\nreview_seed = 42\n"
        "[[competition_seasons]]\ncompetition_id = 1\nseason_id = 2\n"
        'role = "modern_robustness"\ncoverage = "tournament"\nexpected_matches = 3\n'
    )
    requests: list[str] = []

    def fetch(url: str) -> bytes:
        requests.append(url)
        if url.endswith("competitions.json"):
            return b'[{"competition_id":1,"season_id":2}]'
        return json.dumps(
            [
                {
                    "match_id": number,
                    "competition": {"competition_id": 1},
                    "season": {"season_id": 2},
                    "match_date": f"2020-01-0{number}",
                    "kick_off": "12:00:00",
                    "match_status": "available",
                }
                for number in (1, 2, 3)
            ]
        ).encode()

    def adapter(
        configuration: CorpusConfiguration, raw_directory: Path, *, download: bool = False
    ) -> IndexCatalog:
        return load_catalog(configuration, raw_directory, download=download, fetch=fetch)

    monkeypatch.setattr("regista.cli.load_catalog", adapter)
    common = ["--corpus", str(corpus), "--raw-directory", str(tmp_path / "raw")]
    assert main(["data", "catalog", *common]) == 0
    assert "Verified 3 matches" in capsys.readouterr().out
    assert len(requests) == 2
    split_arguments = [
        "data",
        "split",
        *common,
        "--output-directory",
        str(tmp_path / "splits"),
        "--reason",
        "Initial synthetic split",
    ]
    assert main(split_arguments) == 0
    assert "Created immutable split" in capsys.readouterr().out
    assert len(requests) == 2
    contents = (tmp_path / "splits/v1.json").read_bytes()
    with pytest.raises(SystemExit) as error:
        main(split_arguments)
    assert error.value.code == 2
    assert "cannot be edited" in capsys.readouterr().err
    assert (tmp_path / "splits/v1.json").read_bytes() == contents

    downloads: list[str] = []

    def fetch_payload(url: str) -> bytes:
        downloads.append(url)
        return b"[]"

    monkeypatch.setattr("regista.cli.fetch_payload", fetch_payload)
    download_arguments = [
        "data",
        "download",
        *common,
        "--split-file",
        str(tmp_path / "splits/v1.json"),
        "--competition",
        "1",
        "--season",
        "2",
        "--report",
        str(tmp_path / "report.json"),
    ]
    assert main([*download_arguments, "--dry-run"]) == 0
    assert not (tmp_path / "raw/manifest.jsonl").exists()
    assert not downloads
    assert main(download_arguments) == 0
    assert len(downloads) == 2
    assert all(url.endswith("/1.json") for url in downloads)
    original_manifest = (tmp_path / "raw/manifest.jsonl").read_bytes()
    assert main([*download_arguments, "--verify-only"]) == 0
    assert len(downloads) == 2
    assert (tmp_path / "raw/manifest.jsonl").read_bytes() == original_manifest
    with pytest.raises(SystemExit):
        main([*download_arguments, "--match", "3"])
    assert len(downloads) == 2


def test_split_without_local_provenance_fails_without_creating_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        main(
            [
                "data",
                "split",
                "--raw-directory",
                str(tmp_path / "raw"),
                "--output-directory",
                str(tmp_path / "splits"),
                "--reason",
                "Initial split",
            ]
        )
    assert error.value.code == 2
    assert "metadata has not been acquired" in capsys.readouterr().err
    assert not (tmp_path / "splits").exists()


def _remote_files(tmp_path: Path) -> list[str]:
    corpus = tmp_path / "corpus.toml"
    corpus.write_text(
        'provider = "statsbomb"\ndataset = "open-data"\nsource_commit = "' + "a" * 40 + '"\n'
        "inspected_match_ids = []\nreview_seed = 42\n"
        "[[competition_seasons]]\ncompetition_id = 1\nseason_id = 2\n"
        'role = "modern_robustness"\ncoverage = "tournament"\nexpected_matches = 3\n'
    )
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
    return ["--corpus", str(corpus), "--split-file", str(split)]


def test_remote_pull_refuses_held_out_matches_before_reading_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_store() -> None:
        raise AssertionError("credentials must not be read for a refused selection")

    monkeypatch.setattr("regista.cli.R2Store.from_environment", no_store)

    with pytest.raises(SystemExit):
        main(["data", "remote", "pull", *_remote_files(tmp_path), "--match", "3"])
    assert "held out" in capsys.readouterr().err


def test_remote_commands_name_missing_credentials_without_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("REGISTA_R2_ACCOUNT_ID", "REGISTA_R2_ACCESS_KEY_ID", "REGISTA_R2_BUCKET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REGISTA_R2_SECRET_ACCESS_KEY", "never-print-this-secret")

    with pytest.raises(SystemExit):
        main(["data", "remote", "verify", *_remote_files(tmp_path)])
    error = capsys.readouterr().err
    assert "REGISTA_R2_BUCKET" in error
    assert "never-print-this-secret" not in error
