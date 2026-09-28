"""Fetch head-coach tenure candidates from Wikidata's SPARQL service."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://query.wikidata.org/sparql"
MAX_RESPONSE_BYTES = 2_000_000
ENTITY = re.compile(r"Q[1-9][0-9]*\Z")
ENTITY_URI = re.compile(r"https?://www\.wikidata\.org/entity/(Q[1-9][0-9]*)\Z")


class WikidataFormatError(ValueError):
    """Raised when the query service returns an unexpected result shape."""


@dataclass(frozen=True, slots=True)
class CoachTenureCandidate:
    """Unreviewed Wikidata statement, not an admitted source claim."""

    team_entity: str
    coach_entity: str
    coach_label: str
    statement_url: str
    start_value: str | None
    start_precision: int | None
    end_value: str | None
    end_precision: int | None
    reference_url: str | None
    retrieved_at: datetime


def coach_tenures_query(team_entity: str) -> str:
    """Build a bounded query for one validated Wikidata item identifier."""
    if not ENTITY.fullmatch(team_entity):
        raise ValueError("team_entity must be a Wikidata Q identifier")
    return f"""
SELECT ?statement ?coach ?coachLabel ?start ?startPrecision
       ?end ?endPrecision ?referenceUrl WHERE {{
  wd:{team_entity} p:P286 ?statement .
  ?statement ps:P286 ?coach .
  OPTIONAL {{
    ?statement pqv:P580 ?startNode .
    ?startNode wikibase:timeValue ?start ;
               wikibase:timePrecision ?startPrecision .
  }}
  OPTIONAL {{
    ?statement pqv:P582 ?endNode .
    ?endNode wikibase:timeValue ?end ;
             wikibase:timePrecision ?endPrecision .
  }}
  OPTIONAL {{ ?statement prov:wasDerivedFrom/pr:P854 ?referenceUrl . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}} LIMIT 100
""".strip()


def _text(row: Mapping[str, object], name: str, *, required: bool = False) -> str | None:
    binding = row.get(name)
    if binding is None:
        if required:
            raise WikidataFormatError(f"missing {name} binding")
        return None
    if not isinstance(binding, Mapping):
        raise WikidataFormatError(f"invalid {name} binding")
    value = cast(Mapping[str, object], binding).get("value")
    if not isinstance(value, str):
        raise WikidataFormatError(f"invalid {name} value")
    return value


def _precision(row: Mapping[str, object], name: str) -> int | None:
    value = _text(row, name)
    if value is None:
        return None
    if not value.isdecimal():
        raise WikidataFormatError(f"invalid {name} value")
    return int(value)


def parse_coach_tenures(
    payload: object, team_entity: str, retrieved_at: datetime
) -> list[CoachTenureCandidate]:
    """Keep date precision and references visible; do not infer exact dates."""
    if not isinstance(payload, Mapping):
        raise WikidataFormatError("SPARQL response must be an object")
    results = cast(Mapping[str, object], payload).get("results")
    if not isinstance(results, Mapping):
        raise WikidataFormatError("SPARQL response needs results")
    bindings = cast(Mapping[str, object], results).get("bindings")
    if not isinstance(bindings, list):
        raise WikidataFormatError("SPARQL response needs bindings")
    candidates: list[CoachTenureCandidate] = []
    for item in cast(list[object], bindings):
        if not isinstance(item, Mapping):
            raise WikidataFormatError("SPARQL binding must be an object")
        row = cast(Mapping[str, object], item)
        coach_url = _text(row, "coach", required=True)
        assert coach_url is not None
        coach_match = ENTITY_URI.fullmatch(coach_url)
        if coach_match is None:
            raise WikidataFormatError("coach binding is not a Wikidata item")
        statement = _text(row, "statement", required=True)
        assert statement is not None
        if not statement.startswith(
            (
                "http://www.wikidata.org/entity/statement/",
                "https://www.wikidata.org/entity/statement/",
            )
        ):
            raise WikidataFormatError("statement binding is not a Wikidata statement")
        start = _text(row, "start")
        end = _text(row, "end")
        start_precision = _precision(row, "startPrecision")
        end_precision = _precision(row, "endPrecision")
        if (start is None) != (start_precision is None) or (end is None) != (end_precision is None):
            raise WikidataFormatError("tenure date lacks its precision")
        candidates.append(
            CoachTenureCandidate(
                team_entity=team_entity,
                coach_entity=coach_match.group(1),
                coach_label=_text(row, "coachLabel") or coach_match.group(1),
                statement_url=statement,
                start_value=start,
                start_precision=start_precision,
                end_value=end,
                end_precision=end_precision,
                reference_url=_text(row, "referenceUrl"),
                retrieved_at=retrieved_at,
            )
        )
    return candidates


def fetch_coach_tenures(team_entity: str, *, user_agent: str) -> list[CoachTenureCandidate]:
    """Make one read-only request; the caller supplies an identifiable agent."""
    if not user_agent.strip():
        raise ValueError("a descriptive Wikidata user_agent is required")
    query = coach_tenures_query(team_entity)
    request = Request(
        f"{ENDPOINT}?{urlencode({'query': query})}",
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": user_agent,
        },
    )
    with urlopen(request, timeout=20) as response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise WikidataFormatError("SPARQL response exceeded the size limit")
    return parse_coach_tenures(json.loads(content), team_entity, datetime.now(UTC))
