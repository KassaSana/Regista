"""Back up and restore Regista data through a private object store.

Local paths stay the working copy that every other command uses; the object
store is durable storage and a cache. This module is cloud-neutral: the
composition root injects an ``ObjectStore``.

Rules enforced here:
- Only development data moves. Pushing refuses any match receipt that is not
  development under the current split; pulling accepts only development
  matches, and explicitly named matches are checked against the split file
  before any network request.
- Nothing is overwritten. An existing object with a different checksum is a
  failure, just like ``write_once`` locally. There is no delete operation.
- Every restored byte is verified against the manifest's SHA-256 before it is
  published locally.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol

from regista.pipeline.catalog import (
    integer,
    object_list,
    object_record,
    sync_directory,
    text,
    write_once,
)
from regista.pipeline.download import file_checksum, read_manifest

RAW_PREFIX = "raw/"
MANIFEST_PREFIX = "manifests/"
LATEST_MANIFEST_KEY = "manifests/latest.json"
WAREHOUSE_PREFIX = "warehouse/"
LATEST_WAREHOUSE_KEY = "warehouse/latest.json"
REPORT_PREFIX = "reports/downloads/"
MATCH_FILE_KINDS = frozenset({"events", "lineups"})
INDEX_KINDS = frozenset({"competitions", "matches"})
SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RemoteObject:
    key: str
    byte_count: int
    sha256: str | None


class ObjectStore(Protocol):
    """The port to a private object store. Deliberately has no delete."""

    def stat(self, key: str) -> RemoteObject | None: ...

    def upload(self, path: Path, key: str, sha256: str) -> None: ...

    def download(self, key: str, path: Path) -> None: ...

    def put_bytes(self, key: str, contents: bytes, sha256: str) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...

    def keys(self, prefix: str) -> Iterator[str]: ...


class RemoteConflictError(ValueError):
    """Raised when a remote object exists with different contents."""


@dataclass
class TransferResult:
    uploaded: int = 0
    downloaded: int = 0
    unchanged: int = 0
    byte_count: int = 0
    notes: list[str] = field(default_factory=list[str])


@dataclass
class VerifyResult:
    checked: int = 0
    problems: list[str] = field(default_factory=list[str])
    snapshots: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems


def raw_key(relative_path: str) -> str:
    return RAW_PREFIX + _safe_relative(relative_path)


def _safe_relative(relative_path: str) -> str:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts or "\\" in relative_path or not path.parts:
        raise ValueError(f"unsafe relative path: {relative_path!r}")
    return path.as_posix()


def _sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


# Selection guards -------------------------------------------------------------------------


def split_buckets(split_path: Path) -> dict[int, str]:
    """Read match buckets from a frozen split file (identifiers only, no network)."""
    document = object_record(json.loads(split_path.read_bytes()), "split")
    return {
        integer(row.get("match_id"), "match_id"): text(row.get("bucket"), "bucket")
        for value in object_list(document.get("assignments"), "assignments")
        for row in [object_record(value, "assignment")]
    }


def require_development(match_ids: Collection[int], buckets: Mapping[int, str]) -> None:
    """Refuse held-out or unknown matches before anything is transferred."""
    refused = sorted(
        identifier for identifier in match_ids if buckets.get(identifier) != "development"
    )
    if refused:
        raise ValueError(
            f"matches {refused} are held out or absent from the split; development only"
        )


def _match_id(receipt: Mapping[str, object]) -> int | None:
    value = receipt.get("provider_match_id")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _development_receipts(
    manifest: Mapping[str, Mapping[str, object]], development_ids: Collection[int]
) -> list[Mapping[str, object]]:
    """Index and development match receipts; any other match receipt stops the push."""
    selected: list[Mapping[str, object]] = []
    for relative_path, receipt in sorted(manifest.items()):
        kind = receipt.get("kind")
        if kind in INDEX_KINDS:
            selected.append(receipt)
        elif kind in MATCH_FILE_KINDS:
            match_id = _match_id(receipt)
            if match_id not in development_ids or receipt.get("split_bucket") != "development":
                raise ValueError(
                    f"{relative_path} belongs to match {match_id}, which is not development; "
                    "held-out files never go to remote storage"
                )
            selected.append(receipt)
        else:
            raise ValueError(f"{relative_path} has unsupported kind {kind!r} for remote storage")
    return selected


# Push -------------------------------------------------------------------------------------


def _push_file(
    store: ObjectStore, path: Path, key: str, sha256: str, byte_count: int
) -> tuple[str, int]:
    existing = store.stat(key)
    if existing is not None:
        if existing.sha256 == sha256 and existing.byte_count == byte_count:
            return "unchanged", 0
        raise RemoteConflictError(f"{key} already exists with different contents")
    store.upload(path, key, sha256)
    return "uploaded", byte_count


def push_raw(
    store: ObjectStore,
    raw_directory: Path,
    manifest: Mapping[str, Mapping[str, object]],
    development_ids: Collection[int],
    extra_paths: Sequence[str],
    *,
    reports: Sequence[Path] = (),
    workers: int = 4,
    progress: Callable[[int, int], None] | None = None,
) -> TransferResult:
    """Upload verified development raw files, a manifest snapshot, and acquisition reports.

    Idempotent: objects already present with the same checksum are skipped. The manifest
    pointer moves only forward (the remote manifest must be a prefix of the local one).
    """
    if not 1 <= workers <= 8:
        raise ValueError("remote workers must be between one and eight")
    receipts = _development_receipts(manifest, development_ids)
    planned: list[tuple[Path, str, str, int]] = []
    for receipt in receipts:
        relative = _safe_relative(text(receipt.get("relative_path"), "relative_path"))
        path = raw_directory / relative
        sha256, byte_count = file_checksum(path)
        if sha256 != receipt.get("sha256") or byte_count != receipt.get("bytes"):
            raise ValueError(f"local file differs from its manifest receipt: {relative}")
        planned.append((path, raw_key(relative), sha256, byte_count))
    for relative in extra_paths:
        path = raw_directory / _safe_relative(relative)
        sha256, byte_count = file_checksum(path)
        planned.append((path, raw_key(relative), sha256, byte_count))
    manifest_path = raw_directory / "manifest.jsonl"
    manifest_bytes = manifest_path.read_bytes()
    _require_forward_manifest(store, manifest_bytes)

    result = TransferResult()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_push_file, store, *item) for item in planned]
        for number, future in enumerate(futures, 1):
            outcome, byte_count = future.result()
            if outcome == "uploaded":
                result.uploaded += 1
            else:
                result.unchanged += 1
            result.byte_count += byte_count
            if progress is not None:
                progress(number, len(futures))

    manifest_sha = _sha256(manifest_bytes)
    snapshot_key = f"{MANIFEST_PREFIX}manifest-{manifest_sha}.jsonl"
    if store.stat(snapshot_key) is None:
        store.put_bytes(snapshot_key, manifest_bytes, manifest_sha)
        result.notes.append(f"manifest snapshot {manifest_sha[:12]} uploaded")
    pointer = json.dumps(
        {
            "sha256": manifest_sha,
            "key": snapshot_key,
            "receipts": len(manifest),
            "bytes": len(manifest_bytes),
            "pushed_at": datetime.now(UTC).isoformat(),
        },
        indent=2,
    ).encode()
    store.put_bytes(LATEST_MANIFEST_KEY, pointer, _sha256(pointer))
    for report in reports:
        contents = report.read_bytes()
        digest = _sha256(contents)
        key = f"{REPORT_PREFIX}{report.stem}-{digest[:12]}{report.suffix}"
        if store.stat(key) is None:
            store.put_bytes(key, contents, digest)
            result.uploaded += 1
    return result


def _remote_manifest(store: ObjectStore, sha256: str | None = None) -> tuple[bytes, str] | None:
    if sha256 is None:
        if store.stat(LATEST_MANIFEST_KEY) is None:
            return None
        pointer = object_record(
            json.loads(store.get_bytes(LATEST_MANIFEST_KEY)), "manifest pointer"
        )
        sha256 = text(pointer.get("sha256"), "manifest pointer sha256")
    contents = store.get_bytes(f"{MANIFEST_PREFIX}manifest-{sha256}.jsonl")
    if _sha256(contents) != sha256:
        raise ValueError(f"remote manifest snapshot {sha256[:12]} fails its checksum")
    return contents, sha256


def _require_forward_manifest(store: ObjectStore, local: bytes) -> None:
    remote = _remote_manifest(store)
    if remote is not None and not local.startswith(remote[0]):
        raise RemoteConflictError(
            "the remote manifest is not a prefix of the local one; pull it before pushing"
        )


# Pull -------------------------------------------------------------------------------------


def pull_manifest(store: ObjectStore, raw_directory: Path, sha256: str | None = None) -> str:
    """Bring the local append-only manifest up to the remote snapshot; return its checksum."""
    remote = _remote_manifest(store, sha256)
    if remote is None:
        raise ValueError("remote storage has no manifest; push from a machine that has the corpus")
    contents, digest = remote
    path = raw_directory / "manifest.jsonl"
    local = path.read_bytes() if path.exists() else b""
    if local.startswith(contents):
        return digest  # local is equal or already ahead
    if not contents.startswith(local):
        raise RemoteConflictError("local and remote manifests diverge; audit before restoring")
    raw_directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".manifest.jsonl.pulling")
    temporary.write_bytes(contents)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    sync_directory(raw_directory)
    return digest


def _pull_file(
    store: ObjectStore,
    raw_directory: Path,
    relative: str,
    sha256: str | None,
    byte_count: int | None,
) -> tuple[str, int]:
    path = raw_directory / relative
    if path.exists():
        local_sha, local_bytes = file_checksum(path)
        if sha256 is None or (local_sha == sha256 and local_bytes == byte_count):
            return "unchanged", 0
        raise ValueError(f"local file differs from its manifest receipt: {relative}")
    contents = store.get_bytes(raw_key(relative))
    expected = sha256
    if expected is None:
        remote = store.stat(raw_key(relative))
        expected = None if remote is None else remote.sha256
    if expected is None or _sha256(contents) != expected:
        raise ValueError(f"restored bytes fail their checksum: {relative}")
    if byte_count is not None and len(contents) != byte_count:
        raise ValueError(f"restored byte count differs from the manifest: {relative}")
    write_once(path, contents, allow_identical=True)
    return "downloaded", len(contents)


def pull_metadata(
    store: ObjectStore, raw_directory: Path, extra_paths: Sequence[str]
) -> TransferResult:
    """Restore index files (checked against the manifest) and provenance files."""
    manifest = read_manifest(raw_directory / "manifest.jsonl")
    result = TransferResult()
    items: list[tuple[str, str | None, int | None]] = [
        (
            _safe_relative(text(receipt.get("relative_path"), "relative_path")),
            text(receipt.get("sha256"), "sha256"),
            integer(receipt.get("bytes"), "bytes", minimum=0),
        )
        for receipt in manifest.values()
        if receipt.get("kind") in INDEX_KINDS
    ]
    items.extend((_safe_relative(relative), None, None) for relative in extra_paths)
    for relative, sha256, byte_count in sorted(items):
        outcome, transferred = _pull_file(store, raw_directory, relative, sha256, byte_count)
        _count(result, outcome, transferred)
    return result


def pull_match_files(
    store: ObjectStore,
    raw_directory: Path,
    manifest: Mapping[str, Mapping[str, object]],
    match_ids: Collection[int],
    buckets: Mapping[int, str],
    *,
    workers: int = 4,
    progress: Callable[[int, int], None] | None = None,
) -> TransferResult:
    """Restore events and lineups for selected development matches, verifying every byte."""
    if not 1 <= workers <= 8:
        raise ValueError("remote workers must be between one and eight")
    require_development(match_ids, buckets)
    wanted = set(match_ids)
    items: list[tuple[str, str, int]] = []
    for receipt in manifest.values():
        match_id = _match_id(receipt)
        if receipt.get("kind") not in MATCH_FILE_KINDS or match_id not in wanted:
            continue
        if receipt.get("split_bucket") != "development":
            raise ValueError(f"match {match_id} was not acquired as development data")
        items.append(
            (
                _safe_relative(text(receipt.get("relative_path"), "relative_path")),
                text(receipt.get("sha256"), "sha256"),
                integer(receipt.get("bytes"), "bytes", minimum=0),
            )
        )
    found = {
        _match_id(receipt)
        for receipt in manifest.values()
        if receipt.get("kind") in MATCH_FILE_KINDS
    }
    missing = sorted(wanted - found)
    if missing:
        raise ValueError(f"no manifest receipts for matches {missing}; acquire them first")
    result = TransferResult()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_pull_file, store, raw_directory, *item) for item in sorted(items)
        ]
        for number, future in enumerate(futures, 1):
            outcome, transferred = future.result()
            _count(result, outcome, transferred)
            if progress is not None:
                progress(number, len(futures))
    return result


def _count(result: TransferResult, outcome: str, transferred: int) -> None:
    if outcome == "downloaded":
        result.downloaded += 1
    else:
        result.unchanged += 1
    result.byte_count += transferred


# Verify -----------------------------------------------------------------------------------


def verify_remote(
    store: ObjectStore,
    manifest: Mapping[str, Mapping[str, object]],
    development_ids: Collection[int],
    extra_paths: Sequence[str],
    *,
    deep: bool = False,
    scratch_directory: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> VerifyResult:
    """Compare remote storage with the local manifest; ``deep`` re-hashes every object."""
    result = VerifyResult()
    receipts = _development_receipts(manifest, development_ids)
    expected: dict[str, tuple[str, int]] = {
        raw_key(text(receipt.get("relative_path"), "relative_path")): (
            text(receipt.get("sha256"), "sha256"),
            integer(receipt.get("bytes"), "bytes", minimum=0),
        )
        for receipt in receipts
    }
    for number, (key, (sha256, byte_count)) in enumerate(sorted(expected.items()), 1):
        result.checked += 1
        remote = store.stat(key)
        if remote is None:
            result.problems.append(f"missing: {key}")
        elif remote.byte_count != byte_count or remote.sha256 != sha256:
            result.problems.append(f"size or checksum metadata differs: {key}")
        elif deep and _sha256(store.get_bytes(key)) != sha256:
            result.problems.append(f"contents fail their checksum: {key}")
        if progress is not None:
            progress(number, len(expected))
    allowed = set(expected) | {raw_key(relative) for relative in extra_paths}
    for relative in extra_paths:
        result.checked += 1
        if store.stat(raw_key(relative)) is None:
            result.problems.append(f"missing: {raw_key(relative)}")
    # Leakage audit: every raw object must be a known development or metadata file.
    manifest_keys = {raw_key(path): receipt for path, receipt in manifest.items()}
    for key in store.keys(RAW_PREFIX):
        if key in allowed:
            continue
        receipt = manifest_keys.get(key)
        match_id = None if receipt is None else _match_id(receipt)
        if match_id is not None and match_id not in development_ids:
            result.problems.append(f"held-out match file in remote storage: {key}")
        else:
            result.problems.append(f"unexpected raw object: {key}")
    remote_manifest = _remote_manifest(store)
    if remote_manifest is None:
        result.problems.append("no remote manifest snapshot")
    result.snapshots = _verify_snapshots(store, result, deep, scratch_directory)
    return result


def _verify_snapshots(
    store: ObjectStore, result: VerifyResult, deep: bool, scratch_directory: Path | None
) -> int:
    count = 0
    for key in sorted(store.keys(WAREHOUSE_PREFIX)):
        if not key.endswith("/snapshot.json"):
            continue
        count += 1
        snapshot = object_record(json.loads(store.get_bytes(key)), "snapshot")
        warehouse = object_record(snapshot.get("warehouse"), "snapshot warehouse")
        database_key = text(warehouse.get("key"), "warehouse key")
        sha256 = text(warehouse.get("sha256"), "warehouse sha256")
        remote = store.stat(database_key)
        if remote is None:
            result.problems.append(f"snapshot database missing: {database_key}")
            continue
        if remote.byte_count != warehouse.get("bytes") or remote.sha256 != sha256:
            result.problems.append(f"snapshot size or checksum metadata differs: {database_key}")
            continue
        if deep:
            if scratch_directory is None:
                raise ValueError("deep verification of snapshots needs a scratch directory")
            scratch_directory.mkdir(parents=True, exist_ok=True)
            temporary = scratch_directory / ".snapshot-verify.duckdb"
            try:
                store.download(database_key, temporary)
                if file_checksum(temporary)[0] != sha256:
                    result.problems.append(f"snapshot contents fail their checksum: {database_key}")
            finally:
                temporary.unlink(missing_ok=True)
    return count


# Warehouse snapshots ----------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotFacts:
    """What the warehouse says about itself (supplied by the warehouse package)."""

    ingest_run: Mapping[str, object]
    non_development_matches: int
    fingerprint: Mapping[str, tuple[int, str]]


def _fingerprint_json(fingerprint: Mapping[str, tuple[int, str]]) -> dict[str, list[object]]:
    return {table: [count, digest] for table, (count, digest) in sorted(fingerprint.items())}


def push_warehouse(
    store: ObjectStore,
    warehouse_path: Path,
    facts: SnapshotFacts,
    provenance: Mapping[str, object],
    quality_files: Sequence[Path] = (),
    *,
    allow_dirty: bool = False,
) -> TransferResult:
    """Store a development warehouse snapshot with enough provenance to reproduce it."""
    if facts.non_development_matches:
        raise ValueError(
            f"warehouse holds {facts.non_development_matches} non-development matches; "
            "only the development warehouse may be stored"
        )
    run_id = text(facts.ingest_run.get("ingest_run_id"), "ingest_run_id")
    if facts.ingest_run.get("git_dirty") is True and not allow_dirty:
        raise ValueError(
            "the warehouse was built from uncommitted code, so it cannot be reproduced from git; "
            "commit and rebuild, or pass --allow-dirty to store it anyway"
        )
    manifest_sha = provenance.get("manifest_sha256")
    if (
        not isinstance(manifest_sha, str)
        or store.stat(f"{MANIFEST_PREFIX}manifest-{manifest_sha}.jsonl") is None
    ):
        raise ValueError("push the raw corpus and its manifest before the warehouse snapshot")
    prefix = f"{WAREHOUSE_PREFIX}{run_id}/"
    snapshot_key = prefix + "snapshot.json"
    fingerprint = _fingerprint_json(facts.fingerprint)
    result = TransferResult()
    if store.stat(snapshot_key) is not None:
        existing = object_record(json.loads(store.get_bytes(snapshot_key)), "snapshot")
        if existing.get("fingerprint") != fingerprint:
            raise RemoteConflictError(f"snapshot {run_id} exists with a different fingerprint")
        result.unchanged += 1
        result.notes.append(f"snapshot {run_id} already stored")
        return result
    sha256, byte_count = file_checksum(warehouse_path)
    database_key = prefix + warehouse_path.name
    outcome, transferred = _push_file(store, warehouse_path, database_key, sha256, byte_count)
    if outcome == "uploaded":
        result.uploaded += 1
    result.byte_count += transferred
    for path in quality_files:
        contents = path.read_bytes()
        store.put_bytes(f"{prefix}dq{path.suffix}", contents, _sha256(contents))
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "ingest_run_id": run_id,
        "stored_at": datetime.now(UTC).isoformat(),
        "warehouse": {"key": database_key, "sha256": sha256, "bytes": byte_count},
        "ingest_run": dict(facts.ingest_run),
        **dict(provenance),
        "fingerprint": fingerprint,
    }
    contents = json.dumps(snapshot, indent=2, sort_keys=True, default=str).encode()
    # The snapshot record is written last: its presence means the snapshot is complete.
    store.put_bytes(snapshot_key, contents, _sha256(contents))
    pointer = json.dumps({"ingest_run_id": run_id, "key": snapshot_key}, indent=2).encode()
    store.put_bytes(LATEST_WAREHOUSE_KEY, pointer, _sha256(pointer))
    result.notes.append(f"snapshot {run_id} stored")
    return result


def pull_warehouse(
    store: ObjectStore,
    run: str,
    output: Path,
    fingerprint: Callable[[Path], Mapping[str, tuple[int, str]]],
    *,
    replace: bool = False,
) -> tuple[str, TransferResult]:
    """Restore a snapshot, verify its checksum and fingerprint, then publish it atomically."""
    if run == "latest":
        if store.stat(LATEST_WAREHOUSE_KEY) is None:
            raise ValueError("remote storage has no warehouse snapshot")
        pointer = object_record(json.loads(store.get_bytes(LATEST_WAREHOUSE_KEY)), "pointer")
        run = text(pointer.get("ingest_run_id"), "ingest_run_id")
    snapshot_key = f"{WAREHOUSE_PREFIX}{run}/snapshot.json"
    if store.stat(snapshot_key) is None:
        raise ValueError(f"no complete warehouse snapshot {run}")
    snapshot = object_record(json.loads(store.get_bytes(snapshot_key)), "snapshot")
    warehouse = object_record(snapshot.get("warehouse"), "snapshot warehouse")
    if output.exists() and not replace:
        raise ValueError(f"{output} exists; pass --replace to overwrite it")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.pulling")
    temporary.unlink(missing_ok=True)
    try:
        store.download(text(warehouse.get("key"), "warehouse key"), temporary)
        sha256, byte_count = file_checksum(temporary)
        if sha256 != warehouse.get("sha256") or byte_count != warehouse.get("bytes"):
            raise ValueError(f"snapshot {run} fails its checksum")
        if _fingerprint_json(fingerprint(temporary)) != snapshot.get("fingerprint"):
            raise ValueError(f"snapshot {run} fails its table fingerprint")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return run, TransferResult(downloaded=1, byte_count=byte_count)
