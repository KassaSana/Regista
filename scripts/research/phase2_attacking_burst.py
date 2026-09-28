"""Study the attacking burst detector on acquired development matches only.

Run: ``uv run python scripts/research/phase2_attacking_burst.py``.
Sweeps burst thresholds through the production detector, compares coverage by
entry volume with the side-shift detector, and replays a seeded reference in
which each team's shots are spread uniformly over the playing time seen. The
output is aggregate JSON: no provider records and no fan judgments.
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from fractions import Fraction
from itertools import pairwise
from typing import cast

from phase2_card_audit import development_event_files, development_ids

from regista.adapters.statsbomb.events import load_events
from regista.detectors.attacking_burst import (
    AttackingBurstDetector,
    BurstSettings,
    counts_as_burst_shot,
)
from regista.detectors.attacking_side_shift import AttackingSideShiftDetector, SideShiftSettings
from regista.domain.entries import is_final_third_entry
from regista.domain.events import ActionType, Event, MatchClock, ShotDetail, Team
from regista.domain.ids import EventId, MatchId
from regista.domain.replay import replay

GRID = [
    (shots, ratio)
    for shots in (3, 4, 5)
    for ratio in (Fraction(1), Fraction(3, 2), Fraction(2), Fraction(3))
]
DEFAULT = BurstSettings()
SIDE_SHIFT = SideShiftSettings(fire_on_own_entry=True)
REFERENCE_SEEDS = 10
CLUSTER_SECONDS = 60


def _label(shots: int, ratio: Fraction) -> str:
    return f"shots>={shots},ratio>={ratio}"


def _quartile(count: int, edges: list[int]) -> str:
    return f"Q{sum(count > edge for edge in edges) + 1}"


def _is_goal(event: Event) -> bool:
    """Read the shot outcome from the kept provider record (research only)."""
    shot = event.provider_record.get("shot")
    if not isinstance(shot, dict):
        return False
    outcome = cast(dict[str, object], shot).get("outcome")
    return isinstance(outcome, dict) and cast(dict[str, object], outcome).get("name") == "Goal"


def _periods(events: list[Event]) -> dict[int, tuple[int, int]]:
    spans: dict[int, tuple[int, int]] = {}
    for event in events:
        seconds = event.clock.elapsed_seconds
        start, latest = spans.get(event.clock.period, (seconds, seconds))
        spans[event.clock.period] = (start, max(latest, seconds))
    return spans


def _reference_stream(
    team: Team, shots: int, spans: dict[int, tuple[int, int]], generator: random.Random
) -> list[Event]:
    """Spread a team's counted shots uniformly over the playing time seen."""
    periods = [period for period in sorted(spans) if spans[period][1] > spans[period][0]]
    weights = [spans[period][1] - spans[period][0] for period in periods]
    placed: list[tuple[int, int, ActionType]] = []
    for period in periods:
        start, end = spans[period]
        placed += [(period, start, ActionType.OTHER), (period, end, ActionType.OTHER)]
    for _ in range(shots):
        period = generator.choices(periods, weights)[0]
        start, end = spans[period]
        placed.append((period, generator.randint(start, end), ActionType.SHOT))
    placed.sort(key=lambda item: (item[0], item[1], item[2] is ActionType.SHOT))
    return [
        Event(
            identifier=EventId(f"reference-{sequence}"),
            sequence=sequence,
            match_id=MatchId(0),
            clock=MatchClock(period, *divmod(seconds, 60)),
            team=team,
            action=action,
            location=None,
            movement=None,
            source="reference",
            provider_record={},
            shot=ShotDetail(penalty=False) if action is ActionType.SHOT else None,
        )
        for sequence, (period, seconds, action) in enumerate(placed, start=1)
    ]


