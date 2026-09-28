"""Replay the real match for the attacking burst: golden snapshot, prefix, recomputation.

These read the locally downloaded match file and skip when it is missing. The
golden snapshot stores derived output only. Regenerate it with
``REGISTA_UPDATE_GOLDEN=1 uv run pytest tests/contract``, then review the diff.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from fractions import Fraction
from pathlib import Path
from typing import cast

import pytest
from pinned_events import pinned_events_path

from regista.adapters.statsbomb.events import load_events
from regista.detectors.attacking_burst import AttackingBurstDetector, BurstSettings
from regista.domain.events import Event
from regista.domain.ids import MatchId
from regista.domain.insights import AttackingBurst
from regista.domain.replay import replay
from regista.templates import render_attacking_burst

pytestmark = pytest.mark.contract

MATCH_ID = MatchId(3_773_497)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVENTS_PATH = pinned_events_path(MATCH_ID)
GOLDEN_PATH = REPOSITORY_ROOT / "tests/golden" / f"{MATCH_ID}-attacking-burst.json"
SET_PIECE_PASS_TYPES = {"Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"}


def _events() -> list[Event]:
    if not EVENTS_PATH.exists():
        pytest.skip(f"download StatsBomb match {MATCH_ID} to run the replay contract")
    return load_events(EVENTS_PATH, MATCH_ID)


def _cards(events: list[Event], settings: BurstSettings | None = None) -> list[AttackingBurst]:
    return list(replay(events, AttackingBurstDetector(settings or BurstSettings())))


def _snapshot(cards: list[AttackingBurst]) -> dict[str, object]:
    settings = asdict(BurstSettings())
    settings["minimum_rate_ratio"] = str(settings["minimum_rate_ratio"])
    return {
        "match_id": MATCH_ID,
        "detector": "attacking_burst",
        "settings": settings,
        "cards": [
            {
                "period": card.fired_at.period,
                "minute": card.fired_at.minute,
                "second": card.fired_at.second,
                "team": card.team.name,
                "sentence": render_attacking_burst(card),
                "earlier_seconds": card.earlier_seconds,
                "trigger_event_id": card.trigger_event_id,
                "recent_shot_ids": list(card.recent_shot_ids),
                "earlier_shot_ids": list(card.earlier_shot_ids),
                "recent_entry_ids": list(card.recent_entry_ids),
                "earlier_entry_ids": list(card.earlier_entry_ids),
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


def test_cards_before_a_cut_ignore_everything_after_it() -> None:
    # Eager settings so the match produces cards on both sides of the cut.
    eager = BurstSettings(minimum_recent_shots=3, minimum_rate_ratio=Fraction(1))
    events = _events()
    cut = len(events) // 2
    swapped = {event.team for event in events}
    other = {team: next(item for item in swapped if item != team) for team in swapped}
    altered = events[:cut] + [replace(event, team=other[event.team]) for event in events[cut:]]
    early = {event.identifier for event in events[:cut]}

    original = [card for card in _cards(events, eager) if card.trigger_event_id in early]
    after_alteration = [card for card in _cards(altered, eager) if card.trigger_event_id in early]

    assert original
    assert after_alteration == original


def _is_entry(record: dict[str, object]) -> bool:
    kind = cast(dict[str, str], record["type"])["name"]
    if kind == "Pass":
        details = cast(dict[str, object], record["pass"])
        pass_type = cast(dict[str, str], details.get("type", {})).get("name")
        if "outcome" in details or pass_type in SET_PIECE_PASS_TYPES:
            return False
    elif kind == "Carry":
        details = cast(dict[str, object], record["carry"])
    else:
        return False
    start_x = cast(list[float], record["location"])[0]
    end_x = cast(list[float], details["end_location"])[0]
    return start_x < 80 <= end_x


def _independent_cards() -> list[tuple[object, ...]]:
    """Recompute the cards from the raw file with separate, plain code."""
    with EVENTS_PATH.open(encoding="utf-8") as event_file:
        raw = cast(list[dict[str, object]], json.load(event_file))
    records = sorted(raw, key=lambda record: cast(int, record["index"]))
    spans: dict[int, list[int]] = {}
    shots: list[tuple[str, int, int]] = []
    entries: list[tuple[str, int, int]] = []
    cooldowns: dict[str, tuple[int, int]] = {}
    cards: list[tuple[object, ...]] = []
    for record in records:
        period = cast(int, record["period"])
        now = cast(int, record["minute"]) * 60 + cast(int, record["second"])
        team = cast(dict[str, str], record["team"])["name"]
        span = spans.setdefault(period, [now, now])
        span[1] = max(span[1], now)
        if _is_entry(record):
            entries.append((team, period, now))
        if cast(dict[str, str], record["type"])["name"] != "Shot":
            continue
        shot = cast(dict[str, dict[str, str]], record["shot"])
        if shot["type"]["name"] == "Penalty":
            continue
        shots.append((team, period, now))
        if now - spans[period][0] < 600:
            continue
        cooldown = cooldowns.get(team)
        if cooldown is not None and cooldown[0] == period and now < cooldown[1]:
            continue
        earlier_seconds = sum(end - start for p, (start, end) in spans.items() if p < period)
        earlier_seconds += now - 600 - spans[period][0]
        own = [shot for shot in shots if shot[0] == team]
        recent = [shot for shot in own if shot[1] == period and shot[2] > now - 600]
        if earlier_seconds < 600 or len(recent) < 4:
            continue
        if len(recent) * earlier_seconds < 3 * (len(own) - len(recent)) * 600:
            continue
        own_entries = [entry for entry in entries if entry[0] == team]
        recent_entries = [e for e in own_entries if e[1] == period and e[2] > now - 600]
        cards.append(
            (
                period,
                record["minute"],
                record["second"],
                team,
                len(recent),
                len(own) - len(recent),
                earlier_seconds,
                len(recent_entries),
            )
        )
        cooldowns[team] = (period, now + 600)
    return cards


def test_cards_match_an_independent_recomputation() -> None:
    detected = [
        (
            card.fired_at.period,
            card.fired_at.minute,
            card.fired_at.second,
            card.team.name,
            len(card.recent_shot_ids),
            len(card.earlier_shot_ids),
            card.earlier_seconds,
            len(card.recent_entry_ids),
        )
        for card in _cards(_events())
    ]

    assert detected == _independent_cards()
