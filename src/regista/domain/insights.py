"""Insights detectors produce: structured findings, never prose.

Templates turn these into sentences. Every insight carries the identifiers of
its supporting events and the sources they came from.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from regista.domain.entries import Channel
from regista.domain.events import MatchClock, Team
from regista.domain.ids import EventId, MatchId


@dataclass(frozen=True, slots=True)
class ChannelCounts:
    """How many final-third entries ended in each channel."""

    left: int
    center: int
    right: int

    @property
    def total(self) -> int:
        """Return the number of entries across all channels."""
        return self.left + self.center + self.right

    def count(self, channel: Channel) -> int:
        """Return the number of entries that ended in one channel."""
        match channel:
            case Channel.LEFT:
                return self.left
            case Channel.CENTER:
                return self.center
            case Channel.RIGHT:
                return self.right

    def share(self, channel: Channel) -> Fraction:
        """Return one channel's exact share of the entries (zero when there are none)."""
        if self.total == 0:
            return Fraction(0)
        return Fraction(self.count(channel), self.total)


@dataclass(frozen=True, slots=True)
class AttackingSideShift:
    """A team's recent final-third entries moved toward one channel.

    ``recent`` counts the entries in the recent window and ``baseline`` counts
    every earlier entry. ``trigger_event_id`` is the replay position at which
    the detector fired.
    """

    match_id: MatchId
    team: Team
    channel: Channel
    fired_at: MatchClock
    trigger_event_id: EventId
    recent: ChannelCounts
    baseline: ChannelCounts
    recent_entry_ids: tuple[EventId, ...]
    baseline_entry_ids: tuple[EventId, ...]
    sources: tuple[str, ...]

    @property
    def share_increase(self) -> Fraction:
        """Return how much the reported channel's share grew, as an exact fraction."""
        return self.recent.share(self.channel) - self.baseline.share(self.channel)

    @property
    def channels_losing_share(self) -> tuple[Channel, ...]:
        """Return the channels whose share fell: supporting evidence for the shift."""
        return tuple(
            channel
            for channel in Channel
            if self.recent.share(channel) < self.baseline.share(channel)
        )
