"""Synthetic Wikidata coach-tenure candidates, never admitted source claims."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from typing import cast
from unittest.mock import patch
from urllib.request import Request

import pytest

from regista.adapters.wikidata.coaches import (
    WikidataFormatError,
    coach_tenures_query,
    fetch_coach_tenures,
    parse_coach_tenures,
)

RETRIEVED = datetime(2026, 9, 28, tzinfo=UTC)


def binding(value: str) -> dict[str, str]:
    return {"type": "literal", "value": value}


def payload() -> dict[str, object]:
    return {
        "results": {
            "bindings": [
                {
                    "statement": binding("http://www.wikidata.org/entity/statement/Q123-synthetic"),
                    "coach": binding("http://www.wikidata.org/entity/Q456"),
                    "coachLabel": binding("Example Coach"),
                    "start": binding("2020-01-01T00:00:00Z"),
                    "startPrecision": binding("9"),
                    "end": binding("2023-08-12T00:00:00Z"),
                    "endPrecision": binding("11"),
                    "referenceUrl": binding("https://example.org/source"),
                }
            ]
        }
    }


def test_query_is_bounded_and_rejects_entity_injection() -> None:
    query = coach_tenures_query("Q123")
    assert "wd:Q123 p:P286" in query
    assert "pqv:P580" in query and "pqv:P582" in query
    assert "prov:wasDerivedFrom/pr:P854" in query
    assert "LIMIT 100" in query
    with pytest.raises(ValueError, match="Q identifier"):
        coach_tenures_query("Q123 } UNION { ?x ?y ?z")


def test_parser_preserves_precision_reference_and_retrieval() -> None:
    candidates = parse_coach_tenures(payload(), "Q123", RETRIEVED)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert (candidate.team_entity, candidate.coach_entity, candidate.coach_label) == (
        "Q123",
        "Q456",
        "Example Coach",
    )
    assert (candidate.start_value, candidate.start_precision) == ("2020-01-01T00:00:00Z", 9)
    assert (candidate.end_value, candidate.end_precision) == ("2023-08-12T00:00:00Z", 11)
    assert candidate.reference_url == "https://example.org/source"
    assert candidate.retrieved_at == RETRIEVED


def test_missing_reference_and_tenure_dates_remain_unknown() -> None:
    altered = payload()
    results = cast(dict[str, object], altered["results"])
    record = cast(list[dict[str, object]], results["bindings"])[0]
    for field in ("referenceUrl", "start", "startPrecision", "end", "endPrecision"):
        record.pop(field)
    candidate = parse_coach_tenures(altered, "Q123", RETRIEVED)[0]
    assert candidate.reference_url is None
    assert candidate.start_value is None and candidate.start_precision is None
    assert candidate.end_value is None and candidate.end_precision is None


def test_parser_rejects_a_date_without_precision() -> None:
    altered = payload()
    results = cast(dict[str, object], altered["results"])
    record = cast(list[dict[str, object]], results["bindings"])[0]
    record.pop("startPrecision")
    with pytest.raises(WikidataFormatError, match="lacks its precision"):
        parse_coach_tenures(altered, "Q123", RETRIEVED)


def test_fetch_requires_user_agent_and_requests_json() -> None:
    with pytest.raises(ValueError, match="user_agent"):
        fetch_coach_tenures("Q123", user_agent=" ")
    body = json.dumps(payload()).encode()
    with patch("regista.adapters.wikidata.coaches.urlopen", return_value=BytesIO(body)) as opened:
        candidates = fetch_coach_tenures("Q123", user_agent="Regista research contact@example.org")
    assert len(candidates) == 1
    request = cast(Request, opened.call_args.args[0])
    assert "query=" in request.full_url
    assert request.get_header("Accept") == "application/sparql-results+json"
    assert request.get_header("User-agent") == "Regista research contact@example.org"
