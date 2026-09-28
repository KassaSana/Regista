"""Build the Phase 2 card-judging packet from development matches only.

Run: ``uv run python scripts/research/phase2_judging_packet.py``.
Writes ``out/phase2-judging/packet.html`` and ``selection.json`` (both
git-ignored, because they describe provider events). The packet shows every card
of five seeded development matches in replay order, with the evidence behind
each card and blank judgment fields. Nothing in it is a judgment.
"""

from __future__ import annotations

import html
import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

from phase2_card_audit import ROOT, development_event_files, development_ids

from regista.adapters.statsbomb.events import load_events
from regista.detectors.attacking_burst import AttackingBurstDetector, BurstSettings
from regista.detectors.attacking_side_shift import AttackingSideShiftDetector, SideShiftSettings
from regista.domain.entries import Channel, channel_of
from regista.domain.events import Event
from regista.domain.ids import EventId, MatchId
from regista.domain.insights import AttackingBurst, AttackingSideShift
from regista.domain.replay import replay
from regista.pipeline.catalog import load_corpus
from regista.templates import render_attacking_burst, render_attacking_side_shift
from regista.warehouse.research import connect_research

SEED = 20260928
OUTPUT = ROOT / "out/phase2-judging"
ASSETS = Path(__file__).resolve().parent / "judging_packet"
WAREHOUSE = ROOT / "data/warehouse/regista.duckdb"
PREMIER_LEAGUE = (2, 27)
SERIE_A = (12, 27)
MODERN_CLUB = {(11, 90), (9, 281), (7, 108), (7, 235)}
PERIOD_NAMES = {1: "first half", 2: "second half", 3: "extra time, first", 4: "extra time, second"}

type Card = AttackingSideShift | AttackingBurst


@dataclass(frozen=True, slots=True)
class MatchInfo:
    """Kickoff-time facts shown in the packet header: no result."""

    match_id: int
    competition: str
    season: str
    date: str
    home: str
    away: str
    season_key: tuple[int, int]


def match_metadata() -> dict[int, MatchInfo]:
    connection = connect_research(WAREHOUSE)
    rows = connection.sql(
        "SELECT match_id, competition_id, season_id, match_date::VARCHAR, "
        "provider_record->>'$.competition.competition_name', "
        "provider_record->>'$.season.season_name', "
        "provider_record->>'$.home_team.home_team_name', "
        "provider_record->>'$.away_team.away_team_name' FROM normalized.matches"
    ).fetchall()
    return {
        int(row[0]): MatchInfo(
            match_id=int(row[0]),
            competition=str(row[4]),
            season=str(row[5]),
            date=str(row[3]),
            home=str(row[6]),
            away=str(row[7]),
            season_key=(int(row[1]), int(row[2])),
        )
        for row in rows
    }


def _cards(events: list[Event]) -> list[Card]:
    order = {event.identifier: event.sequence for event in events}
    cards: list[Card] = [
        *replay(events, AttackingBurstDetector(BurstSettings())),
        *replay(events, AttackingSideShiftDetector(SideShiftSettings())),
    ]
    return sorted(cards, key=lambda card: order[card.trigger_event_id])


def _select(
    matches: dict[int, MatchInfo], files: dict[int, Path]
) -> list[tuple[str, MatchInfo, list[Event], list[Card]]]:
    """Pick one match per stratum with a fixed seed, among matches with a card."""
    inspected = set(load_corpus(ROOT / "catalog/corpus.toml").inspected_match_ids)
    candidates = sorted(set(files) - inspected)
    strata: list[tuple[str, Callable[[MatchInfo], bool]]] = [
        ("Premier League 2015/16", lambda info: info.season_key == PREMIER_LEAGUE),
        ("Serie A 2015/16", lambda info: info.season_key == SERIE_A),
        ("Recent club season", lambda info: info.season_key in MODERN_CLUB),
        (
            "International tournament",
            lambda info: info.season_key not in MODERN_CLUB | {PREMIER_LEAGUE, SERIE_A},
        ),
        ("Any development match", lambda info: True),
    ]
    generator = random.Random(SEED)
    chosen: list[tuple[str, MatchInfo, list[Event], list[Card]]] = []
    used: set[int] = set()
    for label, belongs in strata:
        pool = [identifier for identifier in candidates if belongs(matches[identifier])]
        generator.shuffle(pool)
        for identifier in pool:
            if identifier in used:
                continue
            events = load_events(files[identifier], MatchId(identifier))
            cards = _cards(events)
            if cards:
                chosen.append((label, matches[identifier], events, cards))
                used.add(identifier)
                break
    return chosen


