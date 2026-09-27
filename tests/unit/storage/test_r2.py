"""The R2 adapter, exercised offline with botocore's Stubber (no network, no credentials)."""

from __future__ import annotations

import io
from pathlib import Path

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from regista.storage.r2 import ENVIRONMENT_VARIABLES, MissingCredentialsError, R2Store

SECRET = "never-print-this-secret"
ENVIRONMENT = {
    "REGISTA_R2_ACCOUNT_ID": "account123",
    "REGISTA_R2_ACCESS_KEY_ID": "key-id",
    "REGISTA_R2_SECRET_ACCESS_KEY": SECRET,
    "REGISTA_R2_BUCKET": "regista-data",
}


def stubbed() -> tuple[R2Store, Stubber]:
    client = boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url="https://account123.r2.cloudflarestorage.com",
        aws_access_key_id="key-id",
        aws_secret_access_key=SECRET,
        region_name="auto",
    )
    return R2Store(client, "regista-data"), Stubber(client)


def test_missing_settings_name_the_variables_but_never_values() -> None:
    with pytest.raises(MissingCredentialsError) as caught:
        R2Store.from_environment({"REGISTA_R2_SECRET_ACCESS_KEY": SECRET})

    message = str(caught.value)
    for name in ENVIRONMENT_VARIABLES:
        if name != "REGISTA_R2_SECRET_ACCESS_KEY":
            assert name in message
    assert SECRET not in message


def test_the_client_targets_the_account_endpoint_without_network() -> None:
    store = R2Store.from_environment(ENVIRONMENT)

    assert store._client.meta.endpoint_url == "https://account123.r2.cloudflarestorage.com"  # pyright: ignore[reportPrivateUsage]
    assert store._client.meta.region_name == "auto"  # pyright: ignore[reportPrivateUsage]


def test_stat_returns_size_and_checksum_metadata_or_none_when_absent() -> None:
    store, stubber = stubbed()
    stubber.add_response(
        "head_object",
        {"ContentLength": 42, "Metadata": {"sha256": "a" * 64}},
        {"Bucket": "regista-data", "Key": "raw/x.json"},
    )
    stubber.add_client_error(
        "head_object",
        service_error_code="404",
        http_status_code=404,
        expected_params={"Bucket": "regista-data", "Key": "raw/missing.json"},
    )
    with stubber:
        present = store.stat("raw/x.json")
        absent = store.stat("raw/missing.json")

    assert present is not None
    assert (present.byte_count, present.sha256) == (42, "a" * 64)
    assert absent is None


def test_other_errors_are_not_mistaken_for_absence() -> None:
    store, stubber = stubbed()
    stubber.add_client_error("head_object", service_error_code="403", http_status_code=403)
    with stubber, pytest.raises(Exception, match="403"):
        store.stat("raw/x.json")


def test_put_get_and_list_use_the_bucket_and_checksum_metadata(tmp_path: Path) -> None:
    store, stubber = stubbed()
    stubber.add_response(
        "put_object",
        {},
        {
            "Bucket": "regista-data",
            "Key": "manifests/latest.json",
            "Body": b"{}",
            "Metadata": {"sha256": "b" * 64},
        },
    )
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(b"{}"), 2)},
        {"Bucket": "regista-data", "Key": "manifests/latest.json"},
    )
    stubber.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": "raw/a.json"}, {"Key": "raw/b.json"}], "IsTruncated": False},
        {"Bucket": "regista-data", "Prefix": "raw/"},
    )
    with stubber:
        store.put_bytes("manifests/latest.json", b"{}", "b" * 64)
        contents = store.get_bytes("manifests/latest.json")
        keys = list(store.keys("raw/"))

    assert contents == b"{}"
    assert keys == ["raw/a.json", "raw/b.json"]
    stubber.assert_no_pending_responses()
