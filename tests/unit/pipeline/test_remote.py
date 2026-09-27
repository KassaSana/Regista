"""Remote backup and restore: checksums, provenance, idempotency, and development-only guards."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from directory_store import DirectoryStore
from synthetic_warehouse import build_warehouse, standard_match

from regista.pipeline.download import read_manifest
from regista.pipeline.remote import (
    LATEST_MANIFEST_KEY,
    RemoteConflictError,
    SnapshotFacts,
    pull_manifest,
    pull_match_files,
    pull_metadata,
    pull_warehouse,
    push_raw,
    push_warehouse,
    raw_key,
    require_development,
    verify_remote,
)
from regista.warehouse.research import fingerprint, snapshot_facts

COMMIT = "c" * 40
PREFIX = f"statsbomb-open-data/{COMMIT}"
PROVENANCE = f"{PREFIX}/metadata-provenance/{'d' * 64}.json"
BUCKETS = {1: "development", 2: "development", 3: "validation"}
DEVELOPMENT = {1, 2}


def _receipt(relative: str, contents: bytes, kind: str, match_id: int | None) -> dict[str, object]:
    return {
        "relative_path": relative,
        "kind": kind,
        "provider_match_id": match_id,
        "sha256": hashlib.sha256(contents).hexdigest(),
        "bytes": len(contents),
        "retrieved_at": "2026-09-27T00:00:00+00:00",
        "source_commit": COMMIT,
        "split_bucket": None if match_id is None else BUCKETS[match_id],
    }


def make_raw(directory: Path, match_ids: tuple[int, ...] = (1, 2)) -> Path:
    """A tiny raw directory: two indexes, match files, provenance, and a manifest."""
    raw = directory / "raw"
    files: list[tuple[str, bytes, str, int | None]] = [
        (f"{PREFIX}/data/competitions.json", b'[{"competition_id": 2}]', "competitions", None),
        (f"{PREFIX}/data/matches/2/27.json", b'[{"match_id": 1}]', "matches", None),
    ]
    for match_id in match_ids:
        for kind in ("events", "lineups"):
            body = json.dumps({"kind": kind, "match": match_id}).encode()
            files.append((f"{PREFIX}/data/{kind}/{match_id}.json", body, kind, match_id))
    lines: list[str] = []
    for relative, contents, kind, match_id in files:
        path = raw / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        lines.append(json.dumps(_receipt(relative, contents, kind, match_id), sort_keys=True))
    (raw / PROVENANCE).parent.mkdir(parents=True, exist_ok=True)
    (raw / PROVENANCE).write_bytes(b'{"provenance": true}')
    (raw / "manifest.jsonl").write_text("\n".join(lines) + "\n")
    return raw


def push(store: DirectoryStore, raw: Path) -> None:
    push_raw(store, raw, read_manifest(raw / "manifest.jsonl"), DEVELOPMENT, [PROVENANCE])


@pytest.fixture
def pushed(tmp_path: Path) -> tuple[DirectoryStore, Path]:
    raw = make_raw(tmp_path / "local")
    store = DirectoryStore(tmp_path / "bucket")
    push(store, raw)
    return store, raw


# Push ------------------------------------------------------------------------------------


def test_push_uploads_files_manifest_and_pointer_with_checksums(
    pushed: tuple[DirectoryStore, Path],
) -> None:
    store, raw = pushed

    keys = set(store.keys(""))
    assert raw_key(f"{PREFIX}/data/events/1.json") in keys
    assert raw_key(PROVENANCE) in keys
    manifest_sha = hashlib.sha256((raw / "manifest.jsonl").read_bytes()).hexdigest()
    assert f"manifests/manifest-{manifest_sha}.jsonl" in keys
    pointer = json.loads(store.get_bytes(LATEST_MANIFEST_KEY))
    assert (pointer["sha256"], pointer["receipts"]) == (manifest_sha, 6)
    events = raw / f"{PREFIX}/data/events/1.json"
    assert (
        store.metadata[raw_key(f"{PREFIX}/data/events/1.json")]
        == hashlib.sha256(events.read_bytes()).hexdigest()
    )


def test_a_second_push_uploads_nothing(pushed: tuple[DirectoryStore, Path]) -> None:
    store, raw = pushed
    store.requests.clear()

    result = push_raw(store, raw, read_manifest(raw / "manifest.jsonl"), DEVELOPMENT, [PROVENANCE])

    assert (result.uploaded, result.unchanged) == (0, 7)
    assert not any(kind == "upload" for kind, _ in store.requests)


def test_push_refuses_held_out_receipts_before_uploading_anything(tmp_path: Path) -> None:
    raw = make_raw(tmp_path / "local", match_ids=(1, 3))
    store = DirectoryStore(tmp_path / "bucket")

    with pytest.raises(ValueError, match="not development"):
        push(store, raw)
    assert store.transfers() == 0


def test_push_refuses_a_local_file_that_differs_from_its_receipt(tmp_path: Path) -> None:
    raw = make_raw(tmp_path / "local")
    (raw / f"{PREFIX}/data/events/2.json").write_bytes(b"tampered")
    store = DirectoryStore(tmp_path / "bucket")

    with pytest.raises(ValueError, match="differs from its manifest receipt"):
        push(store, raw)
    assert store.transfers() == 0


def test_push_never_overwrites_a_different_remote_object(tmp_path: Path) -> None:
    raw = make_raw(tmp_path / "local")
    store = DirectoryStore(tmp_path / "bucket")
    store.put_bytes(raw_key(f"{PREFIX}/data/events/1.json"), b"other", "0" * 64)

    with pytest.raises(RemoteConflictError, match="different contents"):
        push(store, raw)
    assert store.get_bytes(raw_key(f"{PREFIX}/data/events/1.json")) == b"other"


def test_push_refuses_to_move_the_manifest_pointer_sideways(
    pushed: tuple[DirectoryStore, Path], tmp_path: Path
) -> None:
    store, _ = pushed
    other = make_raw(tmp_path / "other", match_ids=(2,))

    with pytest.raises(RemoteConflictError, match="not a prefix"):
        push(store, other)


# Verify ----------------------------------------------------------------------------------


def verify(store: DirectoryStore, raw: Path, *, deep: bool = False) -> list[str]:
    manifest = read_manifest(raw / "manifest.jsonl")
    return verify_remote(store, manifest, DEVELOPMENT, [PROVENANCE], deep=deep).problems


def test_verify_passes_after_a_push_including_deep_checks(
    pushed: tuple[DirectoryStore, Path],
) -> None:
    store, raw = pushed

    assert verify(store, raw) == []
    assert verify(store, raw, deep=True) == []


def test_verify_detects_missing_resized_and_corrupted_objects(
    pushed: tuple[DirectoryStore, Path],
) -> None:
    store, raw = pushed
    events = raw_key(f"{PREFIX}/data/events/1.json")
    lineups = raw_key(f"{PREFIX}/data/lineups/1.json")
    index = raw_key(f"{PREFIX}/data/matches/2/27.json")
    (store.root / events).unlink()
    (store.root / lineups).write_bytes(b"x")
    original = (store.root / index).read_bytes()
    (store.root / index).write_bytes(bytes([original[0] ^ 1]) + original[1:])

    assert verify(store, raw) == [
        f"missing: {events}",
        f"size or checksum metadata differs: {lineups}",
    ]
    assert f"contents fail their checksum: {index}" in verify(store, raw, deep=True)


def test_verify_flags_objects_that_should_not_be_in_the_bucket(
    pushed: tuple[DirectoryStore, Path],
) -> None:
    store, raw = pushed
    stray = raw_key(f"{PREFIX}/data/events/3.json")
    store.put_bytes(stray, b"held out", "0" * 64)

    assert verify(store, raw) == [f"unexpected raw object: {stray}"]


# Pull ------------------------------------------------------------------------------------


def restore(store: DirectoryStore, target: Path, match_ids: list[int]) -> int:
    pull_manifest(store, target)
    pull_metadata(store, target, [PROVENANCE])
    result = pull_match_files(
        store, target, read_manifest(target / "manifest.jsonl"), match_ids, BUCKETS
    )
    return result.downloaded


def test_pull_restores_exact_bytes_on_a_clean_machine(
    pushed: tuple[DirectoryStore, Path], tmp_path: Path
) -> None:
    store, raw = pushed
    target = tmp_path / "clean" / "raw"

    assert restore(store, target, [1, 2]) == 4
    for path in raw.rglob("*"):
        if path.is_file():
            assert (target / path.relative_to(raw)).read_bytes() == path.read_bytes()


def test_pull_fetches_only_the_selected_matches_and_skips_present_files(
    pushed: tuple[DirectoryStore, Path], tmp_path: Path
) -> None:
    store, _ = pushed
    target = tmp_path / "clean" / "raw"

    assert restore(store, target, [1]) == 2
    assert not (target / f"{PREFIX}/data/events/2.json").exists()
    assert restore(store, target, [1]) == 0


def test_pull_refuses_held_out_matches_before_any_transfer(
    pushed: tuple[DirectoryStore, Path], tmp_path: Path
) -> None:
    store, _ = pushed
    store.requests.clear()

    with pytest.raises(ValueError, match="held out"):
        require_development([3], BUCKETS)
    with pytest.raises(ValueError, match="held out"):
        pull_match_files(store, tmp_path / "raw", {}, [1, 3], BUCKETS)
    assert store.requests == []


def test_pull_rejects_corrupted_remote_bytes_and_publishes_nothing(
    pushed: tuple[DirectoryStore, Path], tmp_path: Path
) -> None:
    store, _ = pushed
    key = raw_key(f"{PREFIX}/data/events/1.json")
    (store.root / key).write_bytes(b'{"kind": "events", "match": 9}')
    target = tmp_path / "clean" / "raw"

    with pytest.raises(ValueError, match="fail their checksum"):
        restore(store, target, [1])
    assert not (target / f"{PREFIX}/data/events/1.json").exists()


def test_pull_keeps_a_local_manifest_that_is_ahead_and_rejects_a_divergent_one(
    pushed: tuple[DirectoryStore, Path], tmp_path: Path
) -> None:
    store, raw = pushed
    ahead = tmp_path / "ahead"
    ahead.mkdir()
    extended = (raw / "manifest.jsonl").read_bytes() + b'{"relative_path": "x"}\n'
    (ahead / "manifest.jsonl").write_bytes(extended)
    pull_manifest(store, ahead)
    assert (ahead / "manifest.jsonl").read_bytes() == extended

    divergent = tmp_path / "divergent"
    divergent.mkdir()
    (divergent / "manifest.jsonl").write_bytes(b'{"relative_path": "y"}\n')
    with pytest.raises(RemoteConflictError, match="diverge"):
        pull_manifest(store, divergent)


# Warehouse snapshots ---------------------------------------------------------------------

FINGERPRINT = {"normalized.events": (10, "abc"), "analytical.team_matches": (2, "def")}


def facts(**changes: object) -> SnapshotFacts:
    run: dict[str, object] = {"ingest_run_id": "run1", "git_dirty": False}
    run.update(changes)
    return SnapshotFacts(run, 0, FINGERPRINT)


def provenance(raw: Path) -> dict[str, object]:
    return {
        "manifest_sha256": hashlib.sha256((raw / "manifest.jsonl").read_bytes()).hexdigest(),
        "corpus_configuration_sha256": "e" * 64,
    }


def fake_fingerprint(path: Path) -> Mapping[str, tuple[int, str]]:
    return FINGERPRINT if path.read_bytes() == b"warehouse" else {}


def test_a_warehouse_snapshot_round_trips_with_checksum_and_fingerprint(
    pushed: tuple[DirectoryStore, Path], tmp_path: Path
) -> None:
    store, raw = pushed
    warehouse = tmp_path / "regista.duckdb"
    warehouse.write_bytes(b"warehouse")

    push_warehouse(store, warehouse, facts(), provenance(raw))
    again = push_warehouse(store, warehouse, facts(), provenance(raw))
    assert again.notes == ["snapshot run1 already stored"]
    snapshot = json.loads(store.get_bytes("warehouse/run1/snapshot.json"))
    assert snapshot["manifest_sha256"] == provenance(raw)["manifest_sha256"]
    assert snapshot["fingerprint"]["normalized.events"] == [10, "abc"]

    output = tmp_path / "restored" / "regista.duckdb"
    run, _ = pull_warehouse(store, "latest", output, fake_fingerprint)
    assert (run, output.read_bytes()) == ("run1", b"warehouse")
    with pytest.raises(ValueError, match="pass --replace"):
        pull_warehouse(store, "run1", output, fake_fingerprint)
    assert verify(store, raw, deep=False) == []


def test_warehouse_snapshots_are_refused_when_unsafe_or_unreproducible(
    pushed: tuple[DirectoryStore, Path], tmp_path: Path
) -> None:
    store, raw = pushed
    warehouse = tmp_path / "regista.duckdb"
    warehouse.write_bytes(b"warehouse")

    with pytest.raises(ValueError, match="non-development"):
        push_warehouse(store, warehouse, SnapshotFacts({"ingest_run_id": "r"}, 1, {}), {})
    with pytest.raises(ValueError, match="uncommitted code"):
        push_warehouse(store, warehouse, facts(git_dirty=True), provenance(raw))
    with pytest.raises(ValueError, match="push the raw corpus"):
        push_warehouse(store, warehouse, facts(), {"manifest_sha256": "0" * 64})
    push_warehouse(store, warehouse, facts(git_dirty=True), provenance(raw), allow_dirty=True)
    changed = SnapshotFacts({"ingest_run_id": "run1"}, 0, {"normalized.events": (11, "x")})
    with pytest.raises(RemoteConflictError, match="different fingerprint"):
        push_warehouse(store, warehouse, changed, provenance(raw))


def test_a_restored_snapshot_that_fails_its_fingerprint_is_not_published(
    pushed: tuple[DirectoryStore, Path], tmp_path: Path
) -> None:
    store, raw = pushed
    warehouse = tmp_path / "regista.duckdb"
    warehouse.write_bytes(b"warehouse")
    push_warehouse(store, warehouse, facts(), provenance(raw))
    output = tmp_path / "restored.duckdb"

    with pytest.raises(ValueError, match="table fingerprint"):
        pull_warehouse(store, "run1", output, lambda path: {})
    assert not output.exists()
    assert not list(tmp_path.glob(".restored.duckdb.pulling"))


def test_a_real_synthetic_warehouse_snapshot_restores_with_an_equal_fingerprint(
    pushed: tuple[DirectoryStore, Path], tmp_path: Path
) -> None:
    store, raw = pushed
    built = build_warehouse(tmp_path / "build", [standard_match()]).path
    run, outside, table_fingerprint = snapshot_facts(built)
    assert (run["ingest_run_id"], outside) == ("synthetic-run", 0)

    push_warehouse(store, built, SnapshotFacts(run, outside, table_fingerprint), provenance(raw))
    output = tmp_path / "restored.duckdb"
    pull_warehouse(store, "latest", output, fingerprint)

    assert fingerprint(output) == fingerprint(built)
