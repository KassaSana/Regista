"""Pin the provider fields used by the recorded-fact replay stream."""

from __future__ import annotations

import pytest

from regista.adapters.statsbomb.events import StatsBombFormatError, normalize_event
from regista.domain.events import FormationDetail, SubstitutionDetail
from regista.domain.ids import MatchId, PlayerId


def record(type_name: str, **details: object) -> dict[str, object]:
    event: dict[str, object] = {
        "id": "synthetic-event",
        "index": 1,
        "period": 1,
        "minute": 0,
        "second": 0,
        "type": {"id": 0, "name": type_name},
        "team": {"id": 1, "name": "Home"},
    }
    event.update(details)
    return event


def lineup() -> list[dict[str, object]]:
    return [{"player": {"id": number, "name": f"Player {number}"}} for number in range(1, 12)]


def test_starting_lineup_preserves_formation_and_eleven_player_names() -> None:
    event = normalize_event(
        record("Starting XI", tactics={"formation": 4231, "lineup": lineup()}), MatchId(1)
    )

    assert isinstance(event.match_fact, FormationDetail)
    assert event.match_fact.starting
    assert event.match_fact.formation == "4231"
    assert len(event.match_fact.starting_players) == 11
    assert event.match_fact.starting_players[0].identifier == PlayerId(1)


def test_tactical_shift_needs_only_the_recorded_formation() -> None:
    event = normalize_event(record("Tactical Shift", tactics={"formation": 442}), MatchId(1))

    assert event.match_fact == FormationDetail("442", False)


def test_substitution_uses_names_from_the_same_event() -> None:
    event = normalize_event(
        record(
            "Substitution",
            player={"id": 1, "name": "Departing"},
            substitution={"replacement": {"id": 12, "name": "Entering"}},
        ),
        MatchId(1),
    )

    assert isinstance(event.match_fact, SubstitutionDetail)
    assert event.match_fact.departing.name == "Departing"
    assert event.match_fact.entering.name == "Entering"


@pytest.mark.parametrize(
    "details",
    [
        {"formation": 433, "lineup": lineup()[:-1]},
        {"formation": 433, "lineup": [lineup()[0]] * 11},
    ],
)
def test_invalid_starting_lineups_fail_at_the_adapter(details: dict[str, object]) -> None:
    with pytest.raises(StatsBombFormatError, match="starting lineup"):
        normalize_event(record("Starting XI", tactics=details), MatchId(1))
