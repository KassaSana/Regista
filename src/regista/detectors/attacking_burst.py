"""The attacking burst detector: a team's shots suddenly come much faster.

Specification: ``docs/specs/phase-2-attacking-burst.md``. Like the side-shift
detector it is incremental: the earlier rate is always "everything before the
recent window", never a match-wide aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from regista.domain.entries import is_final_third_entry
from regista.domain.events import ActionType, Event, MatchClock
from regista.domain.ids import TeamId
from regista.domain.insights import AttackingBurst


@dataclass(frozen=True, slots=True)
class BurstSettings:
    """Thresholds for the detector. Initial defaults to evaluate, not tuned values."""

    window_seconds: int = 600
    minimum_recent_shots: int = 4
    minimum_rate_ratio: Fraction = Fraction(3)
    minimum_earlier_seconds: int = 600
    cooldown_seconds: int = 600


def counts_as_burst_shot(event: Event) -> bool:
    """Return whether an event is a shot the detector counts: any shot except a penalty."""
    return event.action is ActionType.SHOT and event.shot is not None and not event.shot.penalty


class AttackingBurstDetector:
    """Fires at a team's own shot when its recent shots far outpace its earlier rate."""

    def __init__(self, settings: BurstSettings | None = None) -> None:
        self._settings = settings or BurstSettings()
        # Learned in replay order: the first and latest clock seen in each period.
        self._period_start_seconds: dict[int, int] = {}
        self._period_latest_seconds: dict[int, int] = {}
        self._shots: dict[TeamId, list[Event]] = {}
        self._entries: dict[TeamId, list[Event]] = {}
        # Per team: (period, elapsed seconds) until which no new card may fire.
        self._cooldowns: dict[TeamId, tuple[int, int]] = {}

    def observe(self, event: Event) -> list[AttackingBurst]:
        """Record one event; evaluate its team only when the event is a counted shot."""
        clock = event.clock
        self._period_start_seconds.setdefault(clock.period, clock.elapsed_seconds)
        latest = self._period_latest_seconds.get(clock.period, clock.elapsed_seconds)
        self._period_latest_seconds[clock.period] = max(latest, clock.elapsed_seconds)
        team = event.team.identifier
        if is_final_third_entry(event):
            self._entries.setdefault(team, []).append(event)
        if not counts_as_burst_shot(event):
            return []
        self._shots.setdefault(team, []).append(event)

        period_elapsed = clock.elapsed_seconds - self._period_start_seconds[clock.period]
        if period_elapsed < self._settings.window_seconds:
            return []
        cooldown = self._cooldowns.get(team)
        if (
            cooldown is not None
            and cooldown[0] == clock.period
            and clock.elapsed_seconds < cooldown[1]
        ):
            return []
        card = self._evaluate(event)
        if card is None:
            return []
        self._cooldowns[team] = (
            clock.period,
            clock.elapsed_seconds + self._settings.cooldown_seconds,
        )
        return [card]

    def _earlier_seconds(self, now: MatchClock) -> int:
        earlier = sum(
            self._period_latest_seconds[period] - start
            for period, start in self._period_start_seconds.items()
            if period < now.period
        )
        window_start = now.elapsed_seconds - self._settings.window_seconds
        return earlier + window_start - self._period_start_seconds[now.period]

    def _split(self, events: list[Event], now: MatchClock) -> tuple[list[Event], list[Event]]:
        window_start = now.elapsed_seconds - self._settings.window_seconds
        recent: list[Event] = []
        earlier: list[Event] = []
        for event in events:
            in_window = (
                event.clock.period == now.period and event.clock.elapsed_seconds > window_start
            )
            (recent if in_window else earlier).append(event)
        return recent, earlier

    def _evaluate(self, trigger: Event) -> AttackingBurst | None:
        settings = self._settings
        now = trigger.clock
        team = trigger.team.identifier
        earlier_seconds = self._earlier_seconds(now)
        if earlier_seconds < settings.minimum_earlier_seconds:
            return None
        recent_shots, earlier_shots = self._split(self._shots[team], now)
        if len(recent_shots) < settings.minimum_recent_shots:
            return None
        # Recent rate at least ``ratio`` times the earlier rate, in exact arithmetic:
        # recent / window >= ratio * earlier / earlier_seconds.
        if (
            len(recent_shots) * earlier_seconds
            < settings.minimum_rate_ratio * len(earlier_shots) * settings.window_seconds
        ):
            return None
        recent_entries, earlier_entries = self._split(self._entries.get(team, []), now)
        evidence = (*recent_shots, *earlier_shots, *recent_entries, *earlier_entries)
        return AttackingBurst(
            match_id=trigger.match_id,
            team=trigger.team,
            fired_at=now,
            trigger_event_id=trigger.identifier,
            window_seconds=settings.window_seconds,
            earlier_seconds=earlier_seconds,
            recent_shot_ids=tuple(event.identifier for event in recent_shots),
            earlier_shot_ids=tuple(event.identifier for event in earlier_shots),
            recent_entry_ids=tuple(event.identifier for event in recent_entries),
            earlier_entry_ids=tuple(event.identifier for event in earlier_entries),
            sources=tuple(sorted({event.source for event in evidence})),
        )