def goal_for(event: Event) -> bool:
    """Read whether an event gave its team a goal (known when it happens)."""
    record = event.provider_record
    kind = cast(dict[str, object], record.get("type", {})).get("name")
    if kind == "Own Goal For":
        return True
    shot = record.get("shot")
    if kind != "Shot" or not isinstance(shot, dict) or event.clock.period >= 5:
        return False
    outcome = cast(dict[str, object], shot).get("outcome")
    return isinstance(outcome, dict) and cast(dict[str, object], outcome).get("name") == "Goal"


def _score_at(events: list[Event], trigger: Event, info: MatchInfo) -> str:
    home = away = 0
    for event in events:
        if event.sequence > trigger.sequence:
            break
        if goal_for(event):
            if event.team.name == info.home:
                home += 1
            else:
                away += 1
    return f"{info.home} {home}–{away} {info.away}"


def pitch_svg(marks: str) -> str:
    """A pitch in the card team's attacking frame: attack to the right, its left at the top."""
    scale = 3
    lines = "".join(
        f'<line x1="0" y1="{y * scale}" x2="{120 * scale}" y2="{y * scale}" class="lane"/>'
        for y in (80 / 3, 160 / 3)
    )
    return (
        f'<svg viewBox="-4 -14 {120 * scale + 8} {80 * scale + 18}" class="pitch" role="img">'
        f'<rect x="0" y="0" width="{120 * scale}" height="{80 * scale}" class="turf"/>'
        f'<line x1="{80 * scale}" y1="0" x2="{80 * scale}" y2="{80 * scale}" class="third"/>'
        f'<rect x="{102 * scale}" y="{18 * scale}" width="{18 * scale}" height="{44 * scale}" '
        f'class="box"/>{lines}'
        f'<text x="2" y="-4" class="label">its left ↑ · attacking →</text>{marks}</svg>'
    )


def _side_shift_evidence(card: AttackingSideShift, by_id: dict[EventId, Event]) -> str:
    marks = ""
    for identifier in card.baseline_entry_ids:
        movement = by_id[identifier].movement
        if movement is not None:
            marks += (
                f'<circle cx="{movement.end.x * 3}" cy="{movement.end.y * 3}" '
                'r="3" class="earlier"/>'
            )
    for identifier in card.recent_entry_ids:
        movement = by_id[identifier].movement
        if movement is None:
            continue
        named = "named" if channel_of(movement.end) is card.channel else "recent"
        marks += (
            f'<line x1="{movement.start.x * 3}" y1="{movement.start.y * 3}" '
            f'x2="{movement.end.x * 3}" y2="{movement.end.y * 3}" class="{named}"/>'
            f'<circle cx="{movement.end.x * 3}" cy="{movement.end.y * 3}" r="4" class="{named}"/>'
        )
    rows = "".join(
        f"<tr><td>{channel.value}</td><td>{card.recent.count(channel)} of {card.recent.total}</td>"
        f"<td>{card.baseline.count(channel)} of {card.baseline.total}</td></tr>"
        for channel in Channel
    )
    table = (
        f"<table><tr><th>channel</th><th>last 10 minutes</th><th>earlier</th></tr>{rows}</table>"
    )
    legend = (
        '<p class="legend">Lines: final-third entries in the last 10 minutes '
        "(highlighted when they end in the named channel). Grey dots: earlier entries.</p>"
    )
    return f'<div class="evidence">{pitch_svg(marks)}<div>{table}{legend}</div></div>'


