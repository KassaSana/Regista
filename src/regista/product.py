"""Assemble what the product shows for one match: the card stream and the replay export.

Everything here reads domain events only, in replay order. The export is thin on
purpose (see DATA_SOURCES.md): period boundaries, goals with the running score,
cards with only their own evidence events, and recorded facts. It never carries
the full event stream or any provider payload, and it never reads the recorded
final score, which is hindsight.
"""

from __future__ import annotations

from collections.abc import Sequence

from regista.detectors.attacking_burst import AttackingBurstDetector, BurstSettings
from regista.detectors.attacking_side_shift import AttackingSideShiftDetector, SideShiftSettings
from regista.detectors.recorded_match_facts import RecordedMatchFactsDetector
from regista.domain.events import ActionType, Event, MatchClock
from regista.domain.ids import EventId
from regista.domain.insights import AttackingBurst, AttackingSideShift
from regista.domain.match_facts import FormationChangeFact, MatchFact, StartingLineupFact
from regista.domain.matches import MatchRecord
from regista.domain.replay import replay
from regista.domain.score import Score, ScoreTracker, goal_scored_by
from regista.templates import (
    render_attacking_burst,
    render_attacking_burst_evidence,
    render_attacking_side_shift,
    render_evidence,
    render_match_fact,
)

SCHEMA_VERSION = 1
# Required wherever StatsBomb-derived analysis is shown (see DATA_SOURCES.md).
ATTRIBUTION = "Data: StatsBomb"

Card = AttackingSideShift | AttackingBurst
type Json = dict[str, object]


def build_card_stream(events: Sequence[Event]) -> list[Card]:
    """Replay both card detectors and return one stream in replay order.

    At a shared trigger event, the burst comes first.
    """
    sequence_of = {event.identifier: event.sequence for event in events}
    shifts = list(replay(events, AttackingSideShiftDetector(SideShiftSettings())))
    bursts = list(replay(events, AttackingBurstDetector(BurstSettings())))
    return sorted([*bursts, *shifts], key=lambda card: sequence_of[card.trigger_event_id])


def build_match_export(events: Sequence[Event], match: MatchRecord) -> Json:
    """Return the replay export for one match (schema ``schemas/replay.schema.json``)."""
    events_by_identifier = {event.identifier: event for event in events}
    tracker = ScoreTracker(match.home_team.identifier, match.away_team.identifier)
    score_after: dict[EventId, Score] = {}
    goals: list[Json] = []
    for event in events:
        before = tracker.score
        score = tracker.observe(event)
        score_after[event.identifier] = score
        if score != before and goal_scored_by(event) is not None:
            goals.append(
                {
                    "event_id": event.identifier,
                    "clock": _clock(event.clock),
                    "team_id": event.team.identifier,
                    "own_goal": event.own_goal_for,
                    "penalty": event.shot is not None and event.shot.penalty,
                    "score": _score(score),
                }
            )
    cards = [
        _card(card, events_by_identifier, score_after[card.trigger_event_id])
        for card in build_card_stream(events)
    ]
    facts = [_fact(fact) for fact in replay(events, RecordedMatchFactsDetector())]
    return {
        "schema_version": SCHEMA_VERSION,
        "attribution": ATTRIBUTION,
        "match": {
            "id": match.match_id,
            "competition": match.competition_name,
            "season": match.season_name,
            "date": match.match_date.isoformat(),
            "home": {"id": match.home_team.identifier, "name": match.home_team.name},
            "away": {"id": match.away_team.identifier, "name": match.away_team.name},
        },
        "periods": _periods(events),
        "goals": goals,
        "cards": cards,
        "facts": facts,
    }


def _card(card: Card, events_by_identifier: dict[EventId, Event], score: Score) -> Json:
    def resolve(identifiers: Sequence[EventId]) -> list[Event]:
        return [events_by_identifier[identifier] for identifier in identifiers]

    recent_entries = resolve(card.recent_entry_ids)
    if isinstance(card, AttackingBurst):
        shots = resolve(card.recent_shot_ids)
        kind, experimental = "burst", True
        sentence = render_attacking_burst(card)
        evidence_lines = render_attacking_burst_evidence(card, shots)
        evidence = [_evidence(shot, "shot") for shot in shots]
    else:
        kind, experimental = "side_shift", False
        sentence = render_attacking_side_shift(card)
        evidence_lines = render_evidence(card, recent_entries, resolve(card.baseline_entry_ids))
        evidence = []
    evidence.extend(_evidence(entry, "recent") for entry in recent_entries)
    return {
        "id": f"{kind}-{card.trigger_event_id}",
        "kind": kind,
        "experimental": experimental,
        "team_id": card.team.identifier,
        "clock": _clock(card.fired_at),
        "trigger_event_id": card.trigger_event_id,
        "score": _score(score),
        "sentence": sentence,
        "evidence_lines": [line.strip() for line in evidence_lines],
        "evidence": evidence,
        "sources": list(card.sources),
    }


def _evidence(event: Event, role: str) -> Json:
    movement = event.movement
    start = movement.start if movement is not None else event.location
    return {
        "event_id": event.identifier,
        "role": role,
        "clock": _clock(event.clock),
        "team_id": event.team.identifier,
        "action": event.action.value,
        "start": None if start is None else {"x": start.x, "y": start.y},
        "end": None if movement is None else {"x": movement.end.x, "y": movement.end.y},
    }


def _fact(fact: MatchFact) -> Json:
    if isinstance(fact, StartingLineupFact):
        kind = "lineup"
    elif isinstance(fact, FormationChangeFact):
        kind = "formation_change"
    else:
        kind = "substitution"
    return {
        "clock": _clock(fact.fired_at),
        "kind": kind,
        "team_id": fact.team.identifier,
        "sentence": render_match_fact(fact),
        "event_id": fact.evidence_event_id,
    }


def _periods(events: Sequence[Event]) -> list[Json]:
    """Each period's first start and last end, from the recorded period events."""
    starts: dict[int, MatchClock] = {}
    ends: dict[int, MatchClock] = {}
    for event in events:
        period = event.clock.period
        if event.action is ActionType.PERIOD_START and period not in starts:
            starts[period] = event.clock
        elif event.action is ActionType.PERIOD_END:
            ends[period] = event.clock
    return [
        {"period": period, "start": _clock(starts[period]), "end": _clock(ends[period])}
        for period in sorted(starts)
        if period in ends
    ]


def _clock(clock: MatchClock) -> Json:
    return {"period": clock.period, "minute": clock.minute, "second": clock.second}


def _score(score: Score) -> Json:
    return {"home": score.home, "away": score.away}
