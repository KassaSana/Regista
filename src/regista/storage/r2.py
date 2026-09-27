"""Cloudflare R2 through its S3-compatible API. The only module that imports boto3.

Credentials come only from environment variables (for example through
``uv run --env-file .env``); they are never read from files in the repository,
printed, or logged. The store has no delete operation.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from regista.pipeline.remote import RemoteObject

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
else:
    S3Client = Any

ENVIRONMENT_VARIABLES = (
    "REGISTA_R2_ACCOUNT_ID",
    "REGISTA_R2_ACCESS_KEY_ID",
    "REGISTA_R2_SECRET_ACCESS_KEY",
    "REGISTA_R2_BUCKET",
)
SHA256_METADATA = "sha256"


class MissingCredentialsError(ValueError):
    """Raised when R2 environment variables are absent. Names only; never values."""


class R2Store:
    """A private R2 bucket addressed by object key."""

    def __init__(self, client: S3Client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> R2Store:
        values = os.environ if environment is None else environment
        missing = [name for name in ENVIRONMENT_VARIABLES if not values.get(name, "").strip()]
        if missing:
            raise MissingCredentialsError(
                "missing R2 settings: " + ", ".join(missing) + ". Copy .env.example to .env, "
                "fill it in, and run with `uv run --env-file .env ...`."
            )
        client: S3Client = boto3.client(  # pyright: ignore[reportUnknownMemberType]
            "s3",
            endpoint_url=f"https://{values['REGISTA_R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=values["REGISTA_R2_ACCESS_KEY_ID"],
            aws_secret_access_key=values["REGISTA_R2_SECRET_ACCESS_KEY"],
            region_name="auto",
            config=Config(
                retries={"max_attempts": 5, "mode": "standard"},
                # Send and validate the optional S3 checksum headers only where the API
                # requires them; Regista verifies SHA-256 itself on every transfer.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        return cls(client, values["REGISTA_R2_BUCKET"])

    def stat(self, key: str) -> RemoteObject | None:
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return RemoteObject(
            key=key,
            byte_count=head["ContentLength"],
            sha256=head.get("Metadata", {}).get(SHA256_METADATA),
        )

    def upload(self, path: Path, key: str, sha256: str) -> None:
        self._client.upload_file(
            str(path), self._bucket, key, ExtraArgs={"Metadata": {SHA256_METADATA: sha256}}
        )

    def download(self, key: str, path: Path) -> None:
        self._client.download_file(self._bucket, key, str(path))

    def put_bytes(self, key: str, contents: bytes, sha256: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=contents, Metadata={SHA256_METADATA: sha256}
        )

    def get_bytes(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def keys(self, prefix: str) -> Iterator[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item.get("Key")
                if key is not None:
                    yield key
