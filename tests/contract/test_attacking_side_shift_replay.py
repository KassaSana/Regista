"""Replay the real match: golden snapshot and prefix invariance.

These read the locally downloaded match file and skip when it is missing. The
golden snapshot stores derived output only (sentences, counts, and evidence
event identifiers), never provider records. Regenerate it with
``REGISTA_UPDATE_GOLDEN=1 uv run pytest tests/contract``, then review the diff:
the snapshot is checked for correctness, never tuned toward a result.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from fractions import Fraction
from pathlib import Path
from typing import cast

import pytest

from regista.adapters.statsbomb.events import load_events
from regista.detectors.attacking_side_shift import AttackingSideShiftDetector, SideShiftSettings
from regista.domain.events import BallMovement, Event
from regista.domain.geometry import Point
from regista.domain.ids import MatchId
from regista.domain.insights import AttackingSideShift
from regista.domain.replay import replay
from regista.templates import render_attacking_side_shift

pytestmark = pytest.mark.contract

MATCH_ID = MatchId(3_773_497)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVENTS_PATH = REPOSITORY_ROOT / "data/statsbomb/data/events" / f"{MATCH_ID}.json"
GOLDEN_PATH = REPOSITORY_ROOT / "tests/golden" / f"{MATCH_ID}-attacking-side-shift.json"
# Prefix-invariance cut: the first event at or after minute 60 of the second half.
CUT_PERIOD, CUT_MINUTE = 2, 60
SET_PIECE_PASS_TYPES = {"Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"}
CHANNELS = ("left", "center", "right")


def _events() -> list[Event]:
    if not EVENTS_PATH.exists():
        pytest.skip(f"download StatsBomb match {MATCH_ID} to run the replay contract")
    return load_events(EVENTS_PATH, MATCH_ID)


def _cards(events: list[Event]) -> list[AttackingSideShift]:
    return list(replay(events, AttackingSideShiftDetector(SideShiftSettings())))


def _snapshot(cards: list[AttackingSideShift]) -> dict[str, object]:
    settings = asdict(SideShiftSettings())
    settings["minimum_share_increase"] = str(settings["minimum_share_increase"])
    return {
        "match_id": MATCH_ID,
        "detector": "attacking_side_shift",
        "settings": settings,
        "cards": [
            {
                "period": card.fired_at.period,
                "minute": card.fired_at.minute,
                "second": card.fired_at.second,
                "team": card.team.name,
                "channel": card.channel.value,
                "sentence": render_attacking_side_shift(card),
                "recent": asdict(card.recent),
                "baseline": asdict(card.baseline),
                "channels_losing_share": [channel.value for channel in card.channels_losing_share],
                "trigger_event_id": card.trigger_event_id,
                "recent_entry_ids": list(card.recent_entry_ids),
                "baseline_entry_ids": list(card.baseline_entry_ids),
                "sources": list(card.sources),
            }
            for card in cards
        ],
    }


def test_replay_matches_the_golden_snapshot() -> None:
    actual = _snapshot(_cards(_events()))

    if os.environ.get("REGISTA_UPDATE_GOLDEN") == "1":
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    assert actual == expected


def _mirrored(event: Event) -> Event:
    """Mirror an event across the pitch's long axis (y becomes 80 - y)."""

    def flip(point: Point) -> Point:
        return Point(x=point.x, y=80.0 - point.y)

    movement = event.movement
    if movement is not None:
        movement = BallMovement(
            start=flip(movement.start),
            end=flip(movement.end),
            completed=movement.completed,
            open_play=movement.open_play,
        )
    location = None if event.location is None else flip(event.location)
    return replace(event, location=location, movement=movement)


def test_cards_before_minute_60_ignore_everything_after_it() -> None:
    events = _events()
    cut = next(
        position
        for position, event in enumerate(events)
        if (event.clock.period, event.clock.minute) >= (CUT_PERIOD, CUT_MINUTE)
    )
    altered = events[:cut] + [_mirrored(event) for event in events[cut:]]
    early = {event.identifier for event in events[:cut]}

    original = [card for card in _cards(events) if card.trigger_event_id in early]
    after_alteration = [card for card in _cards(altered) if card.trigger_event_id in early]

    assert original
    assert after_alteration == original


def _independent_channel(record: dict[str, object]) -> str | None:
    """Return the entry channel of one raw record, or None when it is not an entry."""
    kind = cast(dict[str, str], record["type"])["name"]
    if kind == "Pass":
        details = cast(dict[str, object], record["pass"])
        pass_type = cast(dict[str, str], details.get("type", {})).get("name")
        if "outcome" in details or pass_type in SET_PIECE_PASS_TYPES:
            return None
    elif kind == "Carry":
        details = cast(dict[str, object], record["carry"])
    else:
        return None
    start_x = cast(list[float], record["location"])[0]
    end_x, end_y = cast(list[float], details["end_location"])
    if not start_x < 80 <= end_x:
        return None
    return "left" if end_y < 80 / 3 else "right" if end_y > 160 / 3 else "center"


def _independent_cards() -> list[tuple[object, ...]]:
    """Recompute the cards from the raw file with deliberately separate, plain code.

    This shares nothing with the adapter, domain, or detector: a mistake in one of
    them has to be repeated here by accident to go unnoticed.
    """
    with EVENTS_PATH.open(encoding="utf-8") as event_file:
        raw = cast(list[dict[str, object]], json.load(event_file))
    records = sorted(raw, key=lambda record: cast(int, record["index"]))
    period_starts: dict[int, int] = {}
    teams: list[str] = []
    entries: list[tuple[str, int, int, str]] = []
    cooldowns: dict[str, tuple[int, int]] = {}
    cards: list[tuple[object, ...]] = []
    for record in records:
        period = cast(int, record["period"])
        now = cast(int, record["minute"]) * 60 + cast(int, record["second"])
        team = cast(dict[str, str], record["team"])["name"]
        period_starts.setdefault(period, now)
        if team not in teams:
            teams.append(team)
        channel = _independent_channel(record)
        if channel is not None:
            entries.append((team, period, now, channel))
        if now - period_starts[period] < 600:
            continue
        for candidate in teams:
            cooldown = cooldowns.get(candidate)
            if cooldown is not None and cooldown[0] == period and now < cooldown[1]:
                continue
            own = [entry for entry in entries if entry[0] == candidate]
            recent = [e[3] for e in own if e[1] == period and e[2] > now - 600]
            baseline = [e[3] for e in own if not (e[1] == period and e[2] > now - 600)]
            if len(recent) < 8 or len(baseline) < 12:
                continue
            best: tuple[str, Fraction] | None = None
            for name in CHANNELS:
                increase = Fraction(recent.count(name), len(recent)) - Fraction(
                    baseline.count(name), len(baseline)
                )
                if increase >= Fraction(1, 4) and (best is None or increase > best[1]):
                    best = (name, increase)
            if best is not None:
                cards.append(
                    (
                        period,
                        record["minute"],
                        record["second"],
                        candidate,
                        best[0],
                        tuple(recent.count(name) for name in CHANNELS),
                        tuple(baseline.count(name) for name in CHANNELS),
                    )
                )
                cooldowns[candidate] = (period, now + 600)
    return cards


def test_cards_match_an_independent_recomputation() -> None:
    detected = [
        (
            card.fired_at.period,
            card.fired_at.minute,
            card.fired_at.second,
            card.team.name,
            card.channel.value,
            (card.recent.left, card.recent.center, card.recent.right),
            (card.baseline.left, card.baseline.center, card.baseline.right),
        )
        for card in _cards(_events())
    ]

    assert detected == _independent_cards()
