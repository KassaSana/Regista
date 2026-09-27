"""The replay engine feeds events strictly in provider order."""

import pytest

from regista.domain.events import ActionType, Event, MatchClock, Team
from regista.domain.ids import EventId, MatchId, TeamId
from regista.domain.insights import AttackingSideShift
from regista.domain.replay import ReplayOrderError, replay


class RecordingDetector:
    def __init__(self) -> None:
        self.seen: list[int] = []

    def observe(self, event: Event) -> list[AttackingSideShift]:
        self.seen.append(event.sequence)
        return []


def event(sequence: int) -> Event:
    return Event(
        identifier=EventId(f"event-{sequence}"),
        sequence=sequence,
        match_id=MatchId(1),
        clock=MatchClock(period=1, minute=0, second=0),
        team=Team(identifier=TeamId(1), name="Home"),
        action=ActionType.OTHER,
        location=None,
        movement=None,
        source="Synthetic",
        provider_record={},
    )


def test_replay_feeds_every_event_in_order() -> None:
    detector = RecordingDetector()

    assert list(replay([event(1), event(2), event(5)], detector)) == []
    assert detector.seen == [1, 2, 5]


@pytest.mark.parametrize("sequences", [[2, 1], [1, 1]])
def test_replay_rejects_events_out_of_order(sequences: list[int]) -> None:
    events = [event(sequence) for sequence in sequences]

    with pytest.raises(ReplayOrderError):
        list(replay(events, RecordingDetector()))
