"""Study a score-against-chance-quality observation on development matches only.

Run: ``uv run python scripts/research/phase2_chance_quality.py``.
Replays each match in provider order. After every shot or own goal it compares
the teams' cumulative non-penalty provider xG with the current score. A
candidate fires when one team's xG leads by at least a margin while that team
is not ahead, at most once per team per score state. Output is aggregate JSON
plus a few development examples: no provider records and no fan judgments.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import median
from typing import cast

from phase2_card_audit import development_event_files, development_ids

from regista.adapters.statsbomb.events import load_events
from regista.domain.events import ActionType, Event
from regista.domain.ids import MatchId

MARGINS = (0.75, 1.0, 1.25, 1.5)
DEFAULT_MARGIN = 1.0
BIG_CHANCE_XG = 0.5
EXAMPLES = 6


@dataclass(frozen=True, slots=True)
class Candidate:
    """One firing: the team whose chances are better while it is not ahead."""

    match_id: int
    period: int
    minute: int
    second: int
    team: str
    opponent: str
    goals_for: int
    goals_against: int
    xg_for: float
    xg_against: float
    shots_for: int
    shots_against: int
    largest_shot_share: float
    gap_with_penalties: float
    trigger_sequence: int


def _record(event: Event, key: str) -> dict[str, object]:
    value = event.provider_record.get(key)
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def type_name(event: Event) -> str:
    return str(_record(event, "type").get("name"))


def shot_xg(event: Event) -> float:
    value = _record(event, "shot").get("statsbomb_xg")
    if not isinstance(value, int | float):
        raise ValueError(f"shot {event.identifier} has no provider xG")
    return float(value)


def shot_outcome(event: Event) -> str | None:
    outcome = _record(event, "shot").get("outcome")
    return str(cast(dict[str, object], outcome).get("name")) if isinstance(outcome, dict) else None


def replay_match(match_id: int, events: list[Event], margin: float) -> list[Candidate]:
    """Fire at most once per team and score state, reading only events seen so far."""
    teams = list(dict.fromkeys(event.team.name for event in events))
    goals: Counter[str] = Counter()
    xg: defaultdict[str, float] = defaultdict(float)
    xg_with_penalties: defaultdict[str, float] = defaultdict(float)
    shots: Counter[str] = Counter()
    shot_values: defaultdict[str, list[float]] = defaultdict(list)
    fired_states: set[tuple[str, int, int]] = set()
    candidates: list[Candidate] = []
    for event in events:
        if event.clock.period >= 5:  # penalty shootout
            break
        team = event.team.name
        changed = False
        if event.action is ActionType.SHOT and event.shot is not None:
            value = shot_xg(event)
            xg_with_penalties[team] += value
            if not event.shot.penalty:
                xg[team] += value
                shots[team] += 1
                shot_values[team].append(value)
            if shot_outcome(event) == "Goal":
                goals[team] += 1
            changed = True
        elif type_name(event) == "Own Goal For":
            goals[team] += 1
            changed = True
        if not changed or len(teams) != 2:
            continue
        for side in teams:
            other = teams[1] if side == teams[0] else teams[0]
            gap = xg[side] - xg[other]
            if gap < margin or goals[side] > goals[other]:
                continue
            state = (side, goals[side], goals[other])
            if state in fired_states:
                continue
            fired_states.add(state)
            candidates.append(
                Candidate(
                    match_id=match_id,
                    period=event.clock.period,
                    minute=event.clock.minute,
                    second=event.clock.second,
                    team=side,
                    opponent=other,
                    goals_for=goals[side],
                    goals_against=goals[other],
                    xg_for=round(xg[side], 2),
                    xg_against=round(xg[other], 2),
                    shots_for=shots[side],
                    shots_against=shots[other],
                    largest_shot_share=max(shot_values[side]) / xg[side],
                    gap_with_penalties=xg_with_penalties[side] - xg_with_penalties[other],
                    trigger_sequence=event.sequence,
                )
            )
    return candidates


def _summary(candidates: list[Candidate], matches: int) -> dict[str, object]:
    per_match = Counter(candidate.match_id for candidate in candidates)
    distribution = Counter(per_match.values())
    distribution[0] = matches - len(per_match)
    minutes = [candidate.minute for candidate in candidates]
    return {
        "candidates": len(candidates),
        "matches_with_a_candidate": len(per_match),
        "candidates_per_match": dict(sorted(distribution.items())),
        "trailing": sum(c.goals_for < c.goals_against for c in candidates),
        "level": sum(c.goals_for == c.goals_against for c in candidates),
        "median_minute": median(minutes) if minutes else None,
        "before_minute_30": sum(minute < 30 for minute in minutes),
        "not_more_shots_than_opponent": sum(c.shots_for <= c.shots_against for c in candidates),
        # Obviousness proxies: similar shot counts, and far better chances per shot.
        "shots_within_25_percent_of_opponent": sum(
            c.shots_for <= 1.25 * c.shots_against for c in candidates
        ),
        "xg_per_shot_at_least_1_5_times_opponent": sum(
            c.shots_against == 0
            or (c.xg_for / c.shots_for) >= 1.5 * (c.xg_against / c.shots_against)
            for c in candidates
        ),
        "first_half": sum(c.period == 1 for c in candidates),
        "one_shot_is_over_half_the_xg": sum(c.largest_shot_share > 0.5 for c in candidates),
        "still_at_margin_with_penalties_included": sum(
            c.gap_with_penalties >= DEFAULT_MARGIN for c in candidates
        ),
    }


def study() -> dict[str, object]:
    files = development_event_files(development_ids())
    by_margin: dict[float, list[Candidate]] = {margin: [] for margin in MARGINS}
    final_goals: dict[str, int] = {}
    for match_id, path in sorted(files.items()):
        events = load_events(path, MatchId(match_id))
        final_goals[str(match_id)] = sum(
            1
            for event in events
            if event.clock.period < 5
            and (
                (event.action is ActionType.SHOT and shot_outcome(event) == "Goal")
                or type_name(event) == "Own Goal For"
            )
        )
        for margin in MARGINS:
            by_margin[margin] += replay_match(match_id, events, margin)
    default = by_margin[DEFAULT_MARGIN]
    examples = sorted(
        (c for c in default if c.shots_for <= c.shots_against and c.largest_shot_share <= 0.5),
        key=lambda c: (c.match_id, c.period, c.minute),
    )[:EXAMPLES]
    return {
        "development_matches": len(files),
        "final_goals_counted": final_goals,
        "rule": (
            "after each shot or own goal: team non-penalty xG - opponent >= margin, team not "
            "ahead; at most once per team and score state; shootouts excluded"
        ),
        "by_margin": {
            str(margin): _summary(candidates, len(files))
            for margin, candidates in by_margin.items()
        },
        "examples_margin_1_not_more_shots_and_no_dominant_chance": [
            {
                "match_id": c.match_id,
                "period": c.period,
                "clock": f"{c.minute:02d}:{c.second:02d}",
                "team": c.team,
                "opponent": c.opponent,
                "score": f"{c.goals_for}-{c.goals_against}",
                "xg": f"{c.xg_for} to {c.xg_against}",
                "shots": f"{c.shots_for} to {c.shots_against}",
            }
            for c in examples
        ],
    }


if __name__ == "__main__":
    print(json.dumps(study(), indent=2))
