"""Translate StatsBomb match-index records into Regista match metadata."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from datetime import date, time
from pathlib import Path
from types import MappingProxyType

from regista.domain.catalog import CorpusConfiguration, IndexCatalog
from regista.domain.ids import MatchId, TeamId
from regista.domain.matches import MatchRecord, TeamRecord
from regista.pipeline.catalog import integer, object_list, object_record, text

PROVIDER = "statsbomb"


def load_match_records(
    configuration: CorpusConfiguration,
    catalog: IndexCatalog,
    raw_directory: Path,
    match_ids: Collection[int],
) -> dict[MatchId, MatchRecord]:
    """Parse the selected matches from index files whose bytes match the verified catalog."""
    root = raw_directory / "statsbomb-open-data" / configuration.source_commit
    wanted = set(match_ids)
    records: dict[MatchId, MatchRecord] = {}
    for source in catalog.sources:
        if not source.relative_path.startswith("data/matches/"):
            continue
        contents = (root / source.relative_path).read_bytes()
        if hashlib.sha256(contents).hexdigest() != source.sha256:
            raise ValueError(f"metadata checksum mismatch: {source.relative_path}")
        for value in object_list(json.loads(contents), source.relative_path):
            record = object_record(value, "match")
            if record.get("match_id") in wanted:
                match = parse_match_record(record)
                records[match.match_id] = match
    missing = wanted - set(records)
    if missing:
        raise ValueError(f"matches absent from the verified indexes: {sorted(missing)}")
    return records


def parse_match_record(record: Mapping[str, object]) -> MatchRecord:
    """Translate one match-index record; provider names stop here."""
    competition = object_record(record.get("competition"), "competition")
    season = object_record(record.get("season"), "season")
    metadata = object_record(record.get("metadata", {}), "metadata")
    stage = record.get("competition_stage")
    stadium = record.get("stadium")
    match_week = record.get("match_week")
    return MatchRecord(
        provider=PROVIDER,
        match_id=MatchId(integer(record.get("match_id"), "match_id")),
        competition_id=integer(competition.get("competition_id"), "competition_id"),
        season_id=integer(season.get("season_id"), "season_id"),
        competition_name=text(competition.get("competition_name"), "competition_name"),
        season_name=text(season.get("season_name"), "season_name"),
        match_date=date.fromisoformat(text(record.get("match_date"), "match_date")),
        kickoff=time.fromisoformat(text(record.get("kick_off"), "kick_off")),
        home_team=_team(record.get("home_team"), "home"),
        away_team=_team(record.get("away_team"), "away"),
        home_score=integer(record.get("home_score"), "home_score", minimum=0),
        away_score=integer(record.get("away_score"), "away_score", minimum=0),
        match_week=None if match_week is None else integer(match_week, "match_week"),
        stage=None if stage is None else text(object_record(stage, "stage").get("name"), "stage"),
        stadium=(
            None
            if stadium is None
            else text(object_record(stadium, "stadium").get("name"), "stadium")
        ),
        data_version=_optional_text(metadata.get("data_version")),
        xy_fidelity_version=_optional_text(metadata.get("xy_fidelity_version")),
        shot_fidelity_version=_optional_text(metadata.get("shot_fidelity_version")),
        provider_last_updated=_optional_text(record.get("last_updated")),
        has_three_sixty=record.get("match_status_360") == "available",
        provider_record=MappingProxyType(dict(record)),
    )


def _team(value: object, side: str) -> TeamRecord:
    team = object_record(value, f"{side}_team")
    return TeamRecord(
        identifier=TeamId(integer(team.get(f"{side}_team_id"), f"{side}_team_id")),
        name=text(team.get(f"{side}_team_name"), f"{side}_team_name"),
    )


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
