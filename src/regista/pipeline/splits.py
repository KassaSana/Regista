"""Freeze deterministic date-grouped splits without reading event content."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from regista.domain.catalog import CorpusConfiguration, IndexCatalog, MatchIndex
from regista.pipeline.catalog import json_bytes, write_once

SplitBucket = Literal["development", "validation", "test"]
DevelopmentException = Literal["already_inspected", "same_date_as_inspected"]
SPLIT_RULE = "chronological-whole-dates-70-15-15-v1"
REVIEW_RULE = "lowest-sha256-seed-provider-competition-season-match-v1"


@dataclass(frozen=True)
class SplitAssignment:
    match_id: int
    competition_id: int
    season_id: int
    bucket: SplitBucket
    development_exception: DevelopmentException | None = None
    human_review: bool = False


def _chronological_buckets(matches: list[MatchIndex]) -> dict[int, SplitBucket]:
    groups: dict[date, list[MatchIndex]] = defaultdict(list)
    for match in sorted(matches, key=lambda row: (row.match_date, row.kickoff, row.match_id)):
        groups[match.match_date].append(match)
    dates = sorted(groups)
    if len(dates) < 3:
        raise ValueError("each competition-season needs at least three distinct dates")
    cumulative: list[int] = []
    total = 0
    for match_date in dates:
        total += len(groups[match_date])
        cumulative.append(total)
    # Integer arithmetic: target cumulative fractions are exactly 70/100 and 85/100.
    first, second = min(
        (
            (first, second)
            for first in range(len(dates) - 2)
            for second in range(first + 1, len(dates) - 1)
        ),
        key=lambda pair: (
            abs(100 * cumulative[pair[0]] - 70 * total)
            + abs(100 * cumulative[pair[1]] - 85 * total),
            pair[0],
            pair[1],
        ),
    )
    buckets: dict[int, SplitBucket] = {}
    for index, match_date in enumerate(dates):
        bucket: SplitBucket = (
            "development" if index <= first else "validation" if index <= second else "test"
        )
        buckets.update((match.match_id, bucket) for match in groups[match_date])
    return buckets


def assign_splits(
    configuration: CorpusConfiguration, catalog: IndexCatalog
) -> tuple[SplitAssignment, ...]:
    seasons: dict[tuple[int, int], list[MatchIndex]] = defaultdict(list)
    identifiers: set[int] = set()
    for match in catalog.matches:
        if match.match_id in identifiers:
            raise ValueError("duplicate match identifier in split input")
        identifiers.add(match.match_id)
        seasons[match.season_key].append(match)
    expected = {(season.competition_id, season.season_id) for season in configuration.seasons}
    if set(seasons) != expected:
        raise ValueError("split input competition-seasons differ from corpus choices")
    inspected = set(configuration.inspected_match_ids)
    if not inspected <= identifiers:
        raise ValueError("already-inspected matches missing from split input")
    assignments: list[SplitAssignment] = []
    for season in configuration.seasons:
        matches = seasons[(season.competition_id, season.season_id)]
        if len(matches) != season.expected_matches:
            raise ValueError("split input counts differ from corpus choices")
        buckets = _chronological_buckets(matches)
        forced_dates = {match.match_date for match in matches if match.match_id in inspected}
        exceptions: dict[int, DevelopmentException] = {}
        for match in matches:
            if match.match_date in forced_dates:
                if match.match_id in inspected:
                    exceptions[match.match_id] = "already_inspected"
                elif buckets[match.match_id] != "development":
                    exceptions[match.match_id] = "same_date_as_inspected"
                buckets[match.match_id] = "development"
        if set(buckets.values()) != {"development", "validation", "test"}:
            raise ValueError("development exceptions emptied a held-out split")
        review: set[int] = set()
        if season.role == "core_breadth":
            validation = [match for match in matches if buckets[match.match_id] == "validation"]
            if len(validation) < 6:
                raise ValueError("each core competition-season needs six validation review matches")
            ranked = sorted(
                validation,
                key=lambda match: (
                    hashlib.sha256(
                        f"{configuration.review_seed}:{configuration.provider}:"
                        f"{match.competition_id}:{match.season_id}:{match.match_id}".encode()
                    ).digest(),
                    match.match_id,
                ),
            )
            review = {match.match_id for match in ranked[:6]}
        assignments.extend(
            SplitAssignment(
                match.match_id,
                match.competition_id,
                match.season_id,
                buckets[match.match_id],
                exceptions.get(match.match_id),
                match.match_id in review,
            )
            for match in matches
        )
    return tuple(
        sorted(assignments, key=lambda row: (row.competition_id, row.season_id, row.match_id))
    )


def freeze_splits(
    configuration: CorpusConfiguration,
    catalog: IndexCatalog,
    directory: Path,
    *,
    version: int,
    reason: str,
) -> tuple[Path, tuple[SplitAssignment, ...]]:
    if version < 1 or not reason.strip():
        raise ValueError("split version must be positive and a nonempty reason is required")
    target = directory / f"v{version}.json"
    if target.exists():
        raise FileExistsError(f"split version already exists and cannot be edited: {target}")
    previous_hash: str | None = None
    if version > 1:
        previous = directory / f"v{version - 1}.json"
        if not previous.is_file():
            raise ValueError("the immediately preceding split version must exist")
        previous_hash = hashlib.sha256(previous.read_bytes()).hexdigest()
    elif directory.exists() and any(directory.glob("v*.json")):
        raise ValueError("cannot create version one alongside existing split versions")
    assignments = assign_splits(configuration, catalog)
    document = {
        "schema_version": 1,
        "version": version,
        "generated_at": datetime.now(UTC).isoformat(),
        "reason": reason.strip(),
        "provider": configuration.provider,
        "dataset": configuration.dataset,
        "source_commit": configuration.source_commit,
        "configuration_sha256": configuration.sha256,
        "previous_version_sha256": previous_hash,
        "rule": SPLIT_RULE,
        "boundary_objective": (
            "minimum summed absolute error from cumulative 70% and 85%; earlier ties"
        ),
        "development_exception_rule": "promote the whole season-date group of inspected matches",
        "review_rule": REVIEW_RULE,
        "review_seed": configuration.review_seed,
        "review_matches_per_core_season": 6,
        "index_sources": [
            {
                "relative_path": source.relative_path,
                "sha256": source.sha256,
                "byte_count": source.byte_count,
            }
            for source in catalog.sources
        ],
        "assignments": [asdict(assignment) for assignment in assignments],
    }
    write_once(target, json_bytes(document))
    return target, assignments
