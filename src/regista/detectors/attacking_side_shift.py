"""The Phase 1 attacking-side shift detector.

Specification: ``docs/specs/phase-1-attacking-side-shift.md``. The detector is
incremental: it keeps only what it has seen so far, so the baseline is always
"everything before the recent window", never a match-wide aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from regista.domain.entries import Channel, channel_of, is_final_third_entry
from regista.domain.events import Event, MatchClock, Team
from regista.domain.ids import TeamId
from regista.domain.insights import AttackingSideShift, ChannelCounts


@dataclass(frozen=True, slots=True)
class SideShiftSettings:
    """Thresholds for the detector. Initial defaults to evaluate, not tuned values."""

    window_seconds: int = 600
    minimum_recent_entries: int = 8
    minimum_baseline_entries: int = 12
    minimum_share_increase: Fraction = Fraction(1, 4)
    cooldown_seconds: int = 600


@dataclass(frozen=True, slots=True)
class _Cooldown:
    period: int
    until_elapsed_seconds: int

    def is_active(self, clock: MatchClock) -> bool:
        return clock.period == self.period and clock.elapsed_seconds < self.until_elapsed_seconds


class AttackingSideShiftDetector:
    """Fires when one team's recent final-third entries move toward one channel."""

    def __init__(self, settings: SideShiftSettings | None = None) -> None:
        self._settings = settings or SideShiftSettings()
        # Learned in replay order: the clock of the first event seen in each period.
        self._period_start_seconds: dict[int, int] = {}
        # Teams in order of first appearance, so cards come out in a stable order.
        self._teams: dict[TeamId, Team] = {}
        self._entries: dict[TeamId, list[Event]] = {}
        self._cooldowns: dict[TeamId, _Cooldown] = {}

    def observe(self, event: Event) -> list[AttackingSideShift]:
        """Record one event, then check every team at this replay position."""
        clock = event.clock
        self._period_start_seconds.setdefault(clock.period, clock.elapsed_seconds)
        self._teams.setdefault(event.team.identifier, event.team)
        if is_final_third_entry(event):
            self._entries.setdefault(event.team.identifier, []).append(event)

        # A window never crosses a period boundary, so nothing fires until a
        # full window has elapsed in the current period.
        period_elapsed = clock.elapsed_seconds - self._period_start_seconds[clock.period]
        if period_elapsed < self._settings.window_seconds:
            return []

        cards: list[AttackingSideShift] = []
        for team in self._teams.values():
            cooldown = self._cooldowns.get(team.identifier)
            if cooldown is not None and cooldown.is_active(clock):
                continue
            card = self._evaluate(team, event)
            if card is not None:
                cards.append(card)
                self._cooldowns[team.identifier] = _Cooldown(
                    period=clock.period,
                    until_elapsed_seconds=clock.elapsed_seconds + self._settings.cooldown_seconds,
                )
        return cards

    def _evaluate(self, team: Team, trigger: Event) -> AttackingSideShift | None:
        now = trigger.clock
        window_start = now.elapsed_seconds - self._settings.window_seconds
        recent: list[Event] = []
        baseline: list[Event] = []
        for entry in self._entries.get(team.identifier, []):
            in_window = (
                entry.clock.period == now.period and entry.clock.elapsed_seconds > window_start
            )
            (recent if in_window else baseline).append(entry)

        if len(recent) < self._settings.minimum_recent_entries:
            return None
        if len(baseline) < self._settings.minimum_baseline_entries:
            return None

        recent_counts = _count_by_channel(recent)
        baseline_counts = _count_by_channel(baseline)
        best_channel: Channel | None = None
        best_increase = Fraction(0)
        # Channel order (left, center, right) breaks ties: the first wins.
        for channel in Channel:
            increase = recent_counts.share(channel) - baseline_counts.share(channel)
            if increase >= self._settings.minimum_share_increase and (
                best_channel is None or increase > best_increase
            ):
                best_channel = channel
                best_increase = increase
        if best_channel is None:
            return None

        return AttackingSideShift(
            match_id=trigger.match_id,
            team=team,
            channel=best_channel,
            fired_at=now,
            trigger_event_id=trigger.identifier,
            recent=recent_counts,
            baseline=baseline_counts,
            recent_entry_ids=tuple(entry.identifier for entry in recent),
            baseline_entry_ids=tuple(entry.identifier for entry in baseline),
            sources=tuple(sorted({entry.source for entry in (*recent, *baseline)})),
        )


def _count_by_channel(entries: list[Event]) -> ChannelCounts:
    channels = [channel_of(entry.movement.end) for entry in entries if entry.movement is not None]
    return ChannelCounts(
        left=channels.count(Channel.LEFT),
        center=channels.count(Channel.CENTER),
        right=channels.count(Channel.RIGHT),
    )
