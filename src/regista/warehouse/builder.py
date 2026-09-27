"""Build the DuckDB warehouse from normalized rows, then its quality and analytical layers.

The only package allowed to import ``duckdb``. A build writes into a temporary
file beside the target and replaces the target atomically only after every
step succeeded, so a failed run never leaves a half-built warehouse and never
disturbs a reader holding the previous file open.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from importlib.resources import files
from pathlib import Path
from typing import IO, cast

import duckdb

from regista.domain.lineups import Appearance, PositionSpell
from regista.domain.matches import MatchRecord
from regista.domain.normalized import FIELD_AVAILABILITY, NormalizedMatch, QualityCheck

_STAGED_TABLES = (
    "raw_files",
    "splits",
    "competition_seasons",
    "matches",
    "teams",
    "players",
    "appearances",
    "position_spells",
    "events",
    "passes",
    "carries",
    "shots",
    "substitutions",
    "formation_changes",
    "goals",
    "field_availability",
    "dq_checks",
)
# Load order within each table, so the stored row order never depends on ingestion order.
_ORDER = {
    "raw_files": "relative_path",
    "splits": "match_id",
    "competition_seasons": "competition_id, season_id",
    "matches": "match_id",
    "teams": "team_id, team_name",
    "players": "player_id, player_name",
    "appearances": "match_id, player_id",
    "position_spells": "match_id, player_id, spell_number",
    "events": "match_id, sequence",
    "field_availability": "table_name, column_name",
    "dq_checks": "match_id, check_name",
}
_DISTINCT_TABLES = frozenset({"raw_files", "teams", "players"})


@dataclass(frozen=True)
class IngestRun:
    ingest_run_id: str
    regista_version: str
    git_commit: str
    git_dirty: bool
    adapter_version: str
    provider: str
    source_commit: str
    split_version: int
    split_sha256: str
    selection: str
    selected_matches: int
    normalized_matches: int
    excluded_matches: int
    started_at: datetime
    finished_at: datetime
    status: str


def _sql(name: str) -> str:
    return files("regista.warehouse").joinpath(name).read_text(encoding="utf-8")


def _json_default(value: object) -> object:
    if isinstance(value, date | time):
        return value.isoformat()
    if isinstance(value, Mapping):
        return dict(cast(Mapping[str, object], value))
    raise TypeError(f"cannot stage {type(value).__name__}")


class WarehouseBuilder:
    """Stage validated rows, then build the warehouse in one step with ``build``."""

    def __init__(self, target: Path, ingest_run_id: str) -> None:
        self._target = target
        self._run_id = ingest_run_id
        self._staging = Path(tempfile.mkdtemp(prefix="regista-staging-"))
        self._outputs: dict[str, IO[str]] = {
            table: (self._staging / f"{table}.ndjson").open("w", encoding="utf-8")
            for table in _STAGED_TABLES
        }
        for (table, column), (availability, note) in sorted(FIELD_AVAILABILITY.items()):
            self._write(
                "field_availability",
                {
                    "table_name": table,
                    "column_name": column,
                    "availability": availability,
                    "note": note,
                },
            )

    def _write(self, table: str, row: Mapping[str, object]) -> None:
        self._outputs[table].write(json.dumps(row, default=_json_default) + "\n")

    # WarehouseWriter port -------------------------------------------------------------------

    def add_raw_file(self, receipt: Mapping[str, object]) -> None:
        self._write("raw_files", receipt)

    def add_quality_check(self, check: QualityCheck) -> None:
        self._write(
            "dq_checks",
            {
                "match_id": check.match_id,
                "check_name": check.check,
                "severity": check.severity,
                "passed": check.passed,
                "detail": check.detail,
            },
        )

    def add_match_record(self, match: MatchRecord, checksums: Mapping[str, str]) -> None:
        for team in (match.home_team, match.away_team):
            self._write(
                "teams",
                {"provider": match.provider, "team_id": team.identifier, "team_name": team.name},
            )
        self._write(
            "matches",
            {
                "provider": match.provider,
                "match_id": match.match_id,
                "competition_id": match.competition_id,
                "season_id": match.season_id,
                "match_date": match.match_date,
                "kickoff": match.kickoff,
                "home_team_id": match.home_team.identifier,
                "away_team_id": match.away_team.identifier,
                "home_score": match.home_score,
                "away_score": match.away_score,
                "match_week": match.match_week,
                "stage": match.stage,
                "stadium": match.stadium,
                "data_version": match.data_version,
                "xy_fidelity_version": match.xy_fidelity_version,
                "shot_fidelity_version": match.shot_fidelity_version,
                "provider_last_updated": match.provider_last_updated,
                "has_three_sixty": match.has_three_sixty,
                "events_sha256": checksums.get("events"),
                "lineups_sha256": checksums.get("lineups"),
                "dq_status": None,
                "provider_record": match.provider_record,
            },
        )

    def add_match(self, normalized: NormalizedMatch, checksums: Mapping[str, str]) -> None:
        match = normalized.match
        self.add_match_record(match, checksums)
        for appearance in normalized.appearances:
            self._add_appearance(match.provider, appearance)
        for spell in normalized.position_spells:
            self._add_spell(spell)
        for row in normalized.events:
            event = row.event
            end = event.movement.end if event.movement is not None else None
            self._write(
                "events",
                {
                    "provider": match.provider,
                    "match_id": match.match_id,
                    "event_id": event.identifier,
                    "sequence": event.sequence,
                    "period": event.clock.period,
                    "period_seconds": row.period_seconds,
                    "minute": event.clock.minute,
                    "second": event.clock.second,
                    "team_id": event.team.identifier,
                    "player_id": row.player_id,
                    "position": row.position,
                    "possession": row.possession,
                    "possession_team_id": row.possession_team_id,
                    "event_type": event.action.value,
                    "provider_event_type": row.provider_event_type,
                    "x": None if event.location is None else event.location.x,
                    "y": None if event.location is None else event.location.y,
                    "end_x": None if end is None else end.x,
                    "end_y": None if end is None else end.y,
                    "under_pressure": row.under_pressure,
                    "source": event.source,
                    "provider_record": event.provider_record,
                },
            )
            if event.action.value == "carry":
                self._write("carries", {"match_id": match.match_id, "event_id": event.identifier})
        for item in normalized.passes:
            self._write("passes", {"match_id": match.match_id, **_fields(item)})
        for shot in normalized.shots:
            end = shot.end_location
            self._write(
                "shots",
                {
                    "match_id": match.match_id,
                    "event_id": shot.event_id,
                    "provider_xg": shot.provider_xg,
                    "outcome": shot.outcome,
                    "is_goal": shot.is_goal,
                    "shot_type": shot.shot_type,
                    "body_part": shot.body_part,
                    "key_pass_event_id": shot.key_pass_event_id,
                    "end_x": None if end is None else end.x,
                    "end_y": None if end is None else end.y,
                    "end_z": shot.end_z,
                },
            )
        for table, rows in (
            ("substitutions", normalized.substitutions),
            ("formation_changes", normalized.formation_changes),
            ("goals", normalized.goals),
        ):
            for item in rows:
                self._write(table, {"match_id": match.match_id, **_fields(item)})

    def _add_appearance(self, provider: str, appearance: Appearance) -> None:
        self._write(
            "players",
            {
                "provider": provider,
                "player_id": appearance.player_id,
                "player_name": appearance.player_name,
                "player_nickname": appearance.player_nickname,
            },
        )
        self._write(
            "appearances",
            {
                "match_id": appearance.match_id,
                "team_id": appearance.team_id,
                "player_id": appearance.player_id,
                "jersey_number": appearance.jersey_number,
                "started": appearance.started,
                "provider_record": appearance.provider_record,
            },
        )

    def _add_spell(self, spell: PositionSpell) -> None:
        self._write("position_spells", _fields(spell))

    # Metadata that is not per match ---------------------------------------------------------

    def add_split_assignments(self, rows: Sequence[Mapping[str, object]]) -> None:
        for row in rows:
            self._write("splits", row)

    def add_competition_season(self, row: Mapping[str, object]) -> None:
        self._write("competition_seasons", row)

    # Build ----------------------------------------------------------------------------------

    def build(self, run: IngestRun) -> Path:
        """Load staged rows, run quality checks and analytical builds, and publish atomically."""
        for output in self._outputs.values():
            output.close()
        self._target.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._target.with_name(f".{self._target.name}.building")
        temporary.unlink(missing_ok=True)
        try:
            with duckdb.connect(str(temporary)) as connection:
                connection.execute("SET VARIABLE ingest_run_id = ?", [self._run_id])
                connection.execute(_sql("normalized.sql"))
                for table in _STAGED_TABLES:
                    self._load(connection, table)
                connection.execute(_sql("quality.sql"))
                connection.execute(_sql("analytical.sql"))
                connection.execute(
                    "INSERT INTO normalized.ingest_runs VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        run.ingest_run_id,
                        run.regista_version,
                        run.git_commit,
                        run.git_dirty,
                        run.adapter_version,
                        duckdb.__version__,
                        run.provider,
                        run.source_commit,
                        run.split_version,
                        run.split_sha256,
                        run.selection,
                        run.selected_matches,
                        run.normalized_matches,
                        run.excluded_matches,
                        run.started_at,
                        run.finished_at,
                        run.status,
                    ],
                )
                connection.execute("CHECKPOINT")
            os.replace(temporary, self._target)
        finally:
            temporary.unlink(missing_ok=True)
            shutil.rmtree(self._staging, ignore_errors=True)
        return self._target

    def discard(self) -> None:
        for output in self._outputs.values():
            output.close()
        shutil.rmtree(self._staging, ignore_errors=True)

    def _load(self, connection: duckdb.DuckDBPyConnection, table: str) -> None:
        path = self._staging / f"{table}.ndjson"
        if path.stat().st_size == 0:
            return
        columns = connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'normalized' AND table_name = ? AND column_name <> "
            "'ingest_run_id' ORDER BY ordinal_position",
            [table],
        ).fetchall()
        specification = ", ".join(f"{name}: '{kind}'" for name, kind in columns)
        names = ", ".join(name for name, _ in columns)
        distinct = "DISTINCT " if table in _DISTINCT_TABLES else ""
        order = _ORDER.get(table, "match_id, event_id")
        connection.execute(
            f"INSERT INTO normalized.{table} "
            f"SELECT {distinct}{names}, getvariable('ingest_run_id') "
            f"FROM read_json(?, format = 'newline_delimited', columns = {{{specification}}}) "
            f"ORDER BY {order}",
            [str(path)],
        )


def _fields(item: object) -> dict[str, object]:
    slots: tuple[str, ...] = getattr(type(item), "__slots__", ())
    return {name: getattr(item, name) for name in slots}
