"""Validate selected development matches and hand normalized rows to a warehouse.

Provider-neutral orchestration: the adapter (``normalize``) and the warehouse
(``WarehouseWriter``) are injected by the composition root. Each raw file is
checked against its manifest receipt on the exact bytes that are parsed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from regista.domain.catalog import MatchIndex
from regista.domain.ids import MatchId
from regista.domain.matches import MatchRecord
from regista.domain.normalized import NormalizedMatch, QualityCheck

Normalize = Callable[[MatchRecord, bytes, bytes], NormalizedMatch]
MATCH_FILE_KINDS = ("events", "lineups")


class WarehouseWriter(Protocol):
    """The port through which ingestion stores what it validated."""

    def add_raw_file(self, receipt: Mapping[str, object]) -> None: ...

    def add_match_record(self, match: MatchRecord, checksums: Mapping[str, str]) -> None: ...

    def add_match(self, normalized: NormalizedMatch, checksums: Mapping[str, str]) -> None: ...

    def add_quality_check(self, check: QualityCheck) -> None: ...


@dataclass(frozen=True)
class IngestSummary:
    selected: int
    normalized: int
    excluded: dict[MatchId, list[str]]


def ingest_run_identifier(parts: Mapping[str, object]) -> str:
    """Name a run by everything that determines its rows, so identical inputs share an ID."""
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def match_receipts(
    manifest: Mapping[str, Mapping[str, object]], source_commit: str
) -> dict[tuple[str, int], Mapping[str, object]]:
    """Index match-level receipts from one source commit by kind and match identifier."""
    receipts: dict[tuple[str, int], Mapping[str, object]] = {}
    for receipt in manifest.values():
        kind, match_id = receipt.get("kind"), receipt.get("provider_match_id")
        if (
            receipt.get("source_commit") == source_commit
            and isinstance(kind, str)
            and kind in MATCH_FILE_KINDS
            and isinstance(match_id, int)
        ):
            receipts[(kind, match_id)] = receipt
    return receipts


def ingest_matches(
    matches: Sequence[MatchIndex],
    match_records: Mapping[MatchId, MatchRecord],
    receipts: Mapping[tuple[str, int], Mapping[str, object]],
    raw_directory: Path,
    normalize: Normalize,
    writer: WarehouseWriter,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> IngestSummary:
    """Validate every selected match; a failing match is recorded and excluded, never dropped."""
    excluded: dict[MatchId, list[str]] = {}
    normalized_count = 0
    for number, index in enumerate(matches, 1):
        match_id = MatchId(index.match_id)
        match = match_records[match_id]
        payloads: dict[str, bytes] = {}
        checksums: dict[str, str] = {}
        problems: list[str] = []
        for kind in MATCH_FILE_KINDS:
            receipt = receipts.get((kind, match_id))
            if receipt is None:
                problems.append(f"no manifest receipt for {kind}")
                continue
            if receipt.get("split_bucket") != "development":
                raise ValueError(f"match {match_id} was not acquired as development data")
            writer.add_raw_file(receipt)
            contents = (raw_directory / str(receipt.get("relative_path"))).read_bytes()
            checksum = hashlib.sha256(contents).hexdigest()
            if checksum != receipt.get("sha256") or len(contents) != receipt.get("bytes"):
                problems.append(f"{kind} checksum differs from the manifest")
                continue
            payloads[kind] = contents
            checksums[kind] = checksum
        writer.add_quality_check(
            QualityCheck(match_id, "raw_checksum", "blocking", not problems, "; ".join(problems))
        )
        normalized: NormalizedMatch | None = None
        if not problems:
            try:
                normalized = normalize(match, payloads["events"], payloads["lineups"])
            except ValueError as error:  # includes provider-format and JSON errors
                problems.append(f"adapter_validation: {error}")
            writer.add_quality_check(
                QualityCheck(
                    match_id,
                    "adapter_validation",
                    "blocking",
                    normalized is not None,
                    "" if normalized is not None else problems[-1],
                )
            )
        if normalized is None:
            writer.add_match_record(match, checksums)
            excluded[match_id] = problems
        else:
            writer.add_match(normalized, checksums)
            normalized_count += 1
        if progress is not None:
            progress(number, len(matches))
    return IngestSummary(len(matches), normalized_count, excluded)
