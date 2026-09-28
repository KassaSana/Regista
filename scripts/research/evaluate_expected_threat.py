"""Compare earlier-trained spatial values on later development matches only."""

from __future__ import annotations

import argparse
import json
from bisect import bisect_right
from collections import defaultdict
from datetime import date
from math import hypot
from pathlib import Path
from statistics import median

from regista.domain.geometry import Pitch, Point
from regista.valuation.evaluation import area_under_curve
from regista.valuation.expected_threat import ExpectedThreatSurface
from regista.warehouse.research import connect_research

WAREHOUSE = Path("data/warehouse/regista.duckdb")
DEFAULT_MODEL = Path("out/valuation/expected-threat-before-2023.json")

EVENTS_SQL = """
SELECT events.match_id, events.possession, events.team_id, context.sequence,
    context.event_type, context.completed, context.open_play,
    context.end_x, context.end_y, context.scores_goal
FROM analytical.event_context AS context
JOIN normalized.events AS events USING (match_id, event_id)
JOIN normalized.matches AS matches USING (match_id)
WHERE matches.match_date >= ? AND context.period BETWEEN 1 AND 4
    AND context.event_type IN ('pass', 'carry', 'shot')
ORDER BY events.match_id, context.sequence
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    arguments = parser.parse_args()
    model = json.loads(arguments.model.read_text(encoding="utf-8"))
    if model.get("schema_version") != 1 or model.get("training_before_date") is None:
        parser.error("evaluation requires a date-limited version-one model")
    cutoff = date.fromisoformat(model["training_before_date"])
    surface = ExpectedThreatSurface(
        model["columns"],
        model["rows"],
        tuple(model["values"]),
        model["solver"]["iterations"],
        model["solver"]["residual"],
    )
    pitch = Pitch()
    maximum_distance = hypot(pitch.length, pitch.width / 2)

    # Provider possession grouping is hindsight and used here solely to define
    # retrospective outcomes. It is never an input to an in-match value.
    shots: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    goals: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    moves: list[tuple[int, int, int, int, float, float]] = []
    matches: set[int] = set()
    with connect_research(WAREHOUSE) as connection:
        rows = connection.execute(EVENTS_SQL, [cutoff]).fetchall()
    for (
        match_id,
        possession,
        team_id,
        sequence,
        action,
        completed,
        open_play,
        end_x,
        end_y,
        scores_goal,
    ) in rows:
        matches.add(int(match_id))
        key = (int(match_id), int(possession), int(team_id))
        if action == "shot" and open_play:
            shots[key].append(int(sequence))
            if scores_goal:
                goals[key].append(int(sequence))
        elif (
            action in ("pass", "carry")
            and completed
            and open_play
            and end_x is not None
            and end_y is not None
            and 0 <= end_x <= pitch.length
            and 0 <= end_y <= pitch.width
        ):
            moves.append((*key, int(sequence), float(end_x), float(end_y)))

    expected_scores: list[float] = []
    heuristic_scores: list[float] = []
    shot_targets: list[bool] = []
    goal_targets: list[bool] = []
    match_indices: dict[int, list[int]] = defaultdict(list)
    for match_id, possession, team_id, sequence, x, y in moves:
        key = (match_id, possession, team_id)
        point = Point(x, y)
        expected_scores.append(surface.at(point))
        heuristic_scores.append(1 - pitch.distance_to_opponent_goal(point) / maximum_distance)
        shot_targets.append(bisect_right(shots[key], sequence) < len(shots[key]))
        goal_targets.append(bisect_right(goals[key], sequence) < len(goals[key]))
        match_indices[match_id].append(len(expected_scores) - 1)

    def match_differences(targets: list[bool]) -> dict[str, object]:
        differences: list[float] = []
        for indices in match_indices.values():
            outcome = [targets[index] for index in indices]
            if not any(outcome) or all(outcome):
                continue
            expected = area_under_curve([expected_scores[index] for index in indices], outcome)
            heuristic = area_under_curve([heuristic_scores[index] for index in indices], outcome)
            differences.append(expected - heuristic)
        return {
            "evaluable_matches": len(differences),
            "expected_threat_better": sum(difference > 0 for difference in differences),
            "goal_distance_better": sum(difference < 0 for difference in differences),
            "tied": sum(difference == 0 for difference in differences),
            "median_auc_difference": median(differences) if differences else None,
        }

    result = {
        "model": str(arguments.model),
        "training_before_date": cutoff.isoformat(),
        "later_development_matches": len(matches),
        "completed_moves": len(moves),
        "future_same_possession_shots": sum(shot_targets),
        "future_same_possession_goals": sum(goal_targets),
        "shot_auc": {
            "expected_threat_end": area_under_curve(expected_scores, shot_targets),
            "goal_distance_end": area_under_curve(heuristic_scores, shot_targets),
        },
        "shot_match_comparison": match_differences(shot_targets),
        "goal_auc": {
            "expected_threat_end": area_under_curve(expected_scores, goal_targets),
            "goal_distance_end": area_under_curve(heuristic_scores, goal_targets),
        },
        "goal_match_comparison": match_differences(goal_targets),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
