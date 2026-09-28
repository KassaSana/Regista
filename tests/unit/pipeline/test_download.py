import hashlib
import json
from datetime import date, time
from pathlib import Path

import pytest

from regista.domain.acquisition import RawFileRequest
from regista.domain.catalog import (
    CompetitionSeason,
    CorpusConfiguration,
    IndexCatalog,
    IndexSource,
    MatchIndex,
)
from regista.pipeline.download import acquire_files, acquisition_lock, select_development_matches
from regista.pipeline.splits import freeze_splits


def request(path: str = "events/1.json", body: bytes | None = None) -> RawFileRequest:
    return RawFileRequest(
        "statsbomb",
        "open-data",
        "a" * 40,
        path,
        "https://example.invalid/" + path,
        "events",
        1,
        "2024-01-01",
        "research",
        "development",
        "split",
        hashlib.sha256(body).hexdigest() if body is not None else None,
    )


def test_resume_verifies_receipt_without_fetching_and_rejects_tampering(tmp_path: Path) -> None:
    body = b"[]"
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return body

    target = tmp_path / "events/1.json"
    first = acquire_files([request(body=body)], tmp_path, fetch)
    assert first.downloaded == 1
    second = acquire_files([request(body=body)], tmp_path, fetch, verify_only=True)
    assert second.verified == 1
    assert calls == ["https://example.invalid/events/1.json"]
    assert len((tmp_path / "manifest.jsonl").read_text().splitlines()) == 1
    target.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        acquire_files([request(body=body)], tmp_path, fetch)


def test_missing_manifested_file_is_restored_only_with_matching_hash(tmp_path: Path) -> None:
    body = b"[]"
    acquire_files([request(body=body)], tmp_path, lambda _: body)
    (tmp_path / "events/1.json").unlink()
    with pytest.raises(ValueError, match="redownload differs"):
        acquire_files([request(body=body)], tmp_path, lambda _: b"different")
    result = acquire_files([request(body=body)], tmp_path, lambda _: body)
    assert result.restored == 1
    assert (tmp_path / "events/1.json").read_bytes() == body
    assert len((tmp_path / "manifest.jsonl").read_text().splitlines()) == 1


def test_orphan_is_registered_only_after_identical_source_recovery(tmp_path: Path) -> None:
    body = b"[]"
    target = tmp_path / "events/1.json"
    target.parent.mkdir()
    target.write_bytes(body)
    with pytest.raises(FileExistsError):
        acquire_files([request()], tmp_path, lambda _: b"conflicting")
    result = acquire_files([request()], tmp_path, lambda _: body)
    assert result.downloaded == 1
    assert (
        json.loads((tmp_path / "manifest.jsonl").read_text())["sha256"]
        == hashlib.sha256(body).hexdigest()
    )


def test_incomplete_manifest_fails_closed_and_verify_only_requires_receipt(tmp_path: Path) -> None:
    (tmp_path / "manifest.jsonl").write_bytes(b'{"relative_path":"partial"}')
    with pytest.raises(ValueError, match="incomplete"):
        acquire_files([request()], tmp_path, lambda _: b"[]")
    (tmp_path / "manifest.jsonl").unlink()
    with pytest.raises(ValueError, match="no manifest receipt"):
        acquire_files([request()], tmp_path, lambda _: b"[]", verify_only=True)


def _synthetic_catalog() -> tuple[CorpusConfiguration, IndexCatalog]:
    configuration = CorpusConfiguration(
        "statsbomb",
        "open-data",
        "a" * 40,
        (CompetitionSeason(1, 1, "modern_robustness", "complete_season", 20),),
        (),
        17,
        "b" * 64,
    )
    matches = tuple(
        MatchIndex(
            index,
            1,
            1,
            date(2020, 1, index),
            time(12),
            False,
            (),
        )
        for index in range(1, 21)
    )
    source = IndexSource(
        "data/competitions.json", "https://example.invalid/index", "c" * 64, 2, "now"
    )
    return configuration, IndexCatalog(matches, (source,))


def test_selection_rejects_heldout_and_tampered_frozen_splits(tmp_path: Path) -> None:
    configuration, catalog = _synthetic_catalog()
    path, assignments = freeze_splits(
        configuration, catalog, tmp_path, version=1, reason="synthetic test"
    )
    heldout = next(row.match_id for row in assignments if row.bucket != "development")
    with pytest.raises(ValueError, match="held out"):
        select_development_matches(configuration, catalog, path, match_ids=[heldout])
    document = json.loads(path.read_text())
    document["assignments"][0]["bucket"] = "test"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="assignments do not match"):
        select_development_matches(configuration, catalog, path, match_ids=[1])


def test_acquisition_refuses_concurrent_manifest_writers(tmp_path: Path) -> None:
    with (
        acquisition_lock(tmp_path),
        pytest.raises(ValueError, match="another acquisition process"),
    ):
        acquire_files([request()], tmp_path, lambda _: b"[]")
    assert not (tmp_path / "manifest.jsonl").exists()


def test_path_escape_is_rejected_before_fetch(tmp_path: Path) -> None:
    def fetch(_: str) -> bytes:
        raise AssertionError("network must not be reached")

    with pytest.raises(ValueError, match="beneath the raw directory"):
        acquire_files([request("../escaped.json")], tmp_path, fetch)


def test_selection_rejects_unsupported_split_rules(tmp_path: Path) -> None:
    configuration, catalog = _synthetic_catalog()
    path, _ = freeze_splits(configuration, catalog, tmp_path, version=1, reason="synthetic test")
    document = json.loads(path.read_text())
    document["rule"] = "unsupported-future-rule"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="unsupported split"):
        select_development_matches(configuration, catalog, path, match_ids=[1])


def test_selection_accepts_several_competition_seasons_and_rejects_unknown_ones(
    tmp_path: Path,
) -> None:
    configuration, catalog = _synthetic_catalog()
    path, assignments = freeze_splits(
        configuration, catalog, tmp_path, version=1, reason="synthetic test"
    )
    key = catalog.matches[0].season_key
    by_pair, _ = select_development_matches(
        configuration, catalog, path, competition_id=key[0], season_id=key[1]
    )
    by_keys, _ = select_development_matches(configuration, catalog, path, season_keys=[key])

    assert by_keys == by_pair
    assert {match.match_id for match in by_keys} == {
        row.match_id for row in assignments if row.bucket == "development"
    }
    with pytest.raises(ValueError, match="absent from the corpus"):
        select_development_matches(configuration, catalog, path, season_keys=[key, (999, 1)])
