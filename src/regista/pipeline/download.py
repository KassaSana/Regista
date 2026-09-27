"""Acquire immutable files with a serialized append-only manifest and restart checks."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from regista.domain.acquisition import AcquisitionResult, RawFileRequest
from regista.domain.catalog import CorpusConfiguration, IndexCatalog, MatchIndex
from regista.pipeline.catalog import (
    integer,
    object_list,
    object_record,
    sync_directory,
    text,
    write_once,
)
from regista.pipeline.splits import REVIEW_RULE, SPLIT_RULE, assign_splits


@dataclass(frozen=True)
class _CompletedFile:
    receipt: Mapping[str, object]
    outcome: str
    append: bool


def select_development_matches(
    configuration: CorpusConfiguration,
    catalog: IndexCatalog,
    split_path: Path,
    *,
    competition_id: int | None = None,
    season_id: int | None = None,
    match_ids: Sequence[int] = (),
    include_inspected: bool = False,
    season_keys: Sequence[tuple[int, int]] = (),
) -> tuple[tuple[MatchIndex, ...], str]:
    """Validate the frozen split before returning any match payload requests."""
    from dataclasses import asdict

    contents = split_path.read_bytes()
    document = object_record(json.loads(contents), "split")
    if any(
        document.get(key) != value
        for key, value in {
            "schema_version": 1,
            "rule": SPLIT_RULE,
            "review_rule": REVIEW_RULE,
            "review_seed": configuration.review_seed,
            "review_matches_per_core_season": 6,
        }.items()
    ):
        raise ValueError("unsupported split schema, rule, or review configuration")
    version = integer(document.get("version"), "split version")
    if split_path.name != f"v{version}.json":
        raise ValueError("split filename must agree with its version")
    for key in ("provider", "dataset", "source_commit"):
        if document.get(key) != getattr(configuration, key):
            raise ValueError(f"split {key} differs from the selected corpus")
    if document.get("configuration_sha256") != configuration.sha256:
        raise ValueError("split configuration checksum differs from the corpus")
    expected = [asdict(row) for row in assign_splits(configuration, catalog)]
    if document.get("assignments") != expected:
        raise ValueError("split assignments do not match the frozen chronological rule")
    sources = [
        {
            "relative_path": source.relative_path,
            "sha256": source.sha256,
            "byte_count": source.byte_count,
        }
        for source in catalog.sources
    ]
    if document.get("index_sources") != sources:
        raise ValueError("split index checksums differ from the verified catalog")
    assignments = {
        integer(row.get("match_id"), "match_id"): text(row.get("bucket"), "bucket")
        for value in object_list(document.get("assignments"), "assignments")
        for row in [object_record(value, "assignment")]
    }
    if (competition_id is None) != (season_id is None):
        raise ValueError("competition and season must be selected together")
    keys = list(season_keys)
    if competition_id is not None and season_id is not None:
        keys.append((competition_id, season_id))
    if not keys and not match_ids and not include_inspected:
        raise ValueError("select a competition-season, explicit matches, or inspected matches")
    selected = set(match_ids)
    if include_inspected:
        selected.update(configuration.inspected_match_ids)
    for identifier in selected:
        if assignments.get(identifier) != "development":
            raise ValueError(
                f"match {identifier} is absent or held out; development acquisition only"
            )
    for key in keys:
        season_matches = [match for match in catalog.matches if match.season_key == key]
        if not season_matches:
            raise ValueError(f"competition-season {key[0]}:{key[1]} is absent from the corpus")
        selected.update(
            match.match_id
            for match in season_matches
            if assignments[match.match_id] == "development"
        )
    if not selected:
        raise ValueError("selection contains no development matches")
    return (
        tuple(
            sorted(
                (match for match in catalog.matches if match.match_id in selected),
                key=lambda match: match.match_id,
            )
        ),
        hashlib.sha256(contents).hexdigest(),
    )


def file_checksum(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def _request_identity(request: RawFileRequest) -> dict[str, object]:
    return {
        "provider": request.provider,
        "dataset": request.dataset,
        "source_commit": request.source_commit,
        "url": request.url,
        "relative_path": request.relative_path,
        "kind": request.kind,
        "provider_match_id": request.provider_match_id,
        "provider_last_updated": request.provider_last_updated,
        "license_class": request.license_class,
    }


def read_manifest(path: Path) -> dict[str, Mapping[str, object]]:
    records: dict[str, Mapping[str, object]] = {}
    if not path.exists():
        return records
    with path.open("rb") as source:
        for number, line in enumerate(source, 1):
            if not line.endswith(b"\n"):
                raise ValueError(f"manifest line {number} is incomplete; audit before recovery")
            record = object_record(json.loads(line), f"manifest line {number}")
            relative_path = text(record.get("relative_path"), "relative_path")
            if relative_path in records:
                raise ValueError(f"duplicate manifest file: {relative_path}")
            text(record.get("sha256"), "sha256")
            text(record.get("retrieved_at"), "retrieved_at")
            integer(record.get("bytes"), "bytes", minimum=0)
            records[relative_path] = record
    return records


def _complete_file(
    request: RawFileRequest,
    root: Path,
    recorded: Mapping[str, object] | None,
    fetch: Callable[[str], bytes],
    verify_only: bool,
) -> _CompletedFile:
    relative = PurePosixPath(request.relative_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in request.relative_path:
        raise ValueError("raw-file path must be a relative path beneath the raw directory")
    path = root / relative
    identity = _request_identity(request)
    if recorded is not None:
        if any(recorded.get(key) != value for key, value in identity.items()):
            raise ValueError(f"manifest provenance mismatch: {request.relative_path}")
        expected = text(recorded.get("sha256"), "sha256")
        if request.expected_sha256 is not None and request.expected_sha256 != expected:
            raise ValueError("manifest checksum differs from the verified index provenance")
        if path.exists():
            checksum, byte_count = file_checksum(path)
            if checksum != expected or byte_count != recorded.get("bytes"):
                raise ValueError(f"raw-file checksum mismatch: {request.relative_path}")
            return _CompletedFile(recorded, "verified", False)
        if verify_only:
            raise ValueError(f"manifest file is missing: {request.relative_path}")
        contents = fetch(request.url)
        if hashlib.sha256(contents).hexdigest() != expected or len(contents) != recorded.get(
            "bytes"
        ):
            raise ValueError(f"redownload differs from manifest: {request.relative_path}")
        write_once(path, contents, allow_identical=True)
        return _CompletedFile(recorded, "restored", False)
    if verify_only:
        raise ValueError(f"file has no manifest receipt: {request.relative_path}")
    if request.expected_sha256 is not None and path.exists():
        checksum, byte_count = file_checksum(path)
        if checksum != request.expected_sha256:
            raise ValueError(f"index checksum mismatch: {request.relative_path}")
        outcome = "registered"
    else:
        # A crash after publishing a file but before appending its receipt leaves an orphan.
        # Re-fetch its pinned source and require identical bytes before registering it.
        contents = fetch(request.url)
        checksum, byte_count = hashlib.sha256(contents).hexdigest(), len(contents)
        if request.expected_sha256 is not None and checksum != request.expected_sha256:
            raise ValueError(f"download differs from index provenance: {request.relative_path}")
        write_once(path, contents, allow_identical=True)
        outcome = "downloaded"
    receipt = identity | {
        "sha256": checksum,
        "bytes": byte_count,
        "retrieved_at": request.retrieved_at or datetime.now(UTC).isoformat(),
        "split_bucket": request.split_bucket,
        "split_sha256": request.split_sha256,
    }
    return _CompletedFile(receipt, outcome, True)


def acquire_files(
    requests: Sequence[RawFileRequest],
    raw_directory: Path,
    fetch: Callable[[str], bytes],
    *,
    workers: int = 4,
    verify_only: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> AcquisitionResult:
    """Hold a process lock; workers publish files, one writer appends durable receipts."""
    if not 1 <= workers <= 8:
        raise ValueError("download workers must be between one and eight")
    if len({request.relative_path for request in requests}) != len(requests):
        raise ValueError("duplicate raw-file requests")
    raw_directory.mkdir(parents=True, exist_ok=True)
    manifest = raw_directory / "manifest.jsonl"
    counts = {"downloaded": 0, "verified": 0, "restored": 0, "registered": 0}
    byte_count = 0
    with (raw_directory / ".acquisition.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("another acquisition process holds the raw-directory lock") from None
        records = read_manifest(manifest)
        # Append mode is never opened during verification-only runs.
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    _complete_file,
                    request,
                    raw_directory,
                    records.get(request.relative_path),
                    fetch,
                    verify_only,
                )
                for request in requests
            ]
            try:
                for completed, future in enumerate(as_completed(futures), 1):
                    result = future.result()
                    if result.append:
                        with manifest.open("ab") as output:
                            output.write(
                                (json.dumps(dict(result.receipt), sort_keys=True) + "\n").encode()
                            )
                            output.flush()
                            os.fsync(output.fileno())
                        sync_directory(raw_directory)
                    counts[result.outcome] += 1
                    byte_count += integer(result.receipt.get("bytes"), "bytes", minimum=0)
                    if progress is not None:
                        progress(completed, len(requests))
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
    return AcquisitionResult(
        len(requests),
        counts["downloaded"],
        counts["verified"],
        counts["restored"],
        counts["registered"],
        byte_count,
    )
