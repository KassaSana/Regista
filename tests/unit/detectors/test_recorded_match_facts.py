"""Phase 3 recorded facts on synthetic provider-neutral events."""

from __future__ import annotations

from regista.detectors.recorded_match_facts import RecordedMatchFactsDetector
from regista.domain.events import (
    ActionType,
    Event,
    FormationDetail,
    MatchClock,
    NamedPlayer,
    SubstitutionDetail,
    Team,
)
from regista.domain.ids import EventId, MatchId, PlayerId, TeamId
from regista.domain.match_facts import (
    FormationChangeFact,
    StartingLineupFact,
    SubstitutionFact,
)
from regista.domain.replay import replay
from regista.templates import render_match_fact, render_match_fact_evidence

HOME = Team(TeamId(1), "Home")
AWAY = Team(TeamId(2), "Away")
PLAYERS = tuple(NamedPlayer(PlayerId(number), f"Player {number}") for number in range(1, 12))


def event(
    sequence: int,
    action: ActionType,
    detail: FormationDetail | SubstitutionDetail | None = None,
    *,
    team: Team = HOME,
    source: str = "Synthetic source",
) -> Event:
    return Event(
        EventId(f"event-{sequence}"),
        sequence,
        MatchId(1),
        MatchClock(1, sequence, 0),
        team,
        action,
        None,
        None,
        source,
        {},
        detail,
    )


def test_starting_lineup_and_substitution_are_factual_with_event_evidence() -> None:
    start = event(1, ActionType.FORMATION_CHANGE, FormationDetail("433", True, PLAYERS))
    substitution = event(
        2,
        ActionType.SUBSTITUTION,
        SubstitutionDetail(PLAYERS[0], NamedPlayer(PlayerId(12), "Replacement")),
    )

    facts = list(replay([start, substitution], RecordedMatchFactsDetector()))

    assert isinstance(facts[0], StartingLineupFact)
    assert facts[0].players == PLAYERS
    assert facts[0].evidence_event_id == start.identifier
    assert render_match_fact(facts[0]) == "Home started in a recorded 4-3-3 shape."
    assert "Player 11" in render_match_fact_evidence(facts[0])[1]
    assert isinstance(facts[1], SubstitutionFact)
    assert facts[1].evidence_event_id == substitution.identifier
    assert render_match_fact(facts[1]) == "Replacement replaced Player 1 for Home."


def test_unchanged_formation_and_other_events_are_quiet() -> None:
    facts = list(
        replay(
            [
                event(1, ActionType.FORMATION_CHANGE, FormationDetail("433", True, PLAYERS)),
                event(2, ActionType.OTHER),
                event(3, ActionType.FORMATION_CHANGE, FormationDetail("433", False)),
            ],
            RecordedMatchFactsDetector(),
        )
    )

    assert len(facts) == 1
    assert isinstance(facts[0], StartingLineupFact)


def test_changed_formation_uses_the_last_record_for_that_team_only() -> None:
    facts = list(
        replay(
            [
                event(1, ActionType.FORMATION_CHANGE, FormationDetail("433", True, PLAYERS)),
                event(
                    2,
                    ActionType.FORMATION_CHANGE,
                    FormationDetail("442", True, PLAYERS),
                    team=AWAY,
                ),
                event(
                    3,
                    ActionType.FORMATION_CHANGE,
                    FormationDetail("433", False),
                    source="Updated source",
                ),
                event(4, ActionType.FORMATION_CHANGE, FormationDetail("4231", False)),
            ],
            RecordedMatchFactsDetector(),
        )
    )

    assert len(facts) == 3
    change = facts[-1]
    assert isinstance(change, FormationChangeFact)
    assert (change.previous_formation, change.formation) == ("433", "4231")
    assert change.previous_event_id == EventId("event-3")
    assert change.previous_source == "Updated source"
    assert change.evidence_event_id == EventId("event-4")
    assert render_match_fact(change) == (
        "The recorded formation for Home changed from 4-3-3 to 4-2-3-1."
    )


def test_future_events_cannot_change_earlier_facts() -> None:
    prefix = [
        event(1, ActionType.FORMATION_CHANGE, FormationDetail("433", True, PLAYERS)),
        event(2, ActionType.FORMATION_CHANGE, FormationDetail("442", False)),
    ]
    earlier = list(replay(prefix, RecordedMatchFactsDetector()))
    with_future = list(
        replay(
            prefix + [event(3, ActionType.FORMATION_CHANGE, FormationDetail("352", False))],
            RecordedMatchFactsDetector(),
        )
    )

    assert with_future[: len(earlier)] == earlier
