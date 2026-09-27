"""Synthetic metadata verifies acquisition bounds, provider contracts, and tamper rejection."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from regista.adapters.statsbomb.catalog import load_catalog
from regista.domain.catalog import CompetitionSeason, CorpusConfiguration
from regista.pipeline.catalog import load_corpus, write_once


def configuration() -> CorpusConfiguration:
    return CorpusConfiguration(
        "statsbomb",
        "open-data",
        "a" * 40,
        (CompetitionSeason(1, 2, "modern_robustness", "tournament", 3),),
        (1,),
        42,
        "b" * 64,
    )


def records() -> list[dict[str, object]]:
    return [
        {
            "match_id": index,
            "competition": {"competition_id": 1},
            "season": {"season_id": 2},
            "match_date": f"2020-01-0{index}",
            "kick_off": "12:00:00.000",
            "match_status": "available",
            "match_status_360": "available" if index == 1 else "unscheduled",
            "metadata": {
                "data_version": "1",
                "xy_fidelity_version": "2",
                "shot_fidelity_version": "2",
            },
            "home_score": 999,
            "home_team": {"name": "Not part of split input"},
        }
        for index in (1, 2, 3)
    ]


def fetch_fixture(url: str) -> bytes:
    if url.endswith("data/competitions.json"):
        return json.dumps([{"competition_id": 1, "season_id": 2}]).encode()
    assert url.endswith("data/matches/1/2.json")
    assert "/" + "a" * 40 + "/" in url
    return json.dumps(records()).encode()


def test_downloads_only_indexes_and_reuses_verified_local_metadata(tmp_path: Path) -> None:
    requests: list[str] = []

    def fetch(url: str) -> bytes:
        requests.append(url)
        return fetch_fixture(url)

    catalog = load_catalog(configuration(), tmp_path, download=True, fetch=fetch)
    assert len(requests) == 2
    assert len(catalog.matches) == 3
    assert sum(match.has_three_sixty for match in catalog.matches) == 1
    assert not any(match.missing_metadata for match in catalog.matches)
    assert load_catalog(configuration(), tmp_path, download=True, fetch=fetch) == catalog
    assert len(requests) == 2
    assert all("/events/" not in path.as_posix() for path in tmp_path.rglob("*"))


def test_changed_raw_metadata_is_rejected_even_when_download_is_requested(tmp_path: Path) -> None:
    load_catalog(configuration(), tmp_path, download=True, fetch=fetch_fixture)
    path = tmp_path / "statsbomb-open-data" / ("a" * 40) / "data/matches/1/2.json"
    path.write_text("[]")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_catalog(configuration(), tmp_path, download=True, fetch=fetch_fixture)


def test_missing_metadata_is_reported_without_inventing_a_value(tmp_path: Path) -> None:
    def fetch(url: str) -> bytes:
        if url.endswith("competitions.json"):
            return fetch_fixture(url)
        matches = records()
        matches[0].pop("metadata")
        return json.dumps(matches).encode()

    catalog = load_catalog(configuration(), tmp_path, download=True, fetch=fetch)
    assert catalog.matches[0].missing_metadata == (
        "data_version",
        "xy_fidelity_version",
        "shot_fidelity_version",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("match_id", True),
        ("match_date", "not-a-date"),
        ("kick_off", "12:00:00+00:00"),
        ("match_status", "scheduled"),
        ("season", {"season_id": 3}),
        ("match_status_360", "new-provider-value"),
    ],
)
def test_provider_assumptions_fail_loudly(tmp_path: Path, field: str, value: object) -> None:
    def fetch(url: str) -> bytes:
        if url.endswith("competitions.json"):
            return fetch_fixture(url)
        matches = records()
        matches[0][field] = value
        return json.dumps(matches).encode()

    with pytest.raises(ValueError):
        load_catalog(configuration(), tmp_path, download=True, fetch=fetch)


def test_duplicate_identifiers_and_missing_inspected_matches_fail(tmp_path: Path) -> None:
    def fetch(url: str) -> bytes:
        if url.endswith("competitions.json"):
            return fetch_fixture(url)
        matches = records()
        matches[1]["match_id"] = 1
        return json.dumps(matches).encode()

    with pytest.raises(ValueError, match="unique"):
        load_catalog(configuration(), tmp_path / "duplicates", download=True, fetch=fetch)
    with pytest.raises(ValueError, match="already-inspected"):
        load_catalog(
            replace(configuration(), inspected_match_ids=(999,)),
            tmp_path / "inspected",
            download=True,
            fetch=fetch_fixture,
        )


def test_coverage_changes_require_a_deliberate_configuration_change(tmp_path: Path) -> None:
    season = replace(configuration().seasons[0], expected_matches=4)
    with pytest.raises(ValueError, match="expected 4 matches, got 3"):
        load_catalog(
            replace(configuration(), seasons=(season,)),
            tmp_path,
            download=True,
            fetch=fetch_fixture,
        )


def test_local_load_never_fetches_without_acquisition(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="run 'regista data catalog'"):
        load_catalog(configuration(), tmp_path, fetch=fetch_fixture)


def test_atomic_write_never_replaces_conflicting_evidence(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    write_once(path, b"original")
    write_once(path, b"original", allow_identical=True)
    with pytest.raises(FileExistsError):
        write_once(path, b"changed", allow_identical=True)
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


def test_corpus_choices_are_valid_and_reject_floating_source_references(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[3] / "catalog/corpus.toml"
    corpus = load_corpus(path)
    assert len(corpus.seasons) == 13
    assert sum(season.expected_matches for season in corpus.seasons) == 1894
    changed = tmp_path / "corpus.toml"
    changed.write_text(path.read_text().replace(corpus.source_commit, "master"))
    with pytest.raises(ValueError, match="exact lowercase"):
        load_corpus(changed)


def test_changed_choices_at_same_commit_have_separate_provenance(tmp_path: Path) -> None:
    original = configuration()
    changed = replace(original, review_seed=43, sha256="c" * 64)
    first = load_catalog(original, tmp_path, download=True, fetch=fetch_fixture)
    second = load_catalog(changed, tmp_path, download=True, fetch=fetch_fixture)
    assert first.matches == second.matches
    assert load_catalog(original, tmp_path).matches == first.matches
    assert load_catalog(changed, tmp_path).matches == second.matches
    receipts = list(tmp_path.rglob("metadata-provenance/*.json"))
    assert len(receipts) == 2
