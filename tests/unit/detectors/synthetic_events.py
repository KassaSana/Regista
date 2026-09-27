"""Hand-built domain events for detector tests. No provider data is copied."""

from __future__ import annotations

from regista.domain.entries import Channel
from regista.domain.events import ActionType, BallMovement, Event, MatchClock, Team
from regista.domain.geometry import Point
from regista.domain.ids import EventId, MatchId, TeamId

MATCH = MatchId(1)
HOME = Team(identifier=TeamId(1), name="Home")
AWAY = Team(identifier=TeamId(2), name="Away")
SOURCE = "Synthetic"

# An end location comfortably inside each channel.
CHANNEL_Y = {Channel.LEFT: 10.0, Channel.CENTER: 40.0, Channel.RIGHT: 70.0}


class EventStream:
    """Builds events with increasing sequence numbers, in the order they are added."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def other(self, team: Team, period: int, minute: int, second: int = 0) -> Event:
        """Add a non-moving event (it only advances the replay clock)."""
        return self._add(team, MatchClock(period, minute, second), ActionType.OTHER, None)

    def entry(
        self,
        team: Team,
        period: int,
        minute: int,
        second: int,
        channel: Channel,
        *,
        action: ActionType = ActionType.PASS,
        completed: bool = True,
        open_play: bool = True,
    ) -> Event:
        """Add a pass or carry from x = 70 to x = 85, ending in the given channel."""
        movement = BallMovement(
            start=Point(x=70.0, y=CHANNEL_Y[channel]),
            end=Point(x=85.0, y=CHANNEL_Y[channel]),
            completed=completed,
            open_play=open_play,
        )
        return self._add(team, MatchClock(period, minute, second), action, movement)

    def _add(
        self, team: Team, clock: MatchClock, action: ActionType, movement: BallMovement | None
    ) -> Event:
        sequence = len(self.events) + 1
        event = Event(
            identifier=EventId(f"event-{sequence}"),
            sequence=sequence,
            match_id=MATCH,
            clock=clock,
            team=team,
            action=action,
            location=None if movement is None else movement.start,
            movement=movement,
            source=SOURCE,
            provider_record={},
        )
        self.events.append(event)
        return event


def add_balanced_baseline(stream: EventStream, team: Team = HOME, period: int = 1) -> list[Event]:
    """Add 12 entries, 4 per channel, every 40 seconds from 0:00 to 7:20 of period 1."""
    channels = [Channel.LEFT, Channel.CENTER, Channel.RIGHT] * 4
    return [
        stream.entry(team, period, *divmod(40 * index, 60), channel)
        for index, channel in enumerate(channels)
    ]


def add_baseline(stream: EventStream, channels: list[Channel], team: Team = HOME) -> list[Event]:
    """Add entries in the given channels every 40 seconds from 0:00 of period 1."""
    return [
        stream.entry(team, 1, *divmod(40 * index, 60), channel)
        for index, channel in enumerate(channels)
    ]


def add_recent(
    stream: EventStream,
    channels: list[Channel],
    *,
    team: Team = HOME,
    period: int = 1,
    first_minute: int = 11,
    open_play: bool = True,
) -> list[Event]:
    """Add one entry per minute starting at ``first_minute``, in the given channels."""
    return [
        stream.entry(team, period, first_minute + offset, 0, channel, open_play=open_play)
        for offset, channel in enumerate(channels)
    ]
