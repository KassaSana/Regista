"""Compare each 10-minute spell with earlier complete spells in the same match.

Retrospective development-only research for note 06. Provider possession groups
are used only to attribute shots after entries for this retrospective check.
They are never an input to an in-match detector.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from territory_threat import Window, load_windows, provenance, quantile, spearman_with_interval

from regista.warehouse.research import connect_research

WAREHOUSE = Path("data/warehouse/regista.duckdb")
OUTPUT = Path("out/research/06-territory-earlier-match.json")
WINDOW_SECONDS = 600
SEED = 20260928

STATE_SQL = """
WITH first_event AS (
    SELECT match_id, period, floor(period_seconds / $length)::INTEGER AS window_index,
        arg_min(home_score_before, sequence) AS home_before,
        arg_min(away_score_before, sequence) AS away_before
    FROM analytical.score_states
    WHERE period IN (1, 2)
    GROUP BY ALL
)
SELECT f.match_id, t.team_id, f.period, f.window_index,
    CASE sign(CASE WHEN t.is_home THEN f.home_before - f.away_before
        ELSE f.away_before - f.home_before END)
        WHEN 1 THEN 'leading' WHEN 0 THEN 'level' ELSE 'trailing' END AS state
FROM first_event AS f
JOIN analytical.team_matches AS t USING (match_id)
"""

# A shot is attributed only if an earlier open-play final-third entry by the
# shooting team occurred in the same provider possession and 10-minute window.
# Possession is a hindsight field, so this is an evaluation diagnostic only.
ATTRIBUTED_SQL = """
SELECT shot.match_id, shot.team_id, shot.period,
    floor(shot.period_seconds / $length)::INTEGER AS window_index,
    count(*) AS shots, coalesce(sum(shot.provider_xg), 0)::DOUBLE AS xg
FROM analytical.event_context AS shot
JOIN normalized.events AS source ON source.event_id = shot.event_id
WHERE shot.period IN (1, 2) AND shot.event_type = 'shot'
    AND shot.shot_type = 'Open Play' AND shot.provider_xg IS NOT NULL
    AND EXISTS (
        SELECT 1 FROM analytical.final_third_entries AS entry
        JOIN normalized.events AS entry_source ON entry_source.event_id = entry.event_id
        WHERE entry.match_id = shot.match_id AND entry.team_id = shot.team_id
            AND entry.period = shot.period AND entry.sequence < shot.sequence
            AND entry_source.possession = source.possession
            AND floor(entry.period_seconds / $length)::INTEGER
                = floor(shot.period_seconds / $length)::INTEGER
    )
GROUP BY ALL
"""


@dataclass(frozen=True)
class Comparison:
    window: Window
    prior_windows: int
    entry_excess: float
    shot_excess: float
    xg_excess: float
    attributed_xg: float
    state_before: str


def comparisons(
    windows: list[Window],
    states: dict[tuple[int, int, int, int], str],
    attributed: dict[tuple[int, int, int, int], float],
) -> list[Comparison]:
    by_team_match: dict[tuple[int, int], list[Window]] = defaultdict(list)
    for window in windows:
        if window.complete:
            by_team_match[(window.match_id, window.team_id)].append(window)
    result: list[Comparison] = []
    for group in by_team_match.values():
        group.sort(key=lambda window: (window.period, window.index))
        for position, window in enumerate(group):
            # A single previous window is too thin a baseline. All earlier
            # complete windows are available at this window's end.
            if position < 2 or window.xg is None:
                continue
            earlier = group[:position]
            if any(prior.xg is None for prior in earlier):
                continue
            key = (window.match_id, window.team_id, window.period, window.index)
            state = states.get(key)
            if state is None:
                raise ValueError(f"missing score state for {key}")
            result.append(
                Comparison(
                    window,
                    position,
                    window.entries - statistics.fmean(prior.entries for prior in earlier),
                    window.shots - statistics.fmean(prior.shots for prior in earlier),
                    window.xg - statistics.fmean(cast(float, prior.xg) for prior in earlier),
                    attributed.get(key, 0.0),
                    state,
                )
            )
    return result


def correlations(rows: list[Comparison], seed: int) -> dict[str, object]:
    clusters = [row.window.match_id for row in rows]
    excess = [row.entry_excess for row in rows]
    return {
        "shots": spearman_with_interval(clusters, excess, [row.shot_excess for row in rows], seed),
        "xg": spearman_with_interval(clusters, excess, [row.xg_excess for row in rows], seed + 1),
    }


def bin_summary(rows: list[Comparison]) -> list[dict[str, object]]:
    cuts = [quantile([row.entry_excess for row in rows], part) for part in (0.2, 0.4, 0.6, 0.8)]
    result: list[dict[str, object]] = []
    for index in range(5):
        group = [row for row in rows if sum(row.entry_excess > cut for cut in cuts) == index]
        if not group:
            continue
        entries = sum(row.window.entries for row in group)
        result.append(
            {
                "entry_excess_range": [
                    min(row.entry_excess for row in group),
                    max(row.entry_excess for row in group),
                ],
                "windows": len(group),
                "matches": len({row.window.match_id for row in group}),
                "mean_entry_excess": statistics.fmean(row.entry_excess for row in group),
                "mean_shot_excess": statistics.fmean(row.shot_excess for row in group),
                "mean_xg_excess": statistics.fmean(row.xg_excess for row in group),
                "no_shot_share": sum(row.window.shots == 0 for row in group) / len(group),
                "all_xg_per_entry": sum(cast(float, row.window.xg) for row in group) / entries,
                "attributed_xg_per_entry": sum(row.attributed_xg for row in group) / entries,
            }
        )
    return result


def main() -> None:
    with connect_research(WAREHOUSE) as connection:
        source = provenance(connection)
        windows = load_windows(connection, WINDOW_SECONDS)
        states = {
            (int(match), int(team), int(period), int(index)): str(state)
            for match, team, period, index, state in connection.execute(
                STATE_SQL, {"length": WINDOW_SECONDS}
            ).fetchall()
        }
        attributed = {
            (int(match), int(team), int(period), int(index)): float(xg)
            for match, team, period, index, _, xg in connection.execute(
                ATTRIBUTED_SQL, {"length": WINDOW_SECONDS}
            ).fetchall()
        }
    rows = comparisons(windows, states, attributed)
    if not rows or any(row.attributed_xg > cast(float, row.window.xg) + 1e-9 for row in rows):
        raise ValueError("attributed open-play xG exceeds all-shot xG or no windows survived")
    results: dict[str, Any] = {
        "provenance": source,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "window_minutes": WINDOW_SECONDS // 60,
        "minimum_prior_complete_windows": 2,
        "windows": len(rows),
        "matches": len({row.window.match_id for row in rows}),
        "overall": correlations(rows, SEED),
        "by_score_state_before_window": {
            state: {"windows": len(group), "correlations": correlations(group, SEED + offset)}
            for offset, state in enumerate(("level", "leading", "trailing"), 1)
            if (group := [row for row in rows if row.state_before == state])
        },
        "goal_free_window": correlations(
            [row for row in rows if row.window.goals_for + row.window.goals_against == 0],
            SEED + 4,
        ),
        "entry_excess_bins": bin_summary(rows),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
