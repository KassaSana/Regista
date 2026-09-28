"""The product assembly: one ordered card stream and a thin, schema-valid replay export."""

from __future__ import annotations

import json
import re
from datetime import date, time
from typing import cast

import pytest
from jsonschema import ValidationError
from replay_schema import validate_export
from synthetic_events import (
    AWAY,
    HOME,
    MATCH,
    EventStream,
    add_balanced_baseline,
    add_recent,
)

from regista.domain.entries import Channel
from regista.domain.events import Event
from regista.domain.matches import MatchRecord, TeamRecord
from regista.product import build_card_stream, build_match_export

LEFT, CENTER, RIGHT = Channel.LEFT, Channel.CENTER, Channel.RIGHT
LEFT_SHIFT = [LEFT, LEFT, CENTER, LEFT, LEFT, RIGHT, LEFT, LEFT]
RECORD = MatchRecord(
    provider="synthetic",
    match_id=MATCH,
    competition_id=1,
    season_id=2,
    competition_name="Synthetic League",
    season_name="2026",
    match_date=date(2026, 9, 28),
    kickoff=time(15, 0),
    home_team=TeamRecord(HOME.identifier, HOME.name),
    away_team=TeamRecord(AWAY.identifier, AWAY.name),
    # Hindsight: deliberately wrong, so any export that read it would fail.
    home_score=9,
    away_score=9,
    match_week=None,
    stage=None,
    stadium=None,
    data_version=None,
    xy_fidelity_version=None,
    shot_fidelity_version=None,
    provider_last_updated=None,
    has_three_sixty=False,
    provider_record={},
)

type Json = dict[str, object]


def _match() -> tuple[EventStream, dict[str, Event]]:
    """Home scores, then shifts left (card at 18:00); Away bursts (card at 27:00), then scores."""
    stream = EventStream()
    named: dict[str, Event] = {}
    stream.period_boundary(HOME, 1, 0)
    add_balanced_baseline(stream)
    named["home_goal"] = stream.shot(HOME, 1, 9, scored=True)
    add_recent(stream, LEFT_SHIFT)
    for minute in (21, 23, 25, 27):
        named[f"away_shot_{minute}"] = stream.shot(AWAY, 1, minute)
    named["own_goal"] = stream.own_goal_for(AWAY, 1, 30)
    stream.period_boundary(HOME, 1, 45, end=True)
    return stream, named


def _list(value: object) -> list[Json]:
    return cast(list[Json], value)


def test_the_export_follows_the_schema() -> None:
    stream, _ = _match()

    validate_export(build_match_export(stream.events, RECORD))


def test_cards_are_in_replay_order_and_only_the_burst_is_experimental() -> None:
    stream, _ = _match()

    cards = _list(build_match_export(stream.events, RECORD)["cards"])

    assert [(card["kind"], card["experimental"]) for card in cards] == [
        ("side_shift", False),
        ("burst", True),
    ]
    assert [card["clock"] for card in cards] == [
        {"period": 1, "minute": 18, "second": 0},
        {"period": 1, "minute": 27, "second": 0},
    ]
    assert [card["id"] for card in cards] == [
        f"{kind}-{card.trigger_event_id}"
        for kind, card in zip(
            ("side_shift", "burst"), build_card_stream(stream.events), strict=True
        )
    ]


def test_each_card_carries_the_score_when_it_fired_never_a_later_one() -> None:
    stream, _ = _match()

    export = build_match_export(stream.events, RECORD)

    # The own goal at 30:00 comes after both cards and must not leak into them.
    assert [card["score"] for card in _list(export["cards"])] == [
        {"home": 1, "away": 0},
        {"home": 1, "away": 0},
    ]
    goals = _list(export["goals"])
    assert [(goal["own_goal"], goal["score"]) for goal in goals] == [
        (False, {"home": 1, "away": 0}),
        (True, {"home": 1, "away": 1}),
    ]


def test_evidence_is_exactly_each_cards_recent_events() -> None:
    stream, named = _match()
    side_shift, burst = build_card_stream(stream.events)

    side_card, burst_card = _list(build_match_export(stream.events, RECORD)["cards"])

    assert [item["event_id"] for item in _list(side_card["evidence"])] == list(
        side_shift.recent_entry_ids
    )
    assert {item["role"] for item in _list(side_card["evidence"])} == {"recent"}
    assert [item["event_id"] for item in _list(burst_card["evidence"])] == [
        named[f"away_shot_{minute}"].identifier for minute in (21, 23, 25, 27)
    ]
    assert list(burst.recent_entry_ids) == []


def test_the_export_is_thin_it_names_no_event_beyond_goals_evidence_and_facts() -> None:
    stream, _ = _match()
    export = build_match_export(stream.events, RECORD)
    cards = _list(export["cards"])
    baseline = stream.events[1:13]

    allowed = {goal["event_id"] for goal in _list(export["goals"])}
    allowed |= {fact["event_id"] for fact in _list(export["facts"])}
    for card in cards:
        allowed.add(card["trigger_event_id"])
        allowed |= {item["event_id"] for item in _list(card["evidence"])}
    # Every whole event identifier anywhere in the export, including evidence text.
    named = set(re.findall(r"event-\d+", json.dumps(export)))

    assert named <= allowed
    # Baseline entries feed the counts but are never exported as evidence.
    assert not named & {event.identifier for event in baseline}


def test_periods_come_from_recorded_boundaries() -> None:
    stream, _ = _match()

    assert build_match_export(stream.events, RECORD)["periods"] == [
        {
            "period": 1,
            "start": {"period": 1, "minute": 0, "second": 0},
            "end": {"period": 1, "minute": 45, "second": 0},
        }
    ]


def test_a_quiet_match_has_no_cards_but_keeps_its_goals() -> None:
    stream = EventStream()
    stream.period_boundary(HOME, 1, 0)
    stream.shot(AWAY, 1, 40, penalty=True, scored=True)
    stream.period_boundary(HOME, 1, 45, end=True)

    export = build_match_export(stream.events, RECORD)

    validate_export(export)
    assert export["cards"] == []
    assert [(goal["penalty"], goal["score"]) for goal in _list(export["goals"])] == [
        (True, {"home": 0, "away": 1})
    ]


def test_the_schema_rejects_an_export_that_breaks_the_contract() -> None:
    stream, _ = _match()
    export = build_match_export(stream.events, RECORD)
    first_card = _list(export["cards"])[0]
    first_card["raw_events"] = []

    with pytest.raises(ValidationError):
        validate_export(export)