def _burst_evidence(card: AttackingBurst, by_id: dict[EventId, Event]) -> str:
    marks = ""
    for identifier, kind in [
        *((identifier, "earlier") for identifier in card.earlier_shot_ids),
        *((identifier, "named") for identifier in card.recent_shot_ids),
    ]:
        location = by_id[identifier].location
        if location is not None:
            marks += f'<circle cx="{location.x * 3}" cy="{location.y * 3}" r="5" class="{kind}"/>'
    minutes = card.earlier_seconds // 60
    table = (
        "<table><tr><th></th><th>last 10 minutes</th>"
        f"<th>previous {minutes} minutes</th></tr>"
        f"<tr><td>shots</td><td>{len(card.recent_shot_ids)}</td>"
        f"<td>{len(card.earlier_shot_ids)}</td></tr>"
        f"<tr><td>final-third entries</td><td>{len(card.recent_entry_ids)}</td>"
        f"<td>{len(card.earlier_entry_ids)}</td></tr></table>"
    )
    legend = (
        '<p class="legend">Filled: shot locations in the last 10 minutes. '
        "Grey: earlier shots. Penalties are not counted.</p>"
    )
    return f'<div class="evidence">{pitch_svg(marks)}<div>{table}{legend}</div></div>'


def radio_inputs(name: str, options: list[str]) -> str:
    return "".join(
        f'<label><input type="radio" name="{name}" value="{html.escape(option)}"> '
        f"{html.escape(option)}</label>"
        for option in options
    )


# Framed for the owner's proposed experience (2026-09-28): during play a small
# light-bulb indicator the fan may open; every card stays available afterwards.
CARD_QUESTIONS = [
    (
        "open",
        "If a light bulb lit up at this moment, would opening it have been worth it?",
        ["Yes", "Maybe", "No"],
    ),
    (
        "obvious",
        "Would the broadcast or your own eyes probably have told you this already?",
        ["Yes", "No", "Not sure"],
    ),
    (
        "timing",
        "When is this most useful?",
        ["During play", "After the match", "Neither"],
    ),
    ("clear", "Is the sentence clear on first read?", ["Yes", "No"]),
    ("supported", "Does the evidence support the sentence?", ["Yes", "No", "Can't tell"]),
]
MATCH_QUESTIONS = [
    ("repetition", "Did any card feel like a repeat of an earlier one?", ["Yes", "No"]),
]
OVERALL_QUESTIONS = [
    ("again", "Would you use Regista for another match?", ["Yes", "Maybe", "No"]),
]


def question_fieldsets(prefix: str, questions: list[tuple[str, str, list[str]]]) -> str:
    return "".join(
        f"<fieldset><legend>{html.escape(text)}</legend>{radio_inputs(f'{prefix}.{key}', options)}"
        "</fieldset>"
        for key, text, options in questions
    )


def _card_html(
    number: int, card: Card, events: list[Event], by_id: dict[EventId, Event], info: MatchInfo
) -> tuple[str, str]:
    trigger = by_id[card.trigger_event_id]
    card_id = f"{info.match_id}:{card.trigger_event_id}:{type(card).__name__}"
    if isinstance(card, AttackingBurst):
        kind, sentence, evidence = (
            "Attacking burst",
            render_attacking_burst(card),
            _burst_evidence(card, by_id),
        )
    else:
        kind, sentence = "Attacking side", render_attacking_side_shift(card)
        evidence = _side_shift_evidence(card, by_id)
    clock = f"{card.fired_at.minute:02d}:{card.fired_at.second:02d}"
    period = PERIOD_NAMES.get(card.fired_at.period, f"period {card.fired_at.period}")
    body = (
        f'<article class="card" data-card="{html.escape(card_id)}">'
        f'<header><span class="num">Card {number}</span><span class="kind">{kind}</span>'
        f'<span class="clock">{clock} · {period}</span>'
        f'<span class="score">{html.escape(_score_at(events, trigger, info))}</span></header>'
        f'<p class="sentence">{html.escape(sentence)}</p>{evidence}'
        f'<div class="judge">{question_fieldsets(card_id, CARD_QUESTIONS)}'
        f'<label class="note">Note<textarea name="{html.escape(card_id)}.note" rows="2">'
        "</textarea></label></div></article>"
    )
    return card_id, body


