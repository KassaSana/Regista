"""Provider-neutral, sourced claims eligible for a kickoff context snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isfinite
from urllib.parse import urlparse

from regista.domain.ids import ClaimId


def require_utc(value: datetime, description: str) -> None:
    """Reject timestamps whose ordering against a kickoff is ambiguous."""
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{description} must be a UTC-aware datetime")


@dataclass(frozen=True, slots=True)
class SourceClaim:
    """One immutable assertion, with a link to its original evidence."""

    identifier: ClaimId
    subject: str
    predicate: str
    value: str
    valid_from: date | None
    valid_until: date | None  # Exclusive.
    published_at: datetime | None
    source_url: str
    retrieved_at: datetime
    confidence: float
    license_class: str
    recorded_at: datetime | None = None  # Set by the claim store, never by a source adapter.

    def __post_init__(self) -> None:
        for label, value in (
            ("identifier", self.identifier),
            ("subject", self.subject),
            ("predicate", self.predicate),
            ("value", self.value),
            ("license_class", self.license_class),
        ):
            if not value.strip():
                raise ValueError(f"claim {label} must not be empty")
        source = urlparse(self.source_url)
        if source.scheme != "https" or not source.netloc:
            raise ValueError("claim source_url must be an HTTPS URL")
        if self.valid_from and self.valid_until and self.valid_from >= self.valid_until:
            raise ValueError("claim validity interval must be nonempty")
        if self.published_at is not None:
            require_utc(self.published_at, "published_at")
        require_utc(self.retrieved_at, "retrieved_at")
        if self.recorded_at is not None:
            require_utc(self.recorded_at, "recorded_at")
        if self.published_at is not None and self.published_at > self.retrieved_at:
            raise ValueError("claim cannot be retrieved before publication")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("claim confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class KickoffContext:
    """Claims frozen once for a match; no in-match refresh occurs."""

    kickoff_utc: datetime
    match_local_date: date
    claims: tuple[SourceClaim, ...]

    def __post_init__(self) -> None:
        require_utc(self.kickoff_utc, "kickoff_utc")
