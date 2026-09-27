"""Requests and receipts for immutable source-file acquisition."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RawFileRequest:
    provider: str
    dataset: str
    source_commit: str
    relative_path: str
    url: str
    kind: str
    provider_match_id: int | None
    provider_last_updated: str | None
    license_class: str
    split_bucket: str | None
    split_sha256: str | None
    expected_sha256: str | None = None
    retrieved_at: str | None = None


@dataclass(frozen=True)
class AcquisitionResult:
    files: int
    downloaded: int
    verified: int
    restored: int
    registered: int
    byte_count: int
