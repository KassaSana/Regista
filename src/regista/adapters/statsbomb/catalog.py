"""Fetch only pinned competition and match indexes; never event or lineup payloads."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, date, datetime, time
from pathlib import Path
from urllib.request import urlopen

from regista.domain.catalog import CorpusConfiguration, IndexCatalog, IndexSource, MatchIndex
from regista.pipeline.catalog import (
    integer,
    json_bytes,
    object_list,
    object_record,
    text,
    write_once,
)

METADATA_FIELDS = ("data_version", "xy_fidelity_version", "shot_fidelity_version")
MAXIMUM_INDEX_BYTES = 20 * 1024 * 1024


def provenance_relative_path(configuration: CorpusConfiguration) -> str:
    """Where the metadata provenance receipt for this corpus lives, relative to ``data/raw``."""
    return (
        f"statsbomb-open-data/{configuration.source_commit}/metadata-provenance/"
        f"{configuration.sha256}.json"
    )


def fetch_index(url: str) -> bytes:
    """Bound both waiting and payload size for the small metadata-only acquisition."""
    with urlopen(url, timeout=30) as response:
        contents = response.read(MAXIMUM_INDEX_BYTES + 1)
    if len(contents) > MAXIMUM_INDEX_BYTES:
        raise ValueError("provider index exceeds the 20 MiB metadata limit")
    return contents


def _records(contents: bytes, description: str) -> list[Mapping[str, object]]:
    return [
        object_record(item, description) for item in object_list(json.loads(contents), description)
    ]


def _parse_match(record: Mapping[str, object], competition_id: int, season_id: int) -> MatchIndex:
    competition = object_record(record.get("competition"), "competition")
    season = object_record(record.get("season"), "season")
    if integer(competition.get("competition_id"), "competition_id") != competition_id:
        raise ValueError("match belongs to a different competition")
    if integer(season.get("season_id"), "season_id") != season_id:
        raise ValueError("match belongs to a different season")
    match_date = date.fromisoformat(text(record.get("match_date"), "match_date"))
    kickoff = time.fromisoformat(text(record.get("kick_off"), "kick_off"))
    if kickoff.tzinfo is not None:
        raise ValueError("match index kickoff must be a local time without a timezone")
    if record.get("match_status") != "available":
        raise ValueError("selected match event data is not available")
    status = record.get("match_status_360")
    if status not in (None, "available", "scheduled", "processing", "unscheduled"):
        raise ValueError(f"unknown 360 availability status: {status!r}")
    metadata = object_record(record.get("metadata", {}), "metadata")
    return MatchIndex(
        match_id=integer(record.get("match_id"), "match_id"),
        competition_id=competition_id,
        season_id=season_id,
        match_date=match_date,
        kickoff=kickoff,
        has_three_sixty=status == "available",
        missing_metadata=tuple(field for field in METADATA_FIELDS if not metadata.get(field)),
        provider_last_updated=(
            text(record["last_updated"], "last_updated") if "last_updated" in record else None
        ),
    )


def load_catalog(
    configuration: CorpusConfiguration,
    raw_directory: Path,
    *,
    download: bool = False,
    fetch: Callable[[str], bytes] = fetch_index,
) -> IndexCatalog:
    """Acquire metadata once, then verify bytes before every parse or split generation."""
    if (configuration.provider, configuration.dataset) != ("statsbomb", "open-data"):
        raise ValueError("this adapter supports only StatsBomb Open Data")
    root = raw_directory / "statsbomb-open-data" / configuration.source_commit
    receipt_path = root / "metadata-provenance" / f"{configuration.sha256}.json"
    paths = ["data/competitions.json"] + [
        f"data/matches/{season.competition_id}/{season.season_id}.json"
        for season in configuration.seasons
    ]
    sources: list[IndexSource] = []
    if receipt_path.exists():
        receipt = object_record(json.loads(receipt_path.read_bytes()), "metadata provenance")
        if any(
            receipt.get(field) != getattr(configuration, field)
            for field in ("provider", "dataset", "source_commit")
        ):
            raise ValueError("metadata provenance source identity does not match the corpus")
        if receipt.get("configuration_sha256") != configuration.sha256:
            raise ValueError("metadata provenance belongs to a different corpus configuration")
        for value in object_list(receipt.get("sources"), "sources"):
            source = object_record(value, "source")
            sources.append(
                IndexSource(
                    text(source.get("relative_path"), "relative_path"),
                    text(source.get("url"), "url"),
                    text(source.get("sha256"), "sha256"),
                    integer(source.get("byte_count"), "byte_count"),
                    text(source.get("retrieved_at"), "retrieved_at"),
                )
            )
        if [source.relative_path for source in sources] != paths:
            raise ValueError("metadata source paths do not match the selected corpus")
    elif download:
        for relative_path in paths:
            url = f"https://raw.githubusercontent.com/hudl/open-data/{configuration.source_commit}/{relative_path}"
            contents = fetch(url)
            _records(contents, relative_path)
            write_once(root / relative_path, contents, allow_identical=True)
            sources.append(
                IndexSource(
                    relative_path,
                    url,
                    hashlib.sha256(contents).hexdigest(),
                    len(contents),
                    datetime.now(UTC).isoformat(),
                )
            )
        write_once(
            receipt_path,
            json_bytes(
                {
                    "configuration_sha256": configuration.sha256,
                    "provider": configuration.provider,
                    "dataset": configuration.dataset,
                    "source_commit": configuration.source_commit,
                    "sources": [asdict(source) for source in sources],
                }
            ),
        )
    else:
        raise ValueError("metadata has not been acquired; run 'regista data catalog' first")

    payloads: dict[str, bytes] = {}
    for source in sources:
        contents = (root / source.relative_path).read_bytes()
        expected_url = f"https://raw.githubusercontent.com/hudl/open-data/{configuration.source_commit}/{source.relative_path}"
        if source.url != expected_url:
            raise ValueError("metadata provenance URL does not match the pinned source")
        if (
            len(contents) != source.byte_count
            or hashlib.sha256(contents).hexdigest() != source.sha256
        ):
            raise ValueError(f"metadata checksum mismatch: {source.relative_path}")
        payloads[source.relative_path] = contents
    competitions = _records(payloads[paths[0]], "competitions")
    available = {
        (
            integer(row.get("competition_id"), "competition_id"),
            integer(row.get("season_id"), "season_id"),
        )
        for row in competitions
    }
    matches: list[MatchIndex] = []
    for season in configuration.seasons:
        if (season.competition_id, season.season_id) not in available:
            raise ValueError("selected competition-season is absent from the provider index")
        relative_path = f"data/matches/{season.competition_id}/{season.season_id}.json"
        rows = _records(payloads[relative_path], relative_path)
        if len(rows) != season.expected_matches:
            raise ValueError(
                f"{relative_path}: expected {season.expected_matches} matches, got {len(rows)}"
            )
        matches.extend(_parse_match(row, season.competition_id, season.season_id) for row in rows)
    if len({match.match_id for match in matches}) != len(matches):
        raise ValueError("match identifiers must be unique across the catalog")
    missing = set(configuration.inspected_match_ids) - {match.match_id for match in matches}
    if missing:
        raise ValueError(f"already-inspected matches missing from the corpus: {sorted(missing)}")
    return IndexCatalog(tuple(matches), tuple(sources))