def study() -> dict[str, object]:
    files = development_event_files(development_ids())
    generator = random.Random(20260928)
    team_entries: dict[tuple[int, int], int] = {}
    team_shots: dict[tuple[int, int], int] = {}
    burst_cards: dict[str, Counter[tuple[int, int]]] = defaultdict(Counter)
    reference_cards: Counter[str] = Counter()
    side_shift_cards: Counter[tuple[int, int]] = Counter()
    default_recent_shots: Counter[int] = Counter()
    default_goal_in_window = 0
    stream_per_match: Counter[int] = Counter()
    close_pairs = 0
    combined_teams: Counter[int] = Counter()

    for match_id, path in sorted(files.items()):
        events = load_events(path, MatchId(match_id))
        by_id = {event.identifier: event for event in events}
        spans = _periods(events)
        teams = {event.team.identifier: event.team for event in events}
        for team in teams.values():
            key = (match_id, int(team.identifier))
            team_entries[key] = sum(
                1
                for event in events
                if event.team.identifier == team.identifier and is_final_third_entry(event)
            )
            team_shots[key] = sum(
                1
                for event in events
                if event.team.identifier == team.identifier and counts_as_burst_shot(event)
            )
            for _ in range(REFERENCE_SEEDS):
                stream = _reference_stream(team, team_shots[key], spans, generator)
                for shots, ratio in GRID:
                    settings = BurstSettings(minimum_recent_shots=shots, minimum_rate_ratio=ratio)
                    reference_cards[_label(shots, ratio)] += len(
                        list(replay(stream, AttackingBurstDetector(settings)))
                    )

        for shots, ratio in GRID:
            settings = BurstSettings(minimum_recent_shots=shots, minimum_rate_ratio=ratio)
            for card in replay(events, AttackingBurstDetector(settings)):
                burst_cards[_label(shots, ratio)][(match_id, int(card.team.identifier))] += 1

        # The combined stream at the default settings.
        timeline: list[tuple[int, int, int]] = []
        for card in replay(events, AttackingBurstDetector(DEFAULT)):
            default_recent_shots[len(card.recent_shot_ids)] += 1
            default_goal_in_window += any(
                _is_goal(by_id[identifier]) for identifier in card.recent_shot_ids
            )
            timeline.append((card.fired_at.period, card.fired_at.elapsed_seconds, 0))
        for card in replay(events, AttackingSideShiftDetector(SIDE_SHIFT)):
            side_shift_cards[(match_id, int(card.team.identifier))] += 1
            timeline.append((card.fired_at.period, card.fired_at.elapsed_seconds, 1))
        timeline.sort()
        stream_per_match[len(timeline)] += 1
        close_pairs += sum(
            1
            for earlier, later in pairwise(timeline)
            if earlier[0] == later[0] and later[1] - earlier[1] <= CLUSTER_SECONDS
        )
        default_label = _label(DEFAULT.minimum_recent_shots, DEFAULT.minimum_rate_ratio)
        combined_teams[
            sum(
                1
                for team in teams
                if burst_cards[default_label][(match_id, int(team))]
                or side_shift_cards[(match_id, int(team))]
            )
        ] += 1

    ordered = sorted(team_entries.values())
    edges = [ordered[len(ordered) * step // 4] for step in (1, 2, 3)]
    team_matches = len(team_entries)
    sweep: dict[str, object] = {}
    for shots, ratio in GRID:
        label = _label(shots, ratio)
        cards = burst_cards[label]
        by_quartile: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for key, count in team_entries.items():
            row = by_quartile[_quartile(count, edges)]
            row[0] += 1
            row[1] += cards[key] > 0
        sweep[label] = {
            "cards": sum(cards.values()),
            "cards_per_match": round(sum(cards.values()) / len(files), 3),
            "team_matches_with_a_card": sum(1 for count in cards.values() if count),
            "reference_cards_per_match": round(
                reference_cards[label] / (REFERENCE_SEEDS * len(files)), 3
            ),
            "team_matches_with_a_card_by_entry_quartile": {
                quartile: f"{row[1]}/{row[0]}" for quartile, row in sorted(by_quartile.items())
            },
        }
    side_by_quartile: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for key, count in team_entries.items():
        row = side_by_quartile[_quartile(count, edges)]
        row[0] += 1
        row[1] += side_shift_cards[key] > 0
    shots_by_quartile: dict[str, list[int]] = defaultdict(list)
    for key, count in team_entries.items():
        shots_by_quartile[_quartile(count, edges)].append(team_shots[key])
    return {
        "development_matches": len(files),
        "team_matches": team_matches,
        "entry_quartile_upper_edges": edges,
        "mean_counted_shots_by_entry_quartile": {
            quartile: round(sum(values) / len(values), 2)
            for quartile, values in sorted(shots_by_quartile.items())
        },
        "burst_sweep": sweep,
        "side_shift_own_entry_team_matches_with_a_card_by_entry_quartile": {
            quartile: f"{row[1]}/{row[0]}" for quartile, row in sorted(side_by_quartile.items())
        },
        "default_burst_recent_shot_counts": dict(sorted(default_recent_shots.items())),
        "default_burst_cards_with_a_goal_in_window": default_goal_in_window,
        "combined_stream_cards_per_match": dict(sorted(stream_per_match.items())),
        "combined_stream_adjacent_cards_within_60s": close_pairs,
        "combined_matches_by_number_of_teams_with_a_card": dict(sorted(combined_teams.items())),
    }


if __name__ == "__main__":
    print(json.dumps(study(), indent=2))
