"""Synthetic source claims and kickoff-time eligibility."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from regista.domain.claims import SourceClaim
from regista.domain.ids import ClaimId
from regista.warehouse.claims import ClaimStore

KICKOFF = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)
MATCH_DATE = date(2026, 9, 28)
SUBJECT = "synthetic:player:42"


def claim(identifier: str, **changes: object) -> SourceClaim:
    base = SourceClaim(
        identifier=ClaimId(identifier),
        subject=SUBJECT,
        predicate="synthetic_fact",
        value="example",
        valid_from=date(2026, 9, 1),
        valid_until=date(2026, 10, 1),
        published_at=KICKOFF - timedelta(days=2),
        source_url="https://example.org/claim",
        retrieved_at=KICKOFF - timedelta(days=1),
        confidence=0.8,
        license_class="synthetic_test",
    )
    return replace(base, **changes)


def test_kickoff_snapshot_rejects_future_unknown_or_inapplicable_claims(tmp_path: Path) -> None:
    current = KICKOFF - timedelta(hours=1)
    store = ClaimStore(tmp_path / "claims.duckdb", clock=lambda: current)
    store.initialize()
    store.append(claim("eligible"))
    store.append(claim("unknown_publication", published_at=None))
    store.append(claim("starts_later", valid_from=MATCH_DATE + timedelta(days=1)))
    store.append(claim("ended_today", valid_until=MATCH_DATE))
    store.append(claim("other_subject", subject="synthetic:player:99"))
    current = KICKOFF
    store.append(claim("published_at_kickoff", published_at=KICKOFF, retrieved_at=KICKOFF))
    current = KICKOFF + timedelta(days=2)
    store.append(
        claim(
            "published_after",
            published_at=KICKOFF + timedelta(seconds=1),
            retrieved_at=KICKOFF + timedelta(days=1),
        )
    )
    store.append(claim("retrieved_after", retrieved_at=KICKOFF + timedelta(seconds=1)))

    snapshot = store.freeze_at_kickoff({SUBJECT}, KICKOFF, MATCH_DATE)

    assert [item.identifier for item in snapshot.claims] == [ClaimId("eligible")]
    assert snapshot.claims[0].source_url == "https://example.org/claim"
    assert snapshot.claims[0].license_class == "synthetic_test"
    assert snapshot.claims[0].retrieved_at == KICKOFF - timedelta(days=1)
    assert snapshot.claims[0].recorded_at == KICKOFF - timedelta(hours=1)
    assert snapshot.kickoff_utc == KICKOFF


def test_snapshot_remains_frozen_after_another_claim_is_appended(tmp_path: Path) -> None:
    current = KICKOFF - timedelta(hours=1)
    store = ClaimStore(tmp_path / "claims.duckdb", clock=lambda: current)
    store.append(claim("first"))
    frozen = store.freeze_at_kickoff([SUBJECT], KICKOFF, MATCH_DATE)
    current = KICKOFF + timedelta(hours=1)
    store.append(claim("second"))

    assert [item.identifier for item in frozen.claims] == [ClaimId("first")]
    refreshed = store.freeze_at_kickoff([SUBJECT], KICKOFF, MATCH_DATE)
    assert [item.identifier for item in refreshed.claims] == [ClaimId("first")]


def test_claims_are_append_only_and_subjects_are_parameters(tmp_path: Path) -> None:
    store = ClaimStore(tmp_path / "claims.duckdb", clock=lambda: KICKOFF - timedelta(hours=1))
    quoted_subject = "synthetic:player:'42'"
    store.append(claim("quoted", subject=quoted_subject))
    with pytest.raises(duckdb.ConstraintException):
        store.append(claim("quoted", value="changed"))
    frozen = store.freeze_at_kickoff([quoted_subject], KICKOFF, MATCH_DATE)
    assert [(item.identifier, item.value) for item in frozen.claims] == [
        (ClaimId("quoted"), "example")
    ]


def test_claim_validation_rejects_ambiguous_times_and_sources() -> None:
    with pytest.raises(ValueError, match="UTC-aware"):
        claim("naive", published_at=datetime(2026, 9, 27, 12, 0))
    with pytest.raises(ValueError, match="HTTPS"):
        claim("bad_source", source_url="http://example.org/claim")
    with pytest.raises(ValueError, match="nonempty"):
        claim("bad_dates", valid_from=date(2026, 10, 1))
    with pytest.raises(ValueError, match="zero and one"):
        claim("bad_confidence", confidence=float("nan"))


def test_recorded_time_cannot_be_supplied_or_precede_retrieval(tmp_path: Path) -> None:
    store = ClaimStore(tmp_path / "claims.duckdb", clock=lambda: KICKOFF - timedelta(days=2))
    with pytest.raises(ValueError, match="before retrieval"):
        store.append(claim("before_retrieval"))
    with pytest.raises(ValueError, match="set by the claim store"):
        store.append(claim("backdated", recorded_at=KICKOFF - timedelta(hours=1)))