STYLE = (ASSETS / "packet.css").read_text(encoding="utf-8")

SCRIPT = (ASSETS / "packet.js").read_text(encoding="utf-8")


def build() -> dict[str, object]:
    files = development_event_files(development_ids())
    selected = _select(match_metadata(), files)
    sections: list[str] = []
    selection: list[dict[str, object]] = []
    number = 0
    for label, info, events, cards in selected:
        by_id = {event.identifier: event for event in events}
        bodies: list[str] = []
        card_ids: list[str] = []
        for card in cards:
            number += 1
            card_id, body = _card_html(number, card, events, by_id, info)
            card_ids.append(card_id)
            bodies.append(body)
        match_key = f"match.{info.match_id}"
        sections.append(
            f"<section><h2>{html.escape(info.home)} v {html.escape(info.away)}</h2>"
            f'<p class="meta">{html.escape(info.competition)} {html.escape(info.season)} · '
            f"{html.escape(info.date)} · {html.escape(label)} · {len(cards)} "
            f"card{'s' if len(cards) != 1 else ''}</p>{''.join(bodies)}"
            f'<div class="match-questions"><p><strong>This match as a whole</strong></p>'
            f"{question_fieldsets(match_key, MATCH_QUESTIONS)}"
            f'<label class="note">Did you already know how this match went? Anything else?'
            f'<textarea name="{match_key}.note" rows="2"></textarea></label></div></section>'
        )
        selection.append({"stratum": label, "match_id": info.match_id, "cards": card_ids})
    packet = sha256(json.dumps(selection, sort_keys=True).encode()).hexdigest()[:12]
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Regista card judging</title><style>{STYLE}</style></head>"
        f'<body data-packet="{packet}"><main><h1>Regista card judging</h1>'
        f'<p class="sub">Packet {packet} · {number} cards from {len(selected)} development '
        "matches · private working file, do not circulate</p>"
        "<p>Read each match from top to bottom. Imagine each card as a light bulb that "
        "lights up during play and opens when you tap it, and that every card stays "
        "available after the match. Answer the questions for each card; notes are "
        "optional. The score shown "
        "is the score at that moment; the final result is not shown. Answers are kept in "
        "this browser as you go. When you finish, press Export and send the text back.</p>"
        f"{''.join(sections)}"
        "<h2>Overall</h2>"
        f"{question_fieldsets('overall', OVERALL_QUESTIONS)}"
        '<label class="note">Which one card, if any, would you have tapped the light bulb '
        'for? Why?<textarea name="overall.best" rows="3"></textarea></label>'
        '<label class="note">Anything missing that you expected Regista to notice?'
        '<textarea name="overall.missing" rows="3"></textarea></label>'
        '<p><button id="make-export" type="button">Export answers</button></p>'
        '<textarea id="export" readonly aria-label="Exported answers"></textarea>'
        "<footer>Data: StatsBomb. Cards come from Regista's detectors on StatsBomb Open "
        "Data, used for non-commercial research.</footer>"
        f"</main><script>{SCRIPT}</script></body></html>"
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "packet.html").write_text(page, encoding="utf-8")
    summary: dict[str, object] = {
        "packet": packet,
        "seed": SEED,
        "cards": number,
        "matches": selection,
    }
    (OUTPUT / "selection.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
