"""Command-line composition root for Regista."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from regista import __version__
from regista.adapters.statsbomb.catalog import load_catalog, provenance_relative_path
from regista.adapters.statsbomb.download import fetch_payload, plan_files
from regista.adapters.statsbomb.events import load_events
from regista.adapters.statsbomb.matches import load_match_records
from regista.adapters.statsbomb.normalize import ADAPTER_VERSION, normalize_match
from regista.detectors.recorded_match_facts import RecordedMatchFactsDetector
from regista.domain.catalog import CorpusConfiguration, IndexCatalog
from regista.domain.ids import MatchId
from regista.domain.insights import AttackingBurst
from regista.domain.replay import replay
from regista.pipeline.catalog import load_corpus
from regista.pipeline.download import acquire_files, read_manifest, select_development_matches
from regista.pipeline.ingest import ingest_matches, ingest_run_identifier, match_receipts
from regista.pipeline.remote import (
    SnapshotFacts,
    pull_manifest,
    pull_match_files,
    pull_metadata,
    pull_warehouse,
    push_raw,
    push_warehouse,
    require_development,
    split_buckets,
    verify_remote,
)
from regista.pipeline.splits import assign_splits, freeze_splits
from regista.product import ATTRIBUTION, build_card_stream, build_match_export
from regista.storage.r2 import R2Store
from regista.templates import (
    render_attacking_burst,
    render_attacking_burst_evidence,
    render_attacking_side_shift,
    render_clock,
    render_evidence,
    render_match_fact,
    render_match_fact_evidence,
)
from regista.warehouse.builder import IngestRun, WarehouseBuilder
from regista.warehouse.research import fingerprint, quality_report, snapshot_facts

DEFAULT_WAREHOUSE = Path("data/warehouse/regista.duckdb")
DEFAULT_QUALITY_DIRECTORY = Path("out/dq")
DEFAULT_DOWNLOAD_REPORTS = Path("out/downloads")
DEFAULT_EXPORTS = Path("out/exports")


def _season_key(value: str) -> tuple[int, int]:
    """Parse ``COMPETITION:SEASON`` (for example ``2:27``)."""
    competition, separator, season = value.partition(":")
    if not separator or not competition.isdigit() or not season.isdigit():
        raise argparse.ArgumentTypeError("expected COMPETITION:SEASON, for example 2:27")
    return int(competition), int(season)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface without performing any I/O."""
    parser = argparse.ArgumentParser(
        prog="regista",
        description="Evidence-backed soccer match insights from event data.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    commands = parser.add_subparsers(dest="command")
    replay_command = commands.add_parser(
        "replay",
        help="replay a match in order and print the cards it produces",
    )
    replay_command.add_argument(
        "--match", type=int, required=True, help="StatsBomb match identifier"
    )
    replay_command.add_argument(
        "--events-dir",
        type=Path,
        help="directory of event files (default: the pinned corpus raw directory)",
    )
    replay_command.add_argument(
        "--evidence",
        action="store_true",
        help="print each card's channel table and supporting entries instead of identifiers",
    )
    replay_command.add_argument(
        "--facts",
        action="store_true",
        help="show provisional starting-lineup, substitution, and formation facts",
    )
    export_command = commands.add_parser(
        "export",
        help="write the viewer's replay export for one development match",
    )
    export_command.add_argument(
        "--match",
        type=int,
        action="append",
        required=True,
        help="StatsBomb match identifier (repeat to export several)",
    )
    export_command.add_argument("--corpus", type=Path, default=Path("catalog/corpus.toml"))
    export_command.add_argument("--raw-directory", type=Path, default=Path("data/raw"))
    export_command.add_argument("--split-file", type=Path, default=Path("splits/v1.json"))
    export_command.add_argument("--output-directory", type=Path, default=DEFAULT_EXPORTS)
    data_command = commands.add_parser("data", help="catalog metadata and freeze research splits")
    data_commands = data_command.add_subparsers(dest="data_command", required=True)
    for name, help_text in (
        ("catalog", "acquire and validate pinned competition and match indexes only"),
        ("split", "freeze splits from verified local indexes without downloading events"),
        ("download", "download and verify selected development events and lineups"),
        ("ingest", "validate development matches and rebuild the development warehouse"),
    ):
        command = data_commands.add_parser(name, help=help_text)
        command.add_argument("--corpus", type=Path, default=Path("catalog/corpus.toml"))
        command.add_argument("--raw-directory", type=Path, default=Path("data/raw"))
        if name == "split":
            command.add_argument("--output-directory", type=Path, default=Path("splits"))
            command.add_argument("--split-version", type=int, default=1)
            command.add_argument("--reason", required=True, help="reason for creating this version")
        elif name == "download":
            command.add_argument("--split-file", type=Path, default=Path("splits/v1.json"))
            command.add_argument("--competition", type=int)
            command.add_argument("--season", type=int)
            command.add_argument(
                "--competition-season",
                type=_season_key,
                action="append",
                default=[],
                metavar="C:S",
                help="select a development competition-season; repeatable",
            )
            command.add_argument("--match", type=int, action="append", default=[])
            command.add_argument("--include-inspected", action="store_true")
            command.add_argument("--workers", type=int, default=4)
            command.add_argument("--verify-only", action="store_true")
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--report", type=Path, default=Path("out/downloads/latest.json"))
        elif name == "ingest":
            command.add_argument("--split-file", type=Path, default=Path("splits/v1.json"))
            command.add_argument("--competition", type=int)
            command.add_argument("--season", type=int)
            command.add_argument(
                "--competition-season",
                type=_season_key,
                action="append",
                default=[],
                metavar="C:S",
                help="select a development competition-season; repeatable",
            )
            command.add_argument("--match", type=int, action="append", default=[])
            command.add_argument("--include-inspected", action="store_true")
            command.add_argument("--output", type=Path, default=DEFAULT_WAREHOUSE)
            command.add_argument("--report-directory", type=Path, default=DEFAULT_QUALITY_DIRECTORY)
    remote_command = data_commands.add_parser(
        "remote", help="back up and restore development data in private R2 storage"
    )
    remote_commands = remote_command.add_subparsers(dest="remote_command", required=True)
    for name, help_text in (
        ("push", "upload development raw files, the manifest, and optionally a warehouse"),
        ("verify", "compare remote storage with the local manifest"),
        ("pull", "restore the manifest, indexes, selected matches, or a warehouse snapshot"),
    ):
        command = remote_commands.add_parser(name, help=help_text)
        command.add_argument("--corpus", type=Path, default=Path("catalog/corpus.toml"))
        command.add_argument("--raw-directory", type=Path, default=Path("data/raw"))
        command.add_argument("--split-file", type=Path, default=Path("splits/v1.json"))
        command.add_argument("--workers", type=int, default=4)
        if name == "push":
            command.add_argument(
                "--warehouse", action="store_true", help="store a warehouse snapshot instead"
            )
            command.add_argument("--warehouse-path", type=Path, default=DEFAULT_WAREHOUSE)
            command.add_argument(
                "--quality-directory", type=Path, default=DEFAULT_QUALITY_DIRECTORY
            )
            command.add_argument("--reports-directory", type=Path, default=DEFAULT_DOWNLOAD_REPORTS)
            command.add_argument(
                "--allow-dirty",
                action="store_true",
                help="store a warehouse built from uncommitted code (not reproducible from git)",
            )
        elif name == "verify":
            command.add_argument(
                "--deep", action="store_true", help="download and re-hash every object"
            )
            command.add_argument(
                "--scratch-directory",
                type=Path,
                default=Path("data/tmp"),
                help="where deep verification temporarily downloads warehouse snapshots",
            )
        else:
            command.add_argument("--competition", type=int)
            command.add_argument("--season", type=int)
            command.add_argument(
                "--competition-season", type=_season_key, action="append", default=[], metavar="C:S"
            )
            command.add_argument("--match", type=int, action="append", default=[])
            command.add_argument("--include-inspected", action="store_true")
            command.add_argument("--manifest", help="restore this manifest snapshot SHA-256")
            command.add_argument(
                "--warehouse", metavar="RUN_ID", help="restore a warehouse snapshot or 'latest'"
            )
            command.add_argument("--output", type=Path, default=DEFAULT_WAREHOUSE)
            command.add_argument("--replace", action="store_true")
    quality_command = data_commands.add_parser(
        "quality", help="write the data-quality report of a built warehouse"
    )
    quality_command.add_argument("--warehouse", type=Path, default=DEFAULT_WAREHOUSE)
    quality_command.add_argument("--report-directory", type=Path, default=DEFAULT_QUALITY_DIRECTORY)
    fingerprint_command = data_commands.add_parser(
        "fingerprint", help="print per-table content hashes; compare two builds for determinism"
    )
    fingerprint_command.add_argument("--warehouse", type=Path, default=DEFAULT_WAREHOUSE)
    fingerprint_command.add_argument("--compare", type=Path, help="a second warehouse to compare")
    return parser


def _source_digest() -> str:
    """Hash the package's own source, so uncommitted code changes give a new run identifier."""
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted([*package.rglob("*.py"), *package.rglob("*.sql")]):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_state() -> tuple[str, bool]:
    """Return the current commit and whether the working tree has uncommitted changes."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True
    return commit, bool(status.strip())


def _write_quality_report(warehouse: Path, directory: Path) -> Path:
    markdown, summary = quality_report(warehouse)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "latest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    path = directory / "latest.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def _run_ingest(
    arguments: argparse.Namespace, configuration: CorpusConfiguration, catalog: IndexCatalog
) -> int:
    started_at = datetime.now(UTC)
    matches, split_checksum = select_development_matches(
        configuration,
        catalog,
        arguments.split_file,
        competition_id=arguments.competition,
        season_id=arguments.season,
        match_ids=arguments.match,
        include_inspected=arguments.include_inspected,
        season_keys=arguments.competition_season,
    )
    raw_directory: Path = arguments.raw_directory
    manifest = read_manifest(raw_directory / "manifest.jsonl")
    receipts = match_receipts(manifest, configuration.source_commit)
    records = load_match_records(
        configuration, catalog, raw_directory, [match.match_id for match in matches]
    )
    split_version = int(arguments.split_file.stem.removeprefix("v"))
    git_commit, git_dirty = _git_state()
    selection = (
        f"competition={arguments.competition} season={arguments.season} "
        f"competition_seasons={sorted(arguments.competition_season)} "
        f"matches={sorted(arguments.match)} include_inspected={arguments.include_inspected}"
    )
    run_id = ingest_run_identifier(
        {
            "regista_version": __version__,
            "git_commit": git_commit,
            "git_dirty": git_dirty,
            "source_digest": _source_digest(),
            "adapter_version": ADAPTER_VERSION,
            "source_commit": configuration.source_commit,
            "split_sha256": split_checksum,
            "files": sorted(
                (kind, match.match_id, str(receipt.get("sha256")))
                for match in matches
                for kind in ("events", "lineups")
                if (receipt := receipts.get((kind, match.match_id))) is not None
            ),
        }
    )
    builder = WarehouseBuilder(arguments.output, run_id)
    try:
        for receipt in manifest.values():
            if receipt.get("source_commit") == configuration.source_commit and receipt.get(
                "kind"
            ) in ("competitions", "matches"):
                builder.add_raw_file(receipt)
        assignments = assign_splits(configuration, catalog)
        builder.add_split_assignments(
            [
                {
                    "split_version": split_version,
                    "provider": configuration.provider,
                    "competition_id": row.competition_id,
                    "season_id": row.season_id,
                    "match_id": row.match_id,
                    "bucket": row.bucket,
                    "human_review": row.human_review,
                }
                for row in assignments
            ]
        )

        def progress(completed: int, total: int) -> None:
            if completed % 50 == 0 or completed == total:
                print(f"Validated {completed}/{total} matches.", flush=True)

        summary = ingest_matches(
            matches, records, receipts, raw_directory, normalize_match, builder, progress=progress
        )
        for season in configuration.seasons:
            ingested = [
                record
                for record in records.values()
                if (record.competition_id, record.season_id)
                == (season.competition_id, season.season_id)
            ]
            if not ingested:
                continue
            season_rows = [
                row
                for row in assignments
                if (row.competition_id, row.season_id) == (season.competition_id, season.season_id)
            ]
            builder.add_competition_season(
                {
                    "provider": configuration.provider,
                    "competition_id": season.competition_id,
                    "season_id": season.season_id,
                    "competition_name": ingested[0].competition_name,
                    "season_name": ingested[0].season_name,
                    "role": season.role,
                    "coverage": season.coverage,
                    "expected_matches": season.expected_matches,
                    "known_missing_matches": season.known_missing_matches,
                    "catalog_matches": len(season_rows),
                    **{
                        f"{bucket}_matches": sum(row.bucket == bucket for row in season_rows)
                        for bucket in ("development", "validation", "test")
                    },
                    "ingested_matches": len(ingested),
                }
            )
        builder.build(
            IngestRun(
                ingest_run_id=run_id,
                regista_version=__version__,
                git_commit=git_commit,
                git_dirty=git_dirty,
                adapter_version=ADAPTER_VERSION,
                provider=configuration.provider,
                source_commit=configuration.source_commit,
                split_version=split_version,
                split_sha256=split_checksum,
                selection=selection,
                selected_matches=summary.selected,
                normalized_matches=summary.normalized,
                excluded_matches=len(summary.excluded),
                started_at=started_at,
                finished_at=datetime.now(UTC),
                status="complete",
            )
        )
    except BaseException:
        builder.discard()
        raise
    report = _write_quality_report(arguments.output, arguments.report_directory)
    print(
        f"Built {arguments.output}: {summary.normalized} of {summary.selected} matches normalized; "
        f"{len(summary.excluded)} failed adapter or checksum validation. Run {run_id}."
    )
    print(f"Data-quality report: {report}")
    return 0


def _progress(label: str) -> Callable[[int, int], None]:
    def report(completed: int, total: int) -> None:
        if completed % 100 == 0 or completed == total:
            print(f"{label} {completed}/{total}", flush=True)

    return report


def _development_ids(
    configuration: CorpusConfiguration, raw_directory: Path, split_file: Path
) -> set[int]:
    """Every development match under the frozen split, validated against the local catalog."""
    catalog = load_catalog(configuration, raw_directory)
    matches, _ = select_development_matches(
        configuration,
        catalog,
        split_file,
        season_keys=[(season.competition_id, season.season_id) for season in configuration.seasons],
        include_inspected=True,
    )
    return {match.match_id for match in matches}


def _run_remote(arguments: argparse.Namespace) -> int:
    configuration = load_corpus(arguments.corpus)
    raw_directory: Path = arguments.raw_directory
    split_file: Path = arguments.split_file
    buckets = split_buckets(split_file)
    command: str = arguments.remote_command
    if command == "pull" and arguments.warehouse is None:
        # Named matches are checked against the frozen split before any network request.
        require_development(arguments.match, buckets)
    provenance = provenance_relative_path(configuration)
    store = R2Store.from_environment()

    if command == "push" and arguments.warehouse:
        warehouse: Path = arguments.warehouse_path
        _write_quality_report(warehouse, arguments.quality_directory)
        run, outside, table_fingerprint = snapshot_facts(warehouse)
        manifest_bytes = (raw_directory / "manifest.jsonl").read_bytes()
        git_commit, git_dirty = _git_state()
        result = push_warehouse(
            store,
            warehouse,
            SnapshotFacts(run, outside, table_fingerprint),
            {
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "corpus_configuration_sha256": configuration.sha256,
                "split_file": split_file.as_posix(),
                "split_file_sha256": hashlib.sha256(split_file.read_bytes()).hexdigest(),
                "pushed_from_git_commit": git_commit,
                "pushed_from_dirty_tree": git_dirty,
            },
            [
                arguments.quality_directory / "latest.md",
                arguments.quality_directory / "latest.json",
            ],
            allow_dirty=arguments.allow_dirty,
        )
        print("; ".join(result.notes) or "Nothing to store.")
        print(f"Uploaded {result.uploaded} objects, {result.byte_count:,} bytes.")
        return 0
    if command == "push":
        development = _development_ids(configuration, raw_directory, split_file)
        manifest = read_manifest(raw_directory / "manifest.jsonl")
        reports_directory: Path = arguments.reports_directory
        reports = sorted(reports_directory.glob("*.json")) if reports_directory.exists() else []
        result = push_raw(
            store,
            raw_directory,
            manifest,
            development,
            [provenance],
            reports=reports,
            workers=arguments.workers,
            progress=_progress("Checked or uploaded"),
        )
        print(
            f"Uploaded {result.uploaded} objects ({result.byte_count:,} bytes); "
            f"{result.unchanged} already stored. {'; '.join(result.notes)}"
        )
        return 0
    if command == "verify":
        development = _development_ids(configuration, raw_directory, split_file)
        manifest = read_manifest(raw_directory / "manifest.jsonl")
        verification = verify_remote(
            store,
            manifest,
            development,
            [provenance],
            deep=arguments.deep,
            scratch_directory=arguments.scratch_directory,
            progress=_progress("Verified"),
        )
        for problem in verification.problems:
            print(f"PROBLEM: {problem}")
        print(
            f"Checked {verification.checked} raw objects and {verification.snapshots} warehouse "
            f"snapshots ({'deep' if arguments.deep else 'metadata'}): "
            + ("all verified." if verification.ok else f"{len(verification.problems)} problems.")
        )
        return 0 if verification.ok else 1
    if arguments.warehouse is not None:
        run_id, result = pull_warehouse(
            store, arguments.warehouse, arguments.output, fingerprint, replace=arguments.replace
        )
        print(
            f"Restored warehouse snapshot {run_id} to {arguments.output} "
            f"({result.byte_count:,} bytes); checksum and fingerprint verified."
        )
        return 0
    digest = pull_manifest(store, raw_directory, arguments.manifest)
    metadata = pull_metadata(store, raw_directory, [provenance])
    print(
        f"Manifest {digest[:12]} in place; metadata files: {metadata.downloaded} restored, "
        f"{metadata.unchanged} already present."
    )
    selected = (
        arguments.competition is not None
        or arguments.competition_season
        or arguments.match
        or arguments.include_inspected
    )
    if not selected:
        print("No matches selected; pass a selection to restore match files.")
        return 0
    catalog = load_catalog(configuration, raw_directory)
    matches, _ = select_development_matches(
        configuration,
        catalog,
        split_file,
        competition_id=arguments.competition,
        season_id=arguments.season,
        match_ids=arguments.match,
        include_inspected=arguments.include_inspected,
        season_keys=arguments.competition_season,
    )
    result = pull_match_files(
        store,
        raw_directory,
        read_manifest(raw_directory / "manifest.jsonl"),
        [match.match_id for match in matches],
        buckets,
        workers=arguments.workers,
        progress=_progress("Verified or restored"),
    )
    print(
        f"{len(matches)} development matches: {result.downloaded} files restored "
        f"({result.byte_count:,} bytes), {result.unchanged} already present; all verified."
    )
    return 0


def _run_data(arguments: argparse.Namespace) -> int:
    if arguments.data_command == "remote":
        return _run_remote(arguments)
    if arguments.data_command == "quality":
        report = _write_quality_report(arguments.warehouse, arguments.report_directory)
        print(f"Data-quality report: {report}")
        return 0
    if arguments.data_command == "fingerprint":
        first = fingerprint(arguments.warehouse)
        second = None if arguments.compare is None else fingerprint(arguments.compare)
        differences = 0
        for table, (count, digest) in first.items():
            other = None if second is None else second.get(table)
            marker = ""
            if second is not None:
                marker = "  same" if other == (count, digest) else "  DIFFERS"
            differences += marker == "  DIFFERS"
            print(f"{table:<45} {count:>10,}  {digest}{marker}")
        if second is not None and set(second) != set(first):
            differences += 1
            print(f"Tables differ: {sorted(set(first) ^ set(second))}")
        if second is not None:
            print("Identical." if not differences else f"{differences} tables differ.")
        return 1 if differences else 0
    configuration = load_corpus(arguments.corpus)
    catalog = load_catalog(
        configuration, arguments.raw_directory, download=arguments.data_command == "catalog"
    )
    if arguments.data_command == "catalog":
        print(f"Verified {len(catalog.matches)} matches in {len(configuration.seasons)} seasons.")
        print(f"Pinned source: {configuration.source_commit}")
        print(f"Index files: {len(catalog.sources)}; no event, lineup, or 360 files acquired.")
        for season in configuration.seasons:
            matches = [
                match
                for match in catalog.matches
                if match.season_key == (season.competition_id, season.season_id)
            ]
            print(
                f"  {season.competition_id}/{season.season_id}: {len(matches)} matches, "
                f"{season.role}, {season.coverage}; "
                f"360 available: {sum(match.has_three_sixty for match in matches)}; "
                f"missing metadata: {sum(bool(match.missing_metadata) for match in matches)}; "
                f"known coverage gaps: {season.known_missing_matches}"
            )
    elif arguments.data_command == "ingest":
        return _run_ingest(arguments, configuration, catalog)
    elif arguments.data_command == "split":
        path, assignments = freeze_splits(
            configuration,
            catalog,
            arguments.output_directory,
            version=arguments.split_version,
            reason=arguments.reason,
        )
        print(f"Created immutable split: {path}")
        for bucket in ("development", "validation", "test"):
            print(f"  {bucket}: {sum(row.bucket == bucket for row in assignments)}")
        print(f"Human-review matches: {sum(row.human_review for row in assignments)}")
        print("Probe judgments remain owner-owned; this command does not authorize bulk ingestion.")
    else:
        matches, split_checksum = select_development_matches(
            configuration,
            catalog,
            arguments.split_file,
            competition_id=arguments.competition,
            season_id=arguments.season,
            match_ids=arguments.match,
            include_inspected=arguments.include_inspected,
            season_keys=arguments.competition_season,
        )
        requests = plan_files(configuration, catalog, matches, split_checksum)
        print(
            f"Selected {len(matches)} development matches; {len(requests)} source files.",
            flush=True,
        )
        if arguments.dry_run:
            print("Dry run: no match files fetched or manifest entries written.")
            return 0

        def progress(completed: int, total: int) -> None:
            if completed % 25 == 0 or completed == total:
                print(f"Verified or acquired {completed}/{total} files.", flush=True)

        result = acquire_files(
            requests,
            arguments.raw_directory,
            fetch_payload,
            workers=arguments.workers,
            verify_only=arguments.verify_only,
            progress=progress,
        )
        report = {
            "finished_at": datetime.now(UTC).isoformat(),
            "source_commit": configuration.source_commit,
            "split_sha256": split_checksum,
            "development_match_ids": [match.match_id for match in matches],
            "verify_only": arguments.verify_only,
            "result": asdict(result),
        }
        report_path: Path = arguments.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            f"Complete: {result.downloaded} downloaded, {result.verified} verified, "
            f"{result.restored} restored, {result.registered} registered; "
            f"{result.byte_count:,} bytes. Report: {report_path}"
        )
    return 0


def _run_export(arguments: argparse.Namespace) -> int:
    """Write development matches' replay exports and refresh the export index.

    Every requested match is checked against the split first, from identifiers
    alone, so no event file is opened when any of them is held out.
    """
    match_ids = [MatchId(identifier) for identifier in dict.fromkeys(arguments.match)]
    require_development(match_ids, split_buckets(arguments.split_file))
    configuration = load_corpus(arguments.corpus)
    raw_directory: Path = arguments.raw_directory
    catalog = load_catalog(configuration, raw_directory)
    records = load_match_records(configuration, catalog, raw_directory, match_ids)
    events_directory = raw_directory / "statsbomb-open-data" / configuration.source_commit
    output_directory: Path = arguments.output_directory
    output_directory.mkdir(parents=True, exist_ok=True)
    index_path = output_directory / "index.json"
    entries: dict[int, dict[str, object]] = {}
    if index_path.exists():
        for entry in json.loads(index_path.read_text(encoding="utf-8")):
            entries[int(entry["id"])] = entry
    for match_id in match_ids:
        events_path = events_directory / "data/events" / f"{match_id}.json"
        if not events_path.exists():
            raise ValueError(f"no event file for match {match_id} at {events_path}")
        record = records[match_id]
        export = build_match_export(load_events(events_path, match_id), record)
        output_path = output_directory / f"{match_id}.json"
        output_path.write_text(
            json.dumps(export, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        # Pre-match metadata only: the index never carries a result or a card count.
        entries[match_id] = {
            "id": match_id,
            "date": record.match_date.isoformat(),
            "competition": record.competition_name,
            "home": record.home_team.name,
            "away": record.away_team.name,
        }
        print(f"Wrote {output_path} ({len(cast(list[object], export['cards']))} cards)")
    index_path.write_text(
        json.dumps([entries[key] for key in sorted(entries)], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Choose concrete adapters and run the application.

    This is the only place that picks concrete implementations: the StatsBomb
    adapter, the replay engine, the detector with its settings, and the
    template. Keeping that choice here keeps the domain free of infrastructure.
    """
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "data":
        try:
            return _run_data(arguments)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    if arguments.command == "export":
        try:
            return _run_export(arguments)
        except (OSError, ValueError) as error:
            parser.error(str(error))
    if arguments.command != "replay":
        parser.print_help()
        return 0

    match_id = MatchId(arguments.match)
    events_directory: Path = arguments.events_dir or (
        Path("data/raw/statsbomb-open-data")
        / load_corpus(Path("catalog/corpus.toml")).source_commit
        / "data/events"
    )
    events_path = events_directory / f"{match_id}.json"
    if not events_path.exists():
        parser.error(f"no event file for match {match_id} at {events_path}")

    events = load_events(events_path, match_id)
    if arguments.facts:
        for fact in replay(events, RecordedMatchFactsDetector()):
            print(f"[{render_clock(fact.fired_at)}] {render_match_fact(fact)}")
            if arguments.evidence:
                print("\n".join(render_match_fact_evidence(fact)))
            else:
                print(f"  recorded event: {fact.evidence_event_id}")
        print(ATTRIBUTION)
        return 0
    events_by_identifier = {event.identifier: event for event in events}
    cards = build_card_stream(events)
    if not cards:
        print("No cards.")
    for card in cards:
        if isinstance(card, AttackingBurst):
            print(f"[{render_clock(card.fired_at)}] {render_attacking_burst(card)}")
            if arguments.evidence:
                shots = [events_by_identifier[identifier] for identifier in card.recent_shot_ids]
                print("\n".join(render_attacking_burst_evidence(card, shots)))
            else:
                print(f"  recent shots: {', '.join(card.recent_shot_ids)}")
                print(f"  recent entries: {', '.join(card.recent_entry_ids)}")
            continue
        print(f"[{render_clock(card.fired_at)}] {render_attacking_side_shift(card)}")
        if arguments.evidence:
            recent = [events_by_identifier[identifier] for identifier in card.recent_entry_ids]
            baseline = [events_by_identifier[identifier] for identifier in card.baseline_entry_ids]
            print("\n".join(render_evidence(card, recent, baseline)))
        else:
            print(f"  recent entries: {', '.join(card.recent_entry_ids)}")
            print(f"  baseline entries: {', '.join(card.baseline_entry_ids)}")
    print(ATTRIBUTION)
    return 0
