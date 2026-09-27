from datetime import date, time
from email.message import Message
from urllib.error import HTTPError

import pytest

from regista.adapters.statsbomb.download import fetch_payload, plan_files
from regista.domain.catalog import (
    CompetitionSeason,
    CorpusConfiguration,
    IndexCatalog,
    IndexSource,
    MatchIndex,
)


def _http_error(code: int, retry_after: str = "") -> HTTPError:
    headers = Message()
    if retry_after:
        headers["Retry-After"] = retry_after
    return HTTPError("https://example.invalid/data", code, "failure", headers, None)


def test_transient_http_error_retries_with_bounded_retry_after() -> None:
    failures = iter([_http_error(503, "99")])
    sleeps: list[float] = []

    def read(_: str) -> bytes:
        try:
            raise next(failures)
        except StopIteration:
            return b"[]"

    assert fetch_payload("https://example.invalid/data", read=read, sleep=sleeps.append) == b"[]"
    assert sleeps == [30.0]


def test_permanent_404_fails_without_retry() -> None:
    sleeps: list[float] = []
    with pytest.raises(HTTPError) as error:
        fetch_payload(
            "https://example.invalid/data",
            read=lambda _: (_ for _ in ()).throw(_http_error(404)),
            sleep=sleeps.append,
        )
    assert error.value.code == 404
    assert sleeps == []


def test_payload_must_be_a_json_list() -> None:
    with pytest.raises(ValueError, match="JSON list"):
        fetch_payload(
            "https://example.invalid/data",
            read=lambda _: b'{"events": []}',
            sleep=lambda _: None,
        )


def test_plan_includes_indexes_events_and_lineups_only() -> None:
    configuration = CorpusConfiguration(
        "statsbomb",
        "open-data",
        "a" * 40,
        (CompetitionSeason(1, 2, "modern_robustness", "complete_season", 1),),
        (),
        7,
        "b" * 64,
    )
    match = MatchIndex(123, 1, 2, date(2020, 1, 1), time(12), True, (), "2020-01-02")
    source = IndexSource(
        "data/competitions.json",
        "https://example.invalid/index",
        "c" * 64,
        5,
        "retrieved",
    )
    requests = plan_files(configuration, IndexCatalog((match,), (source,)), (match,), "d" * 64)
    assert [request.kind for request in requests] == ["competitions", "events", "lineups"]
    assert all("three-sixty" not in request.relative_path for request in requests)
    assert requests[1].split_bucket == "development"


def test_transient_failure_stops_after_four_attempts() -> None:
    attempts: list[str] = []
    delays: list[float] = []

    def read(url: str) -> bytes:
        attempts.append(url)
        raise _http_error(503)

    with pytest.raises(HTTPError):
        fetch_payload("https://example.invalid/data", read=read, sleep=delays.append)
    assert len(attempts) == 4
    assert delays == [1.0, 2.0, 4.0]
