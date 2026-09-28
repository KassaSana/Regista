"""Compare side-shift timing variants on acquired development matches only.

Run: ``uv run python scripts/research/phase2_side_shift_variants.py``.
Every variant runs through the production detector with one setting changed, so
cooldown interactions are real rather than simulated by filtering cards. The
output is aggregate JSON: no provider records and no fan judgments.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from statistics import median

from phase2_card_audit import development_event_files, development_ids

from regista.adapters.statsbomb.events import load_events
from regista.detectors.attacking_side_shift import AttackingSideShiftDetector, SideShiftSettings
from regista.domain.entries import Channel, channel_of, is_final_third_entry
from regista.domain.events import Event
from regista.domain.ids import MatchId
from regista.domain.insights import AttackingSideShift
from regista.domain.replay import replay

VARIANTS = {
    # The Phase 1 rule, which evaluates every team at every event.
    "current": SideShiftSettings(fire_on_own_entry=False),
    "own_entry": SideShiftSettings(fire_on_own_entry=True),
    "own_entry_within_30s": SideShiftSettings(
        fire_on_own_entry=False, maximum_seconds_since_own_entry=30
    ),
    "own_entry_within_60s": SideShiftSettings(
        fire_on_own_entry=False, maximum_seconds_since_own_entry=60
    ),
    "own_entry_within_120s": SideShiftSettings(
        fire_on_own_entry=False, maximum_seconds_since_own_entry=120
    ),
}
# Two cards describe the same moment when team, channel, and period agree and
# they fire at most one cooldown apart.
MATCH_TOLERANCE_SECONDS = 600
STALE_SECONDS = 180


@dataclass(frozen=True, slots=True)
class Fired:
    """One card with the context the comparison needs."""

    match_id: int
    team_id: int
    channel: Channel
    period: int
    seconds: int
    other_team_trigger: bool
    non_plurality: bool
    seconds_since_own_entry: int | None
    # Retrospective target only (as in research note 12): None when fewer than
    # eight same-period entries follow within ten minutes, otherwise whether the
    # named channel's later share stays at least 25 points above its baseline.
    sustained: bool | None


def _fired(match_id: int, card: AttackingSideShift, trigger: Event, entries: list[Event]) -> Fired:
    own = [
        entry
        for entry in entries
        if entry.team.identifier == card.team.identifier
        and entry.clock.period == card.fired_at.period
        and entry.sequence <= trigger.sequence
    ]
    named = card.recent.count(card.channel)
    future = [
        entry
        for entry in entries
        if entry.team.identifier == card.team.identifier
        and entry.clock.period == card.fired_at.period
        and entry.sequence > trigger.sequence
        and entry.clock.elapsed_seconds <= card.fired_at.elapsed_seconds + 600
    ]
    sustained: bool | None = None
    if len(future) >= 8:
        later = Fraction(
            sum(
                1
                for entry in future
                if entry.movement is not None and channel_of(entry.movement.end) is card.channel
            ),
            len(future),
        )
        sustained = later >= card.baseline.share(card.channel) + Fraction(1, 4)
    return Fired(
        match_id=match_id,
        team_id=int(card.team.identifier),
        channel=card.channel,
        period=card.fired_at.period,
        seconds=card.fired_at.elapsed_seconds,
        other_team_trigger=trigger.team.identifier != card.team.identifier,
        non_plurality=named < max(card.recent.count(channel) for channel in Channel),
        seconds_since_own_entry=(
            card.fired_at.elapsed_seconds - own[-1].clock.elapsed_seconds if own else None
        ),
        sustained=sustained,
    )


def _pair(
    current: list[Fired], variant: list[Fired]
) -> tuple[list[tuple[Fired, Fired]], list[Fired], list[Fired]]:
    """Pair cards describing the same moment, nearest in time first."""
    candidates = sorted(
        (abs(later.seconds - earlier.seconds), index, other)
        for index, earlier in enumerate(current)
        for other, later in enumerate(variant)
        if (earlier.match_id, earlier.team_id, earlier.channel, earlier.period)
        == (later.match_id, later.team_id, later.channel, later.period)
        and abs(later.seconds - earlier.seconds) <= MATCH_TOLERANCE_SECONDS
    )
    used_current: set[int] = set()
    used_variant: set[int] = set()
    pairs: list[tuple[Fired, Fired]] = []
    for _, index, other in candidates:
        if index in used_current or other in used_variant:
            continue
        used_current.add(index)
        used_variant.add(other)
        pairs.append((current[index], variant[other]))
    lost = [card for index, card in enumerate(current) if index not in used_current]
    new = [card for index, card in enumerate(variant) if index not in used_variant]
    return pairs, lost, new


def _persistence(cards: list[Fired]) -> str:
    """Sustained among cards with enough later entries, as 'sustained/eligible'."""
    eligible = [card for card in cards if card.sustained is not None]
    return f"{sum(1 for card in eligible if card.sustained)}/{len(eligible)}"


def _summary(cards: list[Fired], matches: int) -> dict[str, object]:
    per_match = Counter(card.match_id for card in cards)
    distribution = Counter(per_match.values())
    distribution[0] = matches - len(per_match)
    return {
        "cards": len(cards),
        "matches_with_cards": len(per_match),
        "cards_per_match": dict(sorted(distribution.items())),
        "non_plurality": sum(card.non_plurality for card in cards),
        "other_team_trigger": sum(card.other_team_trigger for card in cards),
        "over_180s_since_own_entry": sum(
            1
            for card in cards
            if card.seconds_since_own_entry is None or card.seconds_since_own_entry > STALE_SECONDS
        ),
        "retrospective_sustained_of_eligible": _persistence(cards),
    }


def _quartile_edges(values: list[int]) -> list[int]:
    ordered = sorted(values)
    return [ordered[len(ordered) * step // 4] for step in (1, 2, 3)]


def study() -> dict[str, object]:
    files = development_event_files(development_ids())
    fired: dict[str, list[Fired]] = defaultdict(list)
    team_entries: dict[tuple[int, int], int] = {}

    for match_id, path in sorted(files.items()):
        events = load_events(path, MatchId(match_id))
        by_id = {event.identifier: event for event in events}
        entries = [event for event in events if is_final_third_entry(event)]
        for team_id in {int(event.team.identifier) for event in events}:
            team_entries[(match_id, team_id)] = sum(
                1 for entry in entries if int(entry.team.identifier) == team_id
            )
        for name, settings in VARIANTS.items():
            for card in replay(events, AttackingSideShiftDetector(settings)):
                fired[name].append(_fired(match_id, card, by_id[card.trigger_event_id], entries))

    matches = len(files)
    result: dict[str, object] = {
        "development_matches": matches,
        "variants": {name: _summary(cards, matches) for name, cards in fired.items()},
    }
    comparisons: dict[str, object] = {}
    for name, cards in fired.items():
        if name == "current":
            continue
        pairs, lost, new = _pair(fired["current"], cards)
        delays = [later.seconds - earlier.seconds for earlier, later in pairs]
        comparisons[name] = {
            "paired_with_a_current_card": len(pairs),
            "same_second": sum(delay == 0 for delay in delays),
            "later": sum(delay > 0 for delay in delays),
            "earlier": sum(delay < 0 for delay in delays),
            "median_delay_of_later_cards_seconds": median(
                [delay for delay in delays if delay > 0] or [0]
            ),
            "later_by_more_than_120s": sum(delay > 120 for delay in delays),
            "current_cards_without_a_counterpart": len(lost),
            "lost_that_were_other_team_triggers": sum(card.other_team_trigger for card in lost),
            "lost_that_were_over_180s_since_own_entry": sum(
                1
                for card in lost
                if card.seconds_since_own_entry is None
                or card.seconds_since_own_entry > STALE_SECONDS
            ),
            "variant_cards_without_a_counterpart": len(new),
            "retrospective_sustained_of_eligible_lost": _persistence(lost),
            "retrospective_sustained_of_eligible_kept_current": _persistence(
                [earlier for earlier, _ in pairs]
            ),
        }
    result["comparisons_with_current"] = comparisons

    # Coverage by entry volume: which team performances ever get a card?
    carded = Counter((card.match_id, card.team_id) for card in fired["current"])
    edges = _quartile_edges(list(team_entries.values()))
    quartiles: dict[str, dict[str, int]] = {}
    for key, count in team_entries.items():
        quartile = sum(count > edge for edge in edges) + 1
        row = quartiles.setdefault(
            f"Q{quartile}", {"team_matches": 0, "with_a_card": 0, "cards": 0}
        )
        row["team_matches"] += 1
        row["with_a_card"] += carded[key] > 0
        row["cards"] += carded[key]
    teams_carded_per_match = Counter(
        sum(1 for (match, _), cards in carded.items() if match == match_id and cards)
        for match_id in files
    )
    result["coverage_by_entry_quartile"] = {
        "quartile_upper_edges_in_entries": edges,
        "quartiles": dict(sorted(quartiles.items())),
        "matches_by_number_of_teams_with_a_card": dict(sorted(teams_carded_per_match.items())),
    }
    return result


if __name__ == "__main__":
    print(json.dumps(study(), indent=2))
