"""Templates: turn detector findings into plain sentences.

Detectors decide; templates render. A template only restates the numbers in an
insight. It never adds causes or intent.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from math import floor

from regista.domain.entries import Channel, channel_of
from regista.domain.events import Event, MatchClock
from regista.domain.insights import AttackingSideShift
from regista.domain.match_facts import (
    FormationChangeFact,
    MatchFact,
    StartingLineupFact,
    SubstitutionFact,
)


def _formation(digits: str) -> str:
    return "-".join(digits) if digits.isdigit() else digits


def render_match_fact(fact: MatchFact) -> str:
    """State a recorded match fact without implying cause or medical condition."""
    if isinstance(fact, StartingLineupFact):
        return f"{fact.team.name} started in a recorded {_formation(fact.formation)} shape."
    if isinstance(fact, SubstitutionFact):
        return f"{fact.entering.name} replaced {fact.departing.name} for {fact.team.name}."
    return (
        f"The recorded formation for {fact.team.name} changed from "
        f"{_formation(fact.previous_formation)} to {_formation(fact.formation)}."
    )


def render_match_fact_evidence(fact: MatchFact) -> list[str]:
    """List the exact event records and lineup names behind a fact."""
    if isinstance(fact, StartingLineupFact):
        return [
            f"  recorded event: {fact.evidence_event_id} ({fact.source})",
            "  starting players: " + ", ".join(player.name for player in fact.players),
        ]
    if isinstance(fact, FormationChangeFact):
        return [
            f"  previous formation event: {fact.previous_event_id} ({fact.previous_source})",
            f"  new formation event: {fact.evidence_event_id} ({fact.source})",
        ]
    return [f"  recorded event: {fact.evidence_event_id} ({fact.source})"]


def render_attacking_side_shift(card: AttackingSideShift) -> str:
    """Return the one-sentence card text for an attacking-side shift."""
    channel = card.channel
    return (
        f"{card.team.name}'s final-third entries have shifted to the {channel.value}: "
        f"{card.recent.count(channel)} of the last {card.recent.total} "
        f"({_percent(card.recent.share(channel))}%), "
        f"up from {card.baseline.count(channel)} of {card.baseline.total} "
        f"({_percent(card.baseline.share(channel))}%) earlier."
    )


def render_clock(clock: MatchClock) -> str:
    """Return a compact match time such as ``period 2, 63:05``."""
    return f"period {clock.period}, {clock.minute:02d}:{clock.second:02d}"


def render_evidence(
    card: AttackingSideShift,
    recent_entries: Sequence[Event],
    baseline_entries: Sequence[Event],
) -> list[str]:
    """Return indented lines that let a person check a card against its entries.

    The caller passes the entry events named by the card's identifiers, in order.
    """
    lines = [f"  {'channel':<8}{'recent':<16}{'baseline':<16}change"]
    for channel in Channel:
        recent_share = card.recent.share(channel)
        baseline_share = card.baseline.share(channel)
        lines.append(
            f"  {channel.value:<8}"
            f"{f'{card.recent.count(channel)} of {card.recent.total}':<9}"
            f"{f'{_percent(recent_share)}%':<7}"
            f"{f'{card.baseline.count(channel)} of {card.baseline.total}':<9}"
            f"{f'{_percent(baseline_share)}%':<7}"
            f"{_percent(recent_share - baseline_share):+d} points"
        )
    lines.append(f"  recent window entries (period {card.fired_at.period}):")
    lines.extend(f"    {_describe_entry(entry)}" for entry in recent_entries)
    lines.append("  baseline entries by period:")
    for period in sorted({entry.clock.period for entry in baseline_entries}):
        channels = [
            channel_of(entry.movement.end)
            for entry in baseline_entries
            if entry.clock.period == period and entry.movement is not None
        ]
        counts = ", ".join(f"{channel.value} {channels.count(channel)}" for channel in Channel)
        lines.append(f"    period {period}: {counts}")
    return lines


def _describe_entry(entry: Event) -> str:
    movement = entry.movement
    if movement is None:
        return f"{render_clock(entry.clock)}  {entry.action.value}"
    start, end = movement.start, movement.end
    return (
        f"{render_clock(entry.clock)}  {entry.action.value:<5}  "
        f"({start.x:5.1f}, {start.y:4.1f}) -> ({end.x:5.1f}, {end.y:4.1f})  "
        f"{channel_of(end).value}"
    )


def _percent(share: Fraction) -> int:
    """Round a share to a whole percentage, halves rounding up."""
    return floor(share * 100 + Fraction(1, 2))
