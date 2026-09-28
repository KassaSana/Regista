"""Append-only DuckDB store for sourced context, separate from provider data."""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import duckdb

from regista.domain.claims import KickoffContext, SourceClaim, require_utc
from regista.domain.ids import ClaimId

DEFAULT_CLAIMS_DATABASE = Path("data/context/claims.duckdb")
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS source_claims (
    claim_id VARCHAR PRIMARY KEY,
    subject VARCHAR NOT NULL,
    predicate VARCHAR NOT NULL,
    value VARCHAR NOT NULL,
    valid_from DATE,
    valid_until DATE,
    published_at TIMESTAMPTZ,
    source_url VARCHAR NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    confidence DOUBLE NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    license_class VARCHAR NOT NULL
)
"""


class ClaimStore:
    """Store immutable claims and freeze only claims known by kickoff."""

    def __init__(
        self,
        path: Path = DEFAULT_CLAIMS_DATABASE,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = path
        self._clock = clock or (lambda: datetime.now(UTC))

    def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self._path)) as connection:
            connection.execute(CREATE_TABLE)

    def append(self, claim: SourceClaim) -> None:
        """Insert once; a duplicate identifier fails instead of revising history."""
        if claim.recorded_at is not None:
            raise ValueError("recorded_at is set by the claim store")
        recorded_at = self._clock()
        require_utc(recorded_at, "recorded_at")
        if recorded_at < claim.retrieved_at:
            raise ValueError("claim cannot be recorded before retrieval")
        if not self._path.exists():
            self.initialize()
        with duckdb.connect(str(self._path)) as connection:
            connection.execute(
                """
                INSERT INTO source_claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    claim.identifier,
                    claim.subject,
                    claim.predicate,
                    claim.value,
                    claim.valid_from,
                    claim.valid_until,
                    claim.published_at,
                    claim.source_url,
                    claim.retrieved_at,
                    recorded_at,
                    claim.confidence,
                    claim.license_class,
                ],
            )

    def freeze_at_kickoff(
        self,
        subjects: Collection[str],
        kickoff_utc: datetime,
        match_local_date: date,
    ) -> KickoffContext:
        """Use only assertions published and retrieved before kickoff.

        The local match date is supplied explicitly: match metadata does not
        contain enough timezone information to derive it from the UTC instant.
        """
        require_utc(kickoff_utc, "kickoff_utc")
        if not self._path.exists():
            raise FileNotFoundError(self._path)
        selected = tuple(sorted(set(subjects)))
        if not selected:
            return KickoffContext(kickoff_utc, match_local_date, ())
        placeholders = ", ".join("?" for _ in selected)
        query = f"""
            SELECT claim_id, subject, predicate, value, valid_from, valid_until,
                epoch_us(published_at), source_url, epoch_us(retrieved_at),
                confidence, license_class, epoch_us(recorded_at)
            FROM source_claims
            WHERE subject IN ({placeholders})
                AND published_at IS NOT NULL AND published_at < ?
                AND retrieved_at <= ?
                AND recorded_at <= ?
                AND (valid_from IS NULL OR valid_from <= ?)
                AND (valid_until IS NULL OR valid_until > ?)
            ORDER BY subject, predicate, valid_from, claim_id
        """
        with duckdb.connect(str(self._path), read_only=True) as connection:
            rows = connection.execute(
                query,
                [
                    *selected,
                    kickoff_utc,
                    kickoff_utc,
                    kickoff_utc,
                    match_local_date,
                    match_local_date,
                ],
            ).fetchall()
        claims = tuple(
            SourceClaim(
                identifier=ClaimId(str(row[0])),
                subject=str(row[1]),
                predicate=str(row[2]),
                value=str(row[3]),
                valid_from=cast(date | None, row[4]),
                valid_until=cast(date | None, row[5]),
                published_at=EPOCH + timedelta(microseconds=int(row[6])),
                source_url=str(row[7]),
                retrieved_at=EPOCH + timedelta(microseconds=int(row[8])),
                confidence=float(row[9]),
                license_class=str(row[10]),
                recorded_at=EPOCH + timedelta(microseconds=int(row[11])),
            )
            for row in rows
        )
        return KickoffContext(kickoff_utc, match_local_date, claims)
