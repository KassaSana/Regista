"""Summarize recovery location and movement directness on development data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from territory_threat import provenance

from regista.warehouse.research import connect_research

WAREHOUSE = Path("data/warehouse/regista.duckdb")


@dataclass(frozen=True)
class TeamMetrics:
    match_id: int
    team_id: int
    recovery_events: int
    valid_recoveries: int
    median_recovery_x: float | None
    attacking_third_recoveries: int
    completed_open_play_moves: int
    valid_moves: int
    directness: float | None


TEAM_METRICS_SQL = """
WITH eligible AS (
    SELECT match_id, team_id, event_type, x, y, end_x, end_y,
        completed, open_play,
        event_type = 'ball_recovery' AS recovery,
        event_type IN ('pass', 'carry') AND completed AND open_play AS movement,
        x BETWEEN 0 AND 120 AND y BETWEEN 0 AND 80 AS valid_start,
        end_x BETWEEN 0 AND 120 AND end_y BETWEEN 0 AND 80 AS valid_end
    FROM analytical.event_context
    WHERE period BETWEEN 1 AND 4
), grouped AS (
    SELECT team.match_id, team.team_id,
        count(*) FILTER (WHERE event.recovery) AS recovery_events,
        count(*) FILTER (WHERE event.recovery AND event.valid_start) AS valid_recoveries,
        median(event.x) FILTER (
            WHERE event.recovery AND event.valid_start
        ) AS median_recovery_x,
        count(*) FILTER (
            WHERE event.recovery AND event.valid_start AND event.x >= 80
        ) AS attacking_third_recoveries,
        count(*) FILTER (WHERE event.movement) AS completed_open_play_moves,
        count(*) FILTER (
            WHERE event.movement AND event.valid_start AND event.valid_end
        ) AS valid_moves,
        sum(greatest(event.end_x - event.x, 0)) FILTER (
            WHERE event.movement AND event.valid_start AND event.valid_end
        ) AS positive_x_distance,
        sum(sqrt(power(event.end_x - event.x, 2) + power(event.end_y - event.y, 2)))
            FILTER (WHERE event.movement AND event.valid_start AND event.valid_end)
            AS movement_distance
    FROM analytical.team_matches AS team
    LEFT JOIN eligible AS event USING (match_id, team_id)
    GROUP BY team.match_id, team.team_id
)
SELECT *, CASE WHEN movement_distance > 0
    THEN 100 * positive_x_distance / movement_distance END AS directness
FROM grouped ORDER BY match_id, team_id
"""


def summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "minimum": None, "median": None, "maximum": None}
    return {
        "count": len(values),
        "minimum": round(min(values), 4),
        "median": round(median(values), 4),
        "maximum": round(max(values), 4),
    }


def main() -> None:
    with connect_research(WAREHOUSE) as connection:
        source = provenance(connection)
        rows = connection.execute(TEAM_METRICS_SQL).fetchall()
    records = [
        TeamMetrics(
            match_id=int(row[0]),
            team_id=int(row[1]),
            recovery_events=int(row[2]),
            valid_recoveries=int(row[3]),
            median_recovery_x=None if row[4] is None else float(row[4]),
            attacking_third_recoveries=int(row[5]),
            completed_open_play_moves=int(row[6]),
            valid_moves=int(row[7]),
            directness=None if row[10] is None else float(row[10]),
        )
        for row in rows
    ]
    qualified = [row for row in records if row.valid_recoveries >= 10 and row.valid_moves >= 100]
    result: dict[str, object] = {
        "provenance": source,
        "definitions": {
            "recovery_location": "median x of valid Ball Recovery events in periods 1-4",
            "directness": "100 * sum(max(end_x - x, 0)) / sum(movement Euclidean distance) "
            "for completed open-play passes and carries with valid coordinates",
            "qualification": "at least 10 valid recoveries and 100 valid moves per team-match",
        },
        "team_matches": len(records),
        "qualified_team_matches": len(qualified),
        "recovery_events": sum(row.recovery_events for row in records),
        "invalid_recovery_coordinates": sum(
            row.recovery_events - row.valid_recoveries for row in records
        ),
        "completed_open_play_moves": sum(row.completed_open_play_moves for row in records),
        "invalid_move_coordinates": sum(
            row.completed_open_play_moves - row.valid_moves for row in records
        ),
        "qualified_median_recovery_x": summary(
            [row.median_recovery_x for row in qualified if row.median_recovery_x is not None]
        ),
        "qualified_directness": summary(
            [row.directness for row in qualified if row.directness is not None]
        ),
        "qualified_attacking_third_recovery_share": summary(
            [row.attacking_third_recoveries / row.valid_recoveries for row in qualified]
        ),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
