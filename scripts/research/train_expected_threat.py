"""Fit a 16-by-12 expected-threat grid from development warehouse counts only."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from territory_threat import provenance

from regista.valuation.expected_threat import (
    CellCounts,
    ExpectedThreatSurface,
    TransitionCount,
)
from regista.warehouse.research import connect_research

WAREHOUSE = Path("data/warehouse/regista.duckdb")
OUTPUT = Path("out/valuation/expected-threat.json")
COLUMNS = 16
ROWS = 12

# Both pass attempts (successful or not) and carries enter the move decision.
# Only completed moves enter a transition. Non-open-play actions, shootouts, and
# coordinates outside the verified pitch are excluded. This differs deliberately
# from socceraction's SPADL action set; compare equations on matched inputs.
BASE_SQL = """
WITH eligible AS (
    SELECT *,
        least(floor(x / 120.0 * 16)::INTEGER, 15)
            + 16 * least(floor(y / 80.0 * 12)::INTEGER, 11) AS start_cell,
        least(floor(end_x / 120.0 * 16)::INTEGER, 15)
            + 16 * least(floor(end_y / 80.0 * 12)::INTEGER, 11) AS end_cell
    FROM analytical.event_context AS events
    JOIN normalized.matches AS matches USING (match_id)
    WHERE matches.match_date < ? AND period BETWEEN 1 AND 4 AND open_play
        AND x BETWEEN 0 AND 120 AND y BETWEEN 0 AND 80
        AND (event_type = 'shot' OR (
            event_type IN ('pass', 'carry')
            AND end_x BETWEEN 0 AND 120 AND end_y BETWEEN 0 AND 80
        ))
)
"""

COUNTS_SQL = (
    BASE_SQL
    + """
SELECT start_cell,
    count(*) FILTER (WHERE event_type = 'shot') AS shots,
    count(*) FILTER (WHERE event_type = 'shot' AND scores_goal) AS goals,
    count(*) FILTER (WHERE event_type IN ('pass', 'carry')) AS moves
FROM eligible GROUP BY start_cell ORDER BY start_cell
"""
)

TRANSITIONS_SQL = (
    BASE_SQL
    + """
SELECT start_cell, end_cell, count(*) AS completed_moves
FROM eligible WHERE event_type IN ('pass', 'carry') AND completed
GROUP BY ALL ORDER BY ALL
"""
)

CANDIDATE_SQL = """
SELECT count(*) FILTER (WHERE event_type = 'shot') AS shots,
    count(*) FILTER (WHERE event_type IN ('pass', 'carry')) AS moves
FROM analytical.event_context AS events
JOIN normalized.matches AS matches USING (match_id)
WHERE matches.match_date < ? AND period BETWEEN 1 AND 4 AND open_play
    AND event_type IN ('shot', 'pass', 'carry')
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--before-date",
        type=date.fromisoformat,
        help="train only on matches dated strictly before YYYY-MM-DD",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT)
    arguments = parser.parse_args()
    cutoff: date = arguments.before_date or date.max
    with connect_research(WAREHOUSE) as connection:
        source = provenance(connection)
        match_count = connection.execute(
            "SELECT count(*) FROM normalized.matches WHERE match_date < ?", [cutoff]
        ).fetchone()
        assert match_count is not None
        selected_matches = int(match_count[0])
        if selected_matches == 0:
            parser.error("no development matches precede the requested date")
        candidates = connection.execute(CANDIDATE_SQL, [cutoff]).fetchone()
        assert candidates is not None
        counts = [
            CellCounts(int(cell), int(shots), int(goals), int(moves))
            for cell, shots, goals, moves in connection.execute(COUNTS_SQL, [cutoff]).fetchall()
        ]
        transitions = [
            TransitionCount(int(start), int(end), int(amount))
            for start, end, amount in connection.execute(TRANSITIONS_SQL, [cutoff]).fetchall()
        ]
    surface = ExpectedThreatSurface.fit(counts, transitions, columns=COLUMNS, rows=ROWS)
    shots = sum(row.shots for row in counts)
    goals = sum(row.goals for row in counts)
    moves = sum(row.move_attempts for row in counts)
    completed = sum(row.completed_moves for row in transitions)
    result = {
        "schema_version": 1,
        "source": "StatsBomb Open Data",
        "provenance": source,
        "training_matches": selected_matches,
        "training_before_date": (
            arguments.before_date.isoformat() if arguments.before_date else None
        ),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "columns": surface.columns,
        "rows": surface.rows,
        "training_counts": {
            "open_play_shots": shots,
            "open_play_goals": goals,
            "move_attempts": moves,
            "completed_moves": completed,
            "shot_coordinate_exclusions": int(candidates[0]) - shots,
            "move_coordinate_exclusions": int(candidates[1]) - moves,
        },
        "solver": {"iterations": surface.iterations, "residual": surface.residual},
        "values": list(surface.values),
    }
    output: Path = arguments.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"Fitted {COLUMNS}x{ROWS} xT grid from {shots:,} shots and {moves:,} move attempts; "
        f"{surface.iterations} iterations. Result: {output}"
    )


if __name__ == "__main__":
    main()
