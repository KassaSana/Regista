"""Rebuild frozen assignments from local, checksum-verified indexes only (no event reads)."""

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pytest

from regista.adapters.statsbomb.catalog import load_catalog
from regista.pipeline.catalog import load_corpus
from regista.pipeline.splits import assign_splits

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.contract
def test_version_one_rebuilds_from_verified_metadata_with_whole_dates_and_review_guards() -> None:
    configuration = load_corpus(ROOT / "catalog/corpus.toml")
    assert set(configuration.inspected_match_ids) == {3773497, 265958, 3869420, 3869321}
    receipt = (
        ROOT
        / "data/raw/statsbomb-open-data"
        / configuration.source_commit
        / "metadata-provenance"
        / f"{configuration.sha256}.json"
    )
    if not receipt.exists():
        pytest.skip("pinned metadata has not been acquired locally")
    catalog = load_catalog(configuration, ROOT / "data/raw")
    assignments = assign_splits(configuration, catalog)
    document = json.loads((ROOT / "splits/v1.json").read_bytes())
    assert document["configuration_sha256"] == configuration.sha256
    assert document["assignments"] == [asdict(row) for row in assignments]
    assert len(catalog.matches) == 1894
    assert Counter(row.bucket for row in assignments) == {
        "development": 1340,
        "validation": 279,
        "test": 275,
    }
    by_identifier = {row.match_id: row for row in assignments}
    buckets_by_date: dict[tuple[int, int, date], set[str]] = defaultdict(set)
    for match in catalog.matches:
        buckets_by_date[(*match.season_key, match.match_date)].add(
            by_identifier[match.match_id].bucket
        )
    assert all(len(buckets) == 1 for buckets in buckets_by_date.values())
    for identifier in configuration.inspected_match_ids:
        assert by_identifier[identifier].bucket == "development"
    review = [row for row in assignments if row.human_review]
    assert len(review) == 24
    assert all(row.bucket == "validation" for row in review)
    assert Counter(row.competition_id for row in review) == {2: 6, 7: 6, 11: 6, 12: 6}
    assert sum(bool(match.missing_metadata) for match in catalog.matches) == 2
