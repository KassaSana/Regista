"""Pinned StatsBomb raw-file requests and bounded HTTP retries."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from regista.domain.acquisition import RawFileRequest
from regista.domain.catalog import CorpusConfiguration, IndexCatalog, MatchIndex

MAXIMUM_PAYLOAD_BYTES = 64 * 1024 * 1024
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _read_payload(url: str) -> bytes:
    request = Request(
        url, headers={"User-Agent": "Regista-research/0.1", "Accept-Encoding": "identity"}
    )
    with urlopen(request, timeout=30) as response:
        contents = response.read(MAXIMUM_PAYLOAD_BYTES + 1)
        expected_length = response.headers.get("Content-Length")
    if len(contents) > MAXIMUM_PAYLOAD_BYTES:
        raise ValueError("provider payload exceeds the 64 MiB per-file limit")
    if expected_length is not None and int(expected_length) != len(contents):
        raise IncompleteRead(contents)
    return contents


def fetch_payload(
    url: str,
    *,
    read: Callable[[str], bytes] = _read_payload,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Retry transient failures three times; fail permanent HTTP errors immediately."""
    for attempt in range(4):
        try:
            contents = read(url)
            if not isinstance(json.loads(contents), list):
                raise ValueError("StatsBomb raw files must contain a JSON list")
            return contents
        except HTTPError as error:
            if error.code not in RETRYABLE_STATUS_CODES or attempt == 3:
                raise
            retry_after = error.headers.get("Retry-After", "")
            delay = min(float(retry_after), 30.0) if retry_after.isdigit() else 2.0**attempt
        except (URLError, TimeoutError, ConnectionError, IncompleteRead):
            if attempt == 3:
                raise
            delay = 2.0**attempt
        sleep(delay)
    raise AssertionError("retry loop must return or raise")


def plan_files(
    configuration: CorpusConfiguration,
    catalog: IndexCatalog,
    matches: Sequence[MatchIndex],
    split_sha256: str,
) -> tuple[RawFileRequest, ...]:
    prefix = f"statsbomb-open-data/{configuration.source_commit}"
    requests = [
        RawFileRequest(
            "statsbomb",
            "open-data",
            configuration.source_commit,
            f"{prefix}/{source.relative_path}",
            source.url,
            "competitions" if source.relative_path == "data/competitions.json" else "matches",
            None,
            None,
            "statsbomb-public-data-agreement",
            None,
            None,
            source.sha256,
            source.retrieved_at,
        )
        for source in catalog.sources
    ]
    for match in matches:
        for kind in ("events", "lineups"):
            path = f"data/{kind}/{match.match_id}.json"
            requests.append(
                RawFileRequest(
                    "statsbomb",
                    "open-data",
                    configuration.source_commit,
                    f"{prefix}/{path}",
                    f"https://raw.githubusercontent.com/hudl/open-data/{configuration.source_commit}/{path}",
                    kind,
                    match.match_id,
                    match.provider_last_updated,
                    "statsbomb-public-data-agreement",
                    "development",
                    split_sha256,
                )
            )
    return tuple(requests)
