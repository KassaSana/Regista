"""Read corpus choices and publish files without replacing existing evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from regista.domain.catalog import CompetitionSeason, CorpusConfiguration, CorpusRole, Coverage


def object_record(value: object, description: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be an object")
    return cast(dict[str, object], value)


def integer(value: object, description: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{description} must be an integer >= {minimum}")
    return value


def text(value: object, description: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{description} must be a nonempty string")
    return value


def object_list(value: object, description: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{description} must be a list")
    return cast(list[object], value)


def load_corpus(path: Path) -> CorpusConfiguration:
    contents = path.read_bytes()
    record = object_record(tomllib.loads(contents.decode("utf-8")), "corpus")
    provider = text(record.get("provider"), "provider")
    dataset = text(record.get("dataset"), "dataset")
    source_commit = text(record.get("source_commit"), "source_commit")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source_commit must be an exact lowercase 40-character commit")
    seasons: list[CompetitionSeason] = []
    for value in object_list(record.get("competition_seasons"), "competition_seasons"):
        season = object_record(value, "competition-season")
        role = text(season.get("role"), "role")
        coverage = text(season.get("coverage"), "coverage")
        if role not in {"core_breadth", "modern_robustness"}:
            raise ValueError(f"unknown corpus role {role!r}")
        if coverage not in {"complete_season", "single_team", "tournament"}:
            raise ValueError(f"unknown coverage {coverage!r}")
        seasons.append(
            CompetitionSeason(
                competition_id=integer(season.get("competition_id"), "competition_id"),
                season_id=integer(season.get("season_id"), "season_id"),
                role=cast(CorpusRole, role),
                coverage=cast(Coverage, coverage),
                expected_matches=integer(season.get("expected_matches"), "expected_matches"),
                known_missing_matches=integer(
                    season.get("known_missing_matches", 0), "known_missing_matches", minimum=0
                ),
            )
        )
    keys = {(season.competition_id, season.season_id) for season in seasons}
    if not seasons or len(keys) != len(seasons):
        raise ValueError("competition-seasons must be nonempty and unique")
    inspected = tuple(
        integer(value, "inspected match identifier")
        for value in object_list(record.get("inspected_match_ids"), "inspected_match_ids")
    )
    if len(set(inspected)) != len(inspected):
        raise ValueError("inspected match identifiers must be unique")
    return CorpusConfiguration(
        provider,
        dataset,
        source_commit,
        tuple(seasons),
        inspected,
        integer(record.get("review_seed"), "review_seed", minimum=0),
        hashlib.sha256(contents).hexdigest(),
    )


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sync_directory(path: Path) -> None:
    """Persist published directory entries before recording their completion elsewhere."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_once(path: Path, contents: bytes, *, allow_identical: bool = False) -> None:
    """Publish a complete file atomically and refuse to replace an existing version."""
    missing_directories: list[Path] = []
    parent = path.parent
    while not parent.exists():
        missing_directories.append(parent)
        parent = parent.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if not allow_identical or path.read_bytes() != contents:
                raise FileExistsError(f"refusing to replace existing file: {path}") from None
        sync_directory(path.parent)
        for directory in missing_directories:
            sync_directory(directory.parent)
    finally:
        temporary.unlink(missing_ok=True)
