"""Frozen partitions protect whole dates, inspected exceptions, and held-out review data."""

import json
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, time, timedelta
from pathlib import Path

import pytest

from regista.domain.catalog import CompetitionSeason, CorpusConfiguration, IndexCatalog, MatchIndex
from regista.pipeline.splits import assign_splits, freeze_splits


def synthetic_catalog() -> tuple[CorpusConfiguration, IndexCatalog]:
    configuration = CorpusConfiguration(
        "synthetic",
        "fixture",
        "a" * 40,
        (CompetitionSeason(1, 1, "core_breadth", "complete_season", 60),),
        (),
        20260927,
        "b" * 64,
    )
    # Two kickoffs per date; the 85% target falls inside a date and must not split it.
    matches = tuple(
        MatchIndex(
            index + 1,
            1,
            1,
            date(2020, 1, 1) + timedelta(days=index // 2),
            time(12 + index % 2),
            False,
            (),
        )
        for index in range(60)
    )
    return configuration, IndexCatalog(matches, ())


def test_chronological_boundaries_keep_dates_whole_and_review_in_validation() -> None:
    configuration, catalog = synthetic_catalog()
    assignments = assign_splits(configuration, catalog)
    assert Counter(row.bucket for row in assignments) == {
        "development": 42,
        "validation": 8,
        "test": 10,
    }
    dates: dict[date, set[str]] = defaultdict(set)
    by_identifier = {row.match_id: row for row in assignments}
    for match in catalog.matches:
        dates[match.match_date].add(by_identifier[match.match_id].bucket)
    assert all(len(buckets) == 1 for buckets in dates.values())
    review = [row for row in assignments if row.human_review]
    assert len(review) == 6
    assert all(row.bucket == "validation" for row in review)
    assert (
        assign_splits(configuration, replace(catalog, matches=tuple(reversed(catalog.matches))))
        == assignments
    )


def test_inspected_match_promotes_its_whole_date_without_using_it_for_review() -> None:
    configuration, catalog = synthetic_catalog()
    configuration = replace(configuration, inspected_match_ids=(59,))
    assignments = {row.match_id: row for row in assign_splits(configuration, catalog)}
    assert assignments[59].bucket == assignments[60].bucket == "development"
    assert assignments[59].development_exception == "already_inspected"
    assert assignments[60].development_exception == "same_date_as_inspected"
    assert not assignments[59].human_review and not assignments[60].human_review
    assert assignments[58].bucket == "test"


def test_freeze_is_exclusive_and_contains_no_provider_payload_or_match_dates(
    tmp_path: Path,
) -> None:
    configuration, catalog = synthetic_catalog()
    path, _ = freeze_splits(configuration, catalog, tmp_path, version=1, reason="Initial fixture")
    original = path.read_bytes()
    document = json.loads(original)
    assert document["version"] == 1
    assert len(document["assignments"]) == 60
    assert set(document["assignments"][0]) == {
        "match_id",
        "competition_id",
        "season_id",
        "bucket",
        "development_exception",
        "human_review",
    }
    with pytest.raises(FileExistsError, match="cannot be edited"):
        freeze_splits(configuration, catalog, tmp_path, version=1, reason="Accidental rerun")
    assert path.read_bytes() == original
    next_path, _ = freeze_splits(configuration, catalog, tmp_path, version=2, reason="New fixture")
    assert next_path.name == "v2.json"
    assert json.loads(next_path.read_bytes())["previous_version_sha256"]


def test_split_version_requires_a_reason_and_predecessor(tmp_path: Path) -> None:
    configuration, catalog = synthetic_catalog()
    with pytest.raises(ValueError, match="reason"):
        freeze_splits(configuration, catalog, tmp_path, version=1, reason=" ")
    with pytest.raises(ValueError, match="preceding"):
        freeze_splits(configuration, catalog, tmp_path, version=2, reason="Skipped predecessor")
    assert not list(tmp_path.iterdir())


def test_rejects_missing_inspected_match_and_duplicate_input() -> None:
    configuration, catalog = synthetic_catalog()
    with pytest.raises(ValueError, match="already-inspected"):
        assign_splits(replace(configuration, inspected_match_ids=(999,)), catalog)
    with pytest.raises(ValueError, match="duplicate"):
        assign_splits(
            configuration, replace(catalog, matches=catalog.matches + catalog.matches[:1])
        )


def test_refuses_too_few_dates_and_empty_held_out_buckets() -> None:
    configuration, catalog = synthetic_catalog()
    same_day = tuple(replace(match, match_date=date(2020, 1, 1)) for match in catalog.matches)
    with pytest.raises(ValueError, match="three distinct dates"):
        assign_splits(configuration, replace(catalog, matches=same_day))
    inspected = tuple(match.match_id for match in catalog.matches)
    with pytest.raises(ValueError, match="emptied"):
        assign_splits(replace(configuration, inspected_match_ids=inspected), catalog)


def test_refuses_core_review_set_with_insufficient_validation_matches() -> None:
    configuration, catalog = synthetic_catalog()
    configuration = replace(
        configuration,
        inspected_match_ids=tuple(range(43, 49)),
    )
    with pytest.raises(ValueError, match="six validation"):
        assign_splits(configuration, catalog)
