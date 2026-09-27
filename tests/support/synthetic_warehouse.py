"""A small hand-built StatsBomb-shaped match and a helper that builds a warehouse from it.

Every expected analytical value in the warehouse tests is computed by hand from
the key events below. About a thousand filler "Ball Receipt*" events (no player)
make the match long enough to pass the plausible-event-count check without
touching any tested metric.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time
from pathlib import Path
from types import MappingProxyType

from regista.adapters.statsbomb.normalize import normalize_match
from regista.domain.catalog import MatchIndex
from regista.domain.ids import MatchId, TeamId
from regista.domain.matches import MatchRecord, TeamRecord
from regista.pipeline.ingest import IngestSummary, ingest_matches, match_receipts
from regista.warehouse.builder import IngestRun, WarehouseBuilder

SOURCE_COMMIT = "c" * 40
FILLER_EVENTS = 1000

Record = dict[str, object]
HOME: Record = {"id": 1, "name": "Home"}
AWAY: Record = {"id": 2, "name": "Away"}


def _timestamp(seconds: float) -> str:
    whole = int(seconds)
    milliseconds = round((seconds - whole) * 1000)
    return f"00:{whole // 60:02d}:{whole % 60:02d}.{milliseconds:03d}"


def _player(identifier: int) -> Record:
    return {"id": identifier, "name": f"Player {identifier}"}


@dataclass
class SyntheticMatch:
    """Key events plus filler; ``records()`` assigns provider indexes in time order."""

    match_id: int = 100
    home_score: int = 1
    away_score: int = 1
    data_version: str | None = "1.1.0"
    filler: int = FILLER_EVENTS
    events: list[tuple[int, float, Record]] = field(default_factory=list[tuple[int, float, Record]])
    lineups: list[Record] = field(default_factory=list[Record])
    # Changes finished records after indexes are assigned (for deliberately broken matches).
    mutate: Callable[[list[Record]], None] | None = None

    def add(
        self,
        period: int,
        seconds: float,
        type_name: str,
        team: Record,
        *,
        player: int | None = None,
        location: tuple[float, float] | None = None,
        **details: object,
    ) -> None:
        record: Record = {
            "type": {"id": 0, "name": type_name},
            "team": dict(team),
            "possession": 1,
            "possession_team": dict(HOME),
            "play_pattern": {"id": 1, "name": "Regular Play"},
        }
        if player is not None:
            record["player"] = _player(player)
            record["position"] = {"id": 1, "name": "Center Forward"}
        if location is not None:
            record["location"] = list(location)
        record.update(details)
        self.events.append((period, seconds, record))

    def records(self) -> list[Record]:
        ordered = sorted(self.events, key=lambda item: (item[0], item[1]))
        output: list[Record] = []
        for index, (period, seconds, record) in enumerate(ordered, 1):
            full = copy.deepcopy(record)
            full.update(
                {
                    "id": f"event-{self.match_id}-{index}",
                    "index": index,
                    "period": period,
                    "timestamp": _timestamp(seconds),
                    "minute": int(seconds) // 60 + (45 if period == 2 else 0),
                    "second": int(seconds) % 60,
                }
            )
            output.append(full)
        if self.mutate is not None:
            self.mutate(output)
        return output

    def record(self) -> MatchRecord:
        return MatchRecord(
            provider="statsbomb",
            match_id=MatchId(self.match_id),
            competition_id=2,
            season_id=27,
            competition_name="Synthetic League",
            season_name="2015/2016",
            match_date=date(2015, 8, 8),
            kickoff=time(15, 0),
            home_team=TeamRecord(TeamId(1), "Home"),
            away_team=TeamRecord(TeamId(2), "Away"),
            home_score=self.home_score,
            away_score=self.away_score,
            match_week=1,
            stage="Regular Season",
            stadium="Synthetic Ground",
            data_version=self.data_version,
            xy_fidelity_version="2",
            shot_fidelity_version="2",
            provider_last_updated=None,
            has_three_sixty=False,
            provider_record=MappingProxyType({"match_id": self.match_id}),
        )


def _spell(
    start: str, start_period: int, end: str | None, end_period: int | None, reasons: tuple[str, str]
) -> Record:
    return {
        "position_id": 1,
        "position": "Center Forward",
        "from": start,
        "to": end,
        "from_period": start_period,
        "to_period": end_period,
        "start_reason": reasons[0],
        "end_reason": reasons[1],
    }


def _lineup_player(identifier: int, positions: list[Record]) -> Record:
    return {
        "player_id": identifier,
        "player_name": f"Player {identifier}",
        "player_nickname": None,
        "jersey_number": identifier,
        "cards": [],
        "positions": positions,
    }


def standard_match(match_id: int = 100, filler: int = FILLER_EVENTS) -> SyntheticMatch:
    """The reference match. Score 1-1: a home shot goal and an away own-goal credit."""
    match = SyntheticMatch(match_id=match_id, filler=filler)
    for team, formation in ((HOME, 442), (AWAY, 433)):
        match.add(1, 0.0, "Starting XI", team, tactics={"formation": formation, "lineup": []})
        match.add(1, 0.0, "Half Start", team)
        match.add(2, 0.0, "Half Start", team)
    # Period 1, bin 0.
    match.add(
        1,
        60.0,
        "Pass",
        HOME,
        player=11,
        location=(70.0, 20.0),
        **{"pass": {"end_location": [85.0, 15.0], "recipient": _player(10)}},
    )
    match.add(
        1,
        120.0,
        "Pass",
        HOME,
        player=11,
        location=(85.0, 40.0),
        **{"pass": {"end_location": [110.0, 40.0], "shot_assist": True}},
    )
    match.add(
        1,
        130.0,
        "Shot",
        HOME,
        player=11,
        location=(110.0, 40.0),
        shot={
            "statsbomb_xg": 0.25,
            "end_location": [120.0, 40.0, 1.0],
            "outcome": {"id": 97, "name": "Goal"},
            "type": {"id": 87, "name": "Open Play"},
            "body_part": {"id": 40, "name": "Right Foot"},
        },
    )
    match.add(
        1,
        200.0,
        "Pass",
        AWAY,
        player=20,
        location=(120.0, 0.1),
        **{"pass": {"end_location": [110.0, 40.0], "type": {"id": 61, "name": "Corner"}}},
    )
    for offset in range(match.filler):
        match.add(1, 1000.0 + offset * 1.5, "Ball Receipt*", HOME, location=(60.0, 40.0))
    match.add(1, 2700.0, "Half End", HOME)
    match.add(1, 2700.0, "Half End", AWAY)
    # Period 2.
    match.add(2, 300.0, "Own Goal Against", HOME, player=10, location=(5.0, 40.0))
    match.add(2, 300.0, "Own Goal For", AWAY)
    match.add(
        2,
        600.0,
        "Substitution",
        HOME,
        player=11,
        substitution={"outcome": {"id": 103, "name": "Tactical"}, "replacement": _player(12)},
    )
    match.add(
        2,
        700.0,
        "Carry",
        HOME,
        player=12,
        location=(75.0, 60.0),
        carry={"end_location": [82.0, 62.0]},
    )
    match.add(
        2,
        800.0,
        "Pass",
        HOME,
        player=12,
        location=(70.0, 40.0),
        **{"pass": {"end_location": [90.0, 40.0], "outcome": {"id": 9, "name": "Incomplete"}}},
    )
    match.add(2, 900.0, "Tactical Shift", HOME, tactics={"formation": 4231, "lineup": []})
    match.add(2, 2800.0, "Half End", HOME)
    match.add(2, 2800.0, "Half End", AWAY)
    match.lineups = [
        {
            "team_id": 1,
            "team_name": "Home",
            "lineup": [
                _lineup_player(
                    10, [_spell("00:00", 1, None, None, ("Starting XI", "Final Whistle"))]
                ),
                _lineup_player(
                    11,
                    [
                        _spell(
                            "00:00", 1, "55:00", 2, ("Starting XI", "Substitution - Off (Tactical)")
                        )
                    ],
                ),
                _lineup_player(
                    12,
                    [
                        _spell(
                            "55:00",
                            2,
                            None,
                            None,
                            ("Substitution - On (Tactical)", "Final Whistle"),
                        )
                    ],
                ),
                _lineup_player(13, []),
            ],
        },
        {
            "team_id": 2,
            "team_name": "Away",
            "lineup": [
                _lineup_player(
                    20, [_spell("00:00", 1, None, None, ("Starting XI", "Final Whistle"))]
                )
            ],
        },
    ]
    return match


@dataclass(frozen=True)
class BuiltWarehouse:
    path: Path
    summary: IngestSummary


def build_warehouse(
    directory: Path,
    matches: Sequence[SyntheticMatch],
    *,
    name: str = "warehouse.duckdb",
    corrupt: Callable[[int, str, bytes], bytes] | None = None,
    run_id: str = "synthetic-run",
) -> BuiltWarehouse:
    """Write checksummed raw files and receipts, then run the real pipeline and builder."""
    raw = directory / "raw"
    manifest: dict[str, dict[str, object]] = {}
    for match in matches:
        payloads = {
            "events": json.dumps(match.records()).encode(),
            "lineups": json.dumps(match.lineups).encode(),
        }
        for kind, contents in payloads.items():
            relative = f"statsbomb-open-data/{SOURCE_COMMIT}/data/{kind}/{match.match_id}.json"
            path = raw / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            stored = contents if corrupt is None else corrupt(match.match_id, kind, contents)
            path.write_bytes(stored)
            manifest[relative] = {
                "provider": "statsbomb",
                "dataset": "open-data",
                "source_commit": SOURCE_COMMIT,
                "relative_path": relative,
                "url": f"https://example.invalid/{relative}",
                "kind": kind,
                "provider_match_id": match.match_id,
                "sha256": hashlib.sha256(contents).hexdigest(),
                "bytes": len(contents),
                "retrieved_at": "2026-09-27T00:00:00+00:00",
                "provider_last_updated": None,
                "license_class": "statsbomb-public-data-agreement",
                "split_bucket": "development",
                "split_sha256": "s" * 64,
            }
    records = {MatchId(match.match_id): match.record() for match in matches}
    indexes = [
        MatchIndex(match.match_id, 2, 27, date(2015, 8, 8), time(15, 0), False, ())
        for match in matches
    ]
    builder = WarehouseBuilder(directory / name, run_id)
    summary = ingest_matches(
        indexes, records, match_receipts(manifest, SOURCE_COMMIT), raw, normalize_match, builder
    )
    builder.add_split_assignments(
        [
            {
                "split_version": 1,
                "provider": "statsbomb",
                "competition_id": 2,
                "season_id": 27,
                "match_id": match.match_id,
                "bucket": "development",
                "human_review": False,
            }
            for match in matches
        ]
    )
    builder.add_competition_season(
        {
            "provider": "statsbomb",
            "competition_id": 2,
            "season_id": 27,
            "competition_name": "Synthetic League",
            "season_name": "2015/2016",
            "role": "core_breadth",
            "coverage": "complete_season",
            "expected_matches": len(matches),
            "known_missing_matches": 0,
            "catalog_matches": len(matches),
            "development_matches": len(matches),
            "validation_matches": 0,
            "test_matches": 0,
            "ingested_matches": len(matches),
        }
    )
    moment = datetime(2026, 9, 27, tzinfo=UTC)
    path = builder.build(
        IngestRun(
            ingest_run_id=run_id,
            regista_version="test",
            git_commit="0" * 40,
            git_dirty=False,
            adapter_version="test",
            provider="statsbomb",
            source_commit=SOURCE_COMMIT,
            split_version=1,
            split_sha256="s" * 64,
            selection="synthetic",
            selected_matches=summary.selected,
            normalized_matches=summary.normalized,
            excluded_matches=len(summary.excluded),
            started_at=moment,
            finished_at=datetime.now(UTC),
            status="complete",
        )
    )
    return BuiltWarehouse(path, summary)


def without_player(lineups: list[Record], player_id: int) -> list[Record]:
    output = copy.deepcopy(lineups)
    for team in output:
        players = team["lineup"]
        assert isinstance(players, list)
        team["lineup"] = [player for player in players if player["player_id"] != player_id]  # pyright: ignore[reportUnknownVariableType, reportIndexIssue, reportUnknownMemberType]
    return output


__all__ = [
    "AWAY",
    "HOME",
    "BuiltWarehouse",
    "SyntheticMatch",
    "build_warehouse",
    "replace",
    "standard_match",
    "without_player",
]
