"""Ingestion refuses held-out data and records missing files instead of dropping matches."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, time
from pathlib import Path

import pytest
from synthetic_warehouse import standard_match

from regista.domain.catalog import MatchIndex
from regista.domain.ids import MatchId
from regista.domain.matches import MatchRecord
from regista.domain.normalized import NormalizedMatch, QualityCheck
from regista.pipeline.ingest import ingest_matches, ingest_run_identifier, match_receipts


class RecordingWriter:
    def __init__(self) -> None:
        self.checks: list[QualityCheck] = []
        self.records: list[int] = []

    def add_raw_file(self, receipt: Mapping[str, object]) -> None:
        pass

    def add_match_record(self, match: MatchRecord, checksums: Mapping[str, str]) -> None:
        self.records.append(match.match_id)

    def add_match(self, normalized: NormalizedMatch, checksums: Mapping[str, str]) -> None:
        raise AssertionError("no match should normalize in these tests")

    def add_quality_check(self, check: QualityCheck) -> None:
        self.checks.append(check)


def _never(match: MatchRecord, events: bytes, lineups: bytes) -> NormalizedMatch:
    raise AssertionError("normalize must not run without verified files")


INDEX = MatchIndex(7, 2, 27, date(2015, 8, 8), time(15, 0), False, ())


def test_a_match_acquired_as_held_out_is_refused(tmp_path: Path) -> None:
    receipts: dict[tuple[str, int], Mapping[str, object]] = {
        ("events", 7): {"split_bucket": "validation", "relative_path": "x"}
    }
    record = standard_match(match_id=7).record()

    with pytest.raises(ValueError, match="not acquired as development"):
        ingest_matches([INDEX], {MatchId(7): record}, receipts, tmp_path, _never, RecordingWriter())


def test_a_missing_receipt_is_a_blocking_failure_not_a_silent_drop(tmp_path: Path) -> None:
    writer = RecordingWriter()
    record = standard_match(match_id=7).record()

    summary = ingest_matches([INDEX], {MatchId(7): record}, {}, tmp_path, _never, writer)

    assert summary.excluded == {
        MatchId(7): ["no manifest receipt for events", "no manifest receipt for lineups"]
    }
    assert [(check.check, check.passed) for check in writer.checks] == [("raw_checksum", False)]
    assert writer.records == [7]


def test_receipts_are_indexed_by_kind_and_match_for_one_source_commit() -> None:
    manifest = {
        "a": {"source_commit": "x", "kind": "events", "provider_match_id": 1},
        "b": {"source_commit": "y", "kind": "events", "provider_match_id": 1},
        "c": {"source_commit": "x", "kind": "matches", "provider_match_id": None},
    }

    assert match_receipts(manifest, "x") == {("events", 1): manifest["a"]}


def test_run_identifiers_depend_only_on_inputs() -> None:
    first = ingest_run_identifier({"source": "x", "files": [("events", 1, "abc")]})

    assert first == ingest_run_identifier({"files": [("events", 1, "abc")], "source": "x"})
    assert first != ingest_run_identifier({"source": "x", "files": [("events", 1, "abd")]})
