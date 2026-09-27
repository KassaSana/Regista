"""Research note 05: does a spell with more territory also contain more attacking threat?

Retrospective research code, not a detector (see
``docs/research/05-territory-and-threat.md``). It reads only the development warehouse,
through the read-only research connection, and changes nothing.

Windows are non-overlapping, fixed-length slices of each regular-time half, starting at
the period's own zero: [0, L), [L, 2L), ... A window is complete when the period lasted
at least to its end. Only complete windows enter the primary analysis; the incomplete
tail of each half is described separately. Extra time and penalty shootouts are left out.

Run: ``uv run python scripts/research/territory_threat.py --window-minutes 10``.
A JSON copy of the printed results goes to ``out/research/05-territory-threat/``
(git-ignored).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from regista.warehouse.research import connect_research

WAREHOUSE = Path("data/warehouse/regista.duckdb")
OUTPUT = Path("out/research/05-territory-threat")
# The owner has not watched these yet; the note never lists them as examples.
PROBE_MATCHES = frozenset({265958, 3869420, 3869321})
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 20260927
TILT_MINIMUM_DENOMINATORS = (1, 5, 10, 20)
TEAM_MINIMUM_PAIRS = 30

WINDOWS_SQL = """
WITH grid AS (
    SELECT
        tm.match_id, tm.team_id, tm.team_name, tm.opponent_team_id,
        tm.competition_name || ' ' || tm.season_name AS competition_season,
        p.period, w.window_index,
        w.window_index * $length AS start_seconds,
        least((w.window_index + 1) * $length, p.end_seconds) AS end_seconds,
        (w.window_index + 1) * $length <= p.end_seconds AS complete
    FROM analytical.team_matches AS tm
    JOIN analytical.periods AS p ON p.match_id = tm.match_id AND p.period IN (1, 2)
    CROSS JOIN LATERAL generate_series(0, floor(p.end_seconds / $length)::INTEGER)
        AS w(window_index)
    WHERE w.window_index * $length < p.end_seconds
),
events AS (
    SELECT *, floor(period_seconds / $length)::INTEGER AS window_index
    FROM analytical.event_context
    WHERE period IN (1, 2)
),
team_counts AS (
    SELECT
        match_id, team_id, period, window_index,
        count(*) AS team_events,
        count(*) FILTER (
            WHERE event_type = 'pass' AND completed AND open_play AND x >= 80
        ) AS tilt_passes,
        count(*) FILTER (WHERE event_type = 'shot') AS shots,
        count(*) FILTER (WHERE event_type = 'shot' AND open_play) AS open_play_shots,
        count(*) FILTER (WHERE event_type = 'shot' AND provider_xg IS NULL) AS shots_missing_xg,
        sum(provider_xg) FILTER (WHERE event_type = 'shot') AS provider_xg,
        sum(provider_xg) FILTER (WHERE event_type = 'shot' AND shot_type <> 'Penalty')
            AS non_penalty_provider_xg,
        count(*) FILTER (WHERE scores_goal) AS goals
    FROM events
    GROUP BY ALL
),
entries AS (
    SELECT match_id, team_id, period, floor(period_seconds / $length)::INTEGER AS window_index,
        count(*) AS final_third_entries
    FROM analytical.final_third_entries
    WHERE period IN (1, 2)
    GROUP BY ALL
)
SELECT
    g.match_id, g.team_id, g.team_name, g.competition_season, g.period, g.window_index,
    g.start_seconds::DOUBLE, g.end_seconds::DOUBLE, g.complete,
    coalesce(own.team_events, 0) + coalesce(opponent.team_events, 0) AS match_events,
    coalesce(en.final_third_entries, 0) AS final_third_entries,
    coalesce(own.tilt_passes, 0) AS tilt_passes,
    coalesce(opponent.tilt_passes, 0) AS opponent_tilt_passes,
    coalesce(own.shots, 0) AS shots,
    coalesce(own.open_play_shots, 0) AS open_play_shots,
    coalesce(own.shots_missing_xg, 0) AS shots_missing_xg,
    -- Zero shots is a true zero xG. Any shot without a provider value makes the sum missing.
    CASE WHEN coalesce(own.shots, 0) = 0 THEN 0
        WHEN own.shots_missing_xg > 0 THEN NULL ELSE own.provider_xg END AS provider_xg,
    CASE WHEN coalesce(own.shots, 0) = 0 THEN 0
        WHEN own.shots_missing_xg > 0 THEN NULL
        ELSE coalesce(own.non_penalty_provider_xg, 0) END AS non_penalty_provider_xg,
    coalesce(own.goals, 0) AS goals_for,
    coalesce(opponent.goals, 0) AS goals_against
FROM grid AS g
LEFT JOIN team_counts AS own USING (match_id, team_id, period, window_index)
LEFT JOIN team_counts AS opponent
    ON opponent.match_id = g.match_id AND opponent.team_id = g.opponent_team_id
    AND opponent.period = g.period AND opponent.window_index = g.window_index
LEFT JOIN entries AS en USING (match_id, team_id, period, window_index)
ORDER BY g.match_id, g.team_id, g.period, g.window_index
"""


@dataclass(frozen=True)
class Window:
    match_id: int
    team_id: int
    team_name: str
    competition_season: str
    period: int
    index: int
    start_seconds: float
    end_seconds: float
    complete: bool
    match_events: int
    entries: int
    tilt_passes: int
    opponent_tilt_passes: int
    shots: int
    open_play_shots: int
    shots_missing_xg: int
    xg: float | None
    non_penalty_xg: float | None
    goals_for: int
    goals_against: int

    @property
    def tilt_denominator(self) -> int:
        return self.tilt_passes + self.opponent_tilt_passes

    @property
    def tilt_share(self) -> float | None:
        denominator = self.tilt_denominator
        return self.tilt_passes / denominator if denominator else None


@dataclass(frozen=True)
class Pair:
    """Two consecutive complete windows of one team in the same half."""

    before: Window
    after: Window

    @property
    def match_id(self) -> int:
        return self.after.match_id

    @property
    def entries_change(self) -> int:
        return self.after.entries - self.before.entries

    @property
    def shots_change(self) -> int:
        return self.after.shots - self.before.shots

    @property
    def xg_change(self) -> float | None:
        if self.after.xg is None or self.before.xg is None:
            return None
        return self.after.xg - self.before.xg

    @property
    def goal_free(self) -> bool:
        return all(w.goals_for + w.goals_against == 0 for w in (self.before, self.after))


def load_windows(connection: Any, length_seconds: int) -> list[Window]:
    rows = cast(
        list[tuple[Any, ...]],
        connection.execute(WINDOWS_SQL, {"length": length_seconds}).fetchall(),
    )

    def number(value: object) -> float | None:
        return None if value is None else float(cast(Decimal, value))

    return [
        Window(
            match_id=int(row[0]),
            team_id=int(row[1]),
            team_name=str(row[2]),
            competition_season=str(row[3]),
            period=int(row[4]),
            index=int(row[5]),
            start_seconds=float(row[6]),
            end_seconds=float(row[7]),
            complete=bool(row[8]),
            match_events=int(row[9]),
            entries=int(row[10]),
            tilt_passes=int(row[11]),
            opponent_tilt_passes=int(row[12]),
            shots=int(row[13]),
            open_play_shots=int(row[14]),
            shots_missing_xg=int(row[15]),
            xg=number(row[16]),
            non_penalty_xg=number(row[17]),
            goals_for=int(row[18]),
            goals_against=int(row[19]),
        )
        for row in rows
    ]


def ranks(values: Sequence[float]) -> list[float]:
    """Average ranks, so ties share a rank (as Spearman's coefficient requires)."""
    order = sorted(range(len(values)), key=lambda position: values[position])
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in order[start : end + 1]:
            result[position] = (start + end) / 2 + 1
        start = end + 1
    return result


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 3:
        return None
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    spread_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    spread_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if spread_x == 0 or spread_y == 0:
        return None
    return covariance / (spread_x * spread_y)


def spearman_with_interval(
    clusters: Sequence[int], xs: Sequence[float], ys: Sequence[float], seed: int
) -> dict[str, float | int | None]:
    """Spearman's coefficient with a 95% match-cluster bootstrap interval.

    Resampling whole matches keeps the windows of one match (both teams) together, so
    the interval reflects that they are not independent. The replicates reuse the full
    sample's ranks (Pearson on fixed ranks), a standard shortcut that keeps this fast.
    """
    rank_x, rank_y = ranks(xs), ranks(ys)
    estimate = pearson(rank_x, rank_y)
    by_match: dict[int, list[int]] = defaultdict(list)
    for position, cluster in enumerate(clusters):
        by_match[cluster].append(position)
    matches = sorted(by_match)
    generator = random.Random(seed)
    replicates: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        positions = [
            position
            for match in generator.choices(matches, k=len(matches))
            for position in by_match[match]
        ]
        value = pearson([rank_x[p] for p in positions], [rank_y[p] for p in positions])
        if value is not None:
            replicates.append(value)
    replicates.sort()
    low = replicates[int(0.025 * len(replicates))] if replicates else None
    high = replicates[int(0.975 * len(replicates)) - 1] if replicates else None
    return {
        "spearman": estimate,
        "low": low,
        "high": high,
        "observations": len(xs),
        "matches": len(matches),
    }


def quantile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def describe(values: Sequence[float]) -> dict[str, float]:
    return {
        "mean": statistics.fmean(values),
        "p10": quantile(values, 0.10),
        "p25": quantile(values, 0.25),
        "median": quantile(values, 0.50),
        "p75": quantile(values, 0.75),
        "p90": quantile(values, 0.90),
    }


def build_pairs(windows: Sequence[Window]) -> list[Pair]:
    complete = {(w.match_id, w.team_id, w.period, w.index): w for w in windows if w.complete}
    return [
        Pair(complete[(m, t, p, i - 1)], w)
        for (m, t, p, i), w in complete.items()
        if (m, t, p, i - 1) in complete
    ]


def value_bins(pairs: Sequence[Pair], key: Callable[[Pair], float]) -> list[dict[str, object]]:
    """Group pairs into five bins at the 20/40/60/80% cut values; ties stay in one bin."""
    values = [key(pair) for pair in pairs]
    cuts = [quantile(values, fraction) for fraction in (0.2, 0.4, 0.6, 0.8)]
    groups: list[list[Pair]] = [[] for _ in range(5)]
    for pair, value in zip(pairs, values, strict=True):
        groups[sum(value > cut for cut in cuts)].append(pair)
    summary: list[dict[str, object]] = []
    for group in groups:
        if not group:
            continue
        xg_changes = [c for c in (p.xg_change for p in group) if c is not None]
        after_entries = sum(p.after.entries for p in group)
        after_xg = sum(p.after.xg or 0.0 for p in group)
        summary.append(
            {
                "range": [min(key(p) for p in group), max(key(p) for p in group)],
                "pairs": len(group),
                "matches": len({p.match_id for p in group}),
                "mean_change": statistics.fmean(key(p) for p in group),
                "mean_shots_change": statistics.fmean(p.shots_change for p in group),
                "mean_xg_change": statistics.fmean(xg_changes) if xg_changes else None,
                "share_shots_up": sum(p.shots_change > 0 for p in group) / len(group),
                "share_shots_down": sum(p.shots_change < 0 for p in group) / len(group),
                "share_no_shot_after": sum(p.after.shots == 0 for p in group) / len(group),
                "mean_shots_after": statistics.fmean(p.after.shots for p in group),
                "mean_xg_after": statistics.fmean(p.after.xg or 0.0 for p in group),
                "xg_per_entry_after": after_xg / after_entries if after_entries else None,
            }
        )
    return summary


def change_associations(pairs: Sequence[Pair], seed: int) -> dict[str, object]:
    usable = [p for p in pairs if p.xg_change is not None]
    clusters = [p.match_id for p in usable]
    entries = [float(p.entries_change) for p in usable]
    return {
        "entries_vs_shots": spearman_with_interval(
            clusters, entries, [float(p.shots_change) for p in usable], seed
        ),
        "entries_vs_xg": spearman_with_interval(
            clusters, entries, [cast(float, p.xg_change) for p in usable], seed + 1
        ),
    }


def level_analysis(windows: Sequence[Window], seed: int) -> dict[str, object]:
    """Same-window association after removing each team-match's own average."""
    by_team_match: dict[tuple[int, int], list[Window]] = defaultdict(list)
    for window in windows:
        if window.complete and window.xg is not None:
            by_team_match[(window.match_id, window.team_id)].append(window)
    clusters: list[int] = []
    entries: list[float] = []
    shots: list[float] = []
    xgs: list[float] = []
    above: list[tuple[float, float]] = []
    below: list[tuple[float, float]] = []
    for (match_id, _), group in by_team_match.items():
        mean_entries = statistics.fmean(w.entries for w in group)
        mean_shots = statistics.fmean(w.shots for w in group)
        mean_xg = statistics.fmean(cast(float, w.xg) for w in group)
        for w in group:
            centered = (w.shots - mean_shots, cast(float, w.xg) - mean_xg)
            clusters.append(match_id)
            entries.append(w.entries - mean_entries)
            shots.append(centered[0])
            xgs.append(centered[1])
            if w.entries > mean_entries:
                above.append(centered)
            elif w.entries < mean_entries:
                below.append(centered)
    return {
        "team_matches": len(by_team_match),
        "windows": len(entries),
        "entries_vs_shots": spearman_with_interval(clusters, entries, shots, seed),
        "entries_vs_xg": spearman_with_interval(clusters, entries, xgs, seed + 1),
        "above_own_average": {
            "windows": len(above),
            "mean_shots_vs_own_average": statistics.fmean(a[0] for a in above),
            "mean_xg_vs_own_average": statistics.fmean(a[1] for a in above),
        },
        "below_own_average": {
            "windows": len(below),
            "mean_shots_vs_own_average": statistics.fmean(b[0] for b in below),
            "mean_xg_vs_own_average": statistics.fmean(b[1] for b in below),
        },
    }


def tilt_change(pair: Pair) -> float:
    """Change in field-tilt share; only called when both windows have a denominator."""
    return cast(float, pair.after.tilt_share) - cast(float, pair.before.tilt_share)


def tilt_analysis(pairs: Sequence[Pair], seed: int) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for minimum in TILT_MINIMUM_DENOMINATORS:
        usable = [
            p
            for p in pairs
            if p.before.tilt_denominator >= minimum
            and p.after.tilt_denominator >= minimum
            and p.xg_change is not None
        ]
        changes = [
            cast(float, p.after.tilt_share) - cast(float, p.before.tilt_share) for p in usable
        ]
        clusters = [p.match_id for p in usable]
        results.append(
            {
                "minimum_denominator": minimum,
                "pairs": len(usable),
                "share_of_all_pairs": len(usable) / len(pairs),
                "tilt_change": describe(changes),
                "tilt_vs_shots": spearman_with_interval(
                    clusters, changes, [float(p.shots_change) for p in usable], seed
                ),
                "tilt_vs_xg": spearman_with_interval(
                    clusters, changes, [cast(float, p.xg_change) for p in usable], seed + 1
                ),
                "bins": value_bins(usable, tilt_change),
            }
        )
    return results


def by_group(
    pairs: Sequence[Pair], group: Callable[[Pair], str], seed: int
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[Pair]] = defaultdict(list)
    for pair in pairs:
        grouped[group(pair)].append(pair)
    return {
        name: {
            "pairs": len(members),
            "matches": len({p.match_id for p in members}),
            **change_associations(members, seed),
        }
        for name, members in sorted(grouped.items())
        if len({p.match_id for p in members}) >= 10
    }


def per_team(pairs: Sequence[Pair]) -> dict[str, object]:
    """One coefficient per team, so heavily repeated teams do not dominate."""
    grouped: dict[int, list[Pair]] = defaultdict(list)
    for pair in pairs:
        grouped[pair.after.team_id].append(pair)
    shots_coefficients: list[float] = []
    xg_coefficients: list[float] = []
    for members in grouped.values():
        usable = [p for p in members if p.xg_change is not None]
        if len(usable) < TEAM_MINIMUM_PAIRS:
            continue
        entries = ranks([float(p.entries_change) for p in usable])
        shots = pearson(entries, ranks([float(p.shots_change) for p in usable]))
        xg = pearson(entries, ranks([cast(float, p.xg_change) for p in usable]))
        if shots is not None:
            shots_coefficients.append(shots)
        if xg is not None:
            xg_coefficients.append(xg)
    return {
        "minimum_pairs": TEAM_MINIMUM_PAIRS,
        "teams": len(shots_coefficients),
        "entries_vs_shots": describe(shots_coefficients),
        "share_positive_shots": sum(c > 0 for c in shots_coefficients) / len(shots_coefficients),
        "entries_vs_xg": describe(xg_coefficients),
        "share_positive_xg": sum(c > 0 for c in xg_coefficients) / len(xg_coefficients),
    }


def counterexamples(pairs: Sequence[Pair]) -> dict[str, object]:
    changes = [float(p.entries_change) for p in pairs]
    top_cut = quantile(changes, 0.9)
    bottom_cut = quantile(changes, 0.1)
    top = [p for p in pairs if p.entries_change >= top_cut]
    top_without_shot = [p for p in top if p.after.shots == 0]
    top_fewer_shots = [p for p in top if p.shots_change < 0]
    bottom = [p for p in pairs if p.entries_change <= bottom_cut]
    bottom_more_shots = [p for p in bottom if p.shots_change > 0]

    def example(pair: Pair) -> dict[str, object]:
        return {
            "match_id": pair.match_id,
            "team": pair.after.team_name,
            "competition_season": pair.after.competition_season,
            "period": pair.after.period,
            "window_minutes": [pair.after.start_seconds / 60, pair.after.end_seconds / 60],
            "entries": [pair.before.entries, pair.after.entries],
            "tilt_passes": [
                f"{w.tilt_passes}/{w.tilt_denominator}" for w in (pair.before, pair.after)
            ],
            "shots": [pair.before.shots, pair.after.shots],
            "xg": [round(pair.before.xg or 0.0, 3), round(pair.after.xg or 0.0, 3)],
        }

    listable = sorted(
        (p for p in top_without_shot if p.match_id not in PROBE_MATCHES),
        key=lambda p: (-p.after.entries, p.match_id, p.after.team_id, p.after.period),
    )
    return {
        "top_decile_entries_change_cut": top_cut,
        "top_decile_pairs": len(top),
        "top_decile_no_shot_after": len(top_without_shot),
        "top_decile_fewer_shots_after": len(top_fewer_shots),
        "bottom_decile_entries_change_cut": bottom_cut,
        "bottom_decile_pairs": len(bottom),
        "bottom_decile_more_shots_after": len(bottom_more_shots),
        "largest_entry_spells_without_a_shot": [example(p) for p in listable[:6]],
    }


def coverage(windows: Sequence[Window], pairs: Sequence[Pair]) -> dict[str, object]:
    complete = [w for w in windows if w.complete]
    incomplete = [w for w in windows if not w.complete]
    total_shots = sum(w.shots for w in windows)
    per_competition: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for pair in pairs:
        per_competition[pair.after.competition_season]["pairs"] += 1
    for window in complete:
        per_competition[window.competition_season]["complete_windows"] += 1
    return {
        "matches": len({w.match_id for w in windows}),
        "team_matches": len({(w.match_id, w.team_id) for w in windows}),
        "teams": len({w.team_id for w in windows}),
        "complete_windows": len(complete),
        "incomplete_windows": len(incomplete),
        "incomplete_seconds": describe([w.end_seconds - w.start_seconds for w in incomplete]),
        "share_of_shots_in_incomplete_windows": sum(w.shots for w in incomplete) / total_shots,
        "complete_windows_without_any_event": sum(w.match_events == 0 for w in complete),
        "shots_missing_xg": sum(w.shots_missing_xg for w in windows),
        "windows_with_missing_xg": sum(w.xg is None for w in windows),
        "pairs": len(pairs),
        "pairs_goal_free": sum(p.goal_free for p in pairs),
        "per_competition_season": {k: dict(v) for k, v in sorted(per_competition.items())},
    }


def distributions(windows: Sequence[Window]) -> dict[str, object]:
    complete = [w for w in windows if w.complete]
    denominators = [float(w.tilt_denominator) for w in complete]
    return {
        "entries": describe([float(w.entries) for w in complete]),
        "shots": describe([float(w.shots) for w in complete]),
        "share_windows_without_shot": sum(w.shots == 0 for w in complete) / len(complete),
        "xg": describe([w.xg or 0.0 for w in complete]),
        "tilt_denominator": describe(denominators),
        "share_windows_tilt_undefined": sum(d == 0 for d in denominators) / len(denominators),
        "share_windows_tilt_denominator_below": {
            str(m): sum(d < m for d in denominators) / len(denominators)
            for m in TILT_MINIMUM_DENOMINATORS
        },
    }


def provenance(connection: Any) -> dict[str, object]:
    run = cast(
        tuple[Any, ...],
        connection.execute(
            "SELECT ingest_run_id, git_commit, git_dirty, source_commit, split_version, "
            "duckdb_version, normalized_matches FROM normalized.ingest_runs"
        ).fetchone(),
    )
    return {
        "ingest_run_id": run[0],
        "ingest_git_commit": run[1],
        "ingest_git_dirty": run[2],
        "source_commit": run[3],
        "split_version": run[4],
        "duckdb_version": run[5],
        "normalized_matches": run[6],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--window-minutes", type=int, default=10)
    parser.add_argument("--warehouse", type=Path, default=WAREHOUSE)
    arguments = parser.parse_args()
    length = arguments.window_minutes * 60

    with connect_research(arguments.warehouse) as connection:
        facts = provenance(connection)
        windows = load_windows(connection, length)
    pairs = build_pairs(windows)
    goal_free = [p for p in pairs if p.goal_free]
    results: dict[str, object] = {
        "window_minutes": arguments.window_minutes,
        "provenance": facts,
        "coverage": coverage(windows, pairs),
        "distributions": distributions(windows),
        "level_within_team_match": level_analysis(windows, BOOTSTRAP_SEED),
        "change_all_pairs": change_associations(pairs, BOOTSTRAP_SEED),
        "change_bins_entries": value_bins(pairs, lambda p: float(p.entries_change)),
        "change_goal_free_pairs": change_associations(goal_free, BOOTSTRAP_SEED),
        "change_bins_entries_goal_free": value_bins(goal_free, lambda p: float(p.entries_change)),
        "change_by_competition_season": by_group(
            pairs, lambda p: p.after.competition_season, BOOTSTRAP_SEED
        ),
        "change_by_half": by_group(pairs, lambda p: f"period {p.after.period}", BOOTSTRAP_SEED),
        "change_per_team": per_team(pairs),
        "field_tilt": tilt_analysis(pairs, BOOTSTRAP_SEED),
        "counterexamples": counterexamples(pairs),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(results, indent=2, default=str)
    (OUTPUT / f"results-{arguments.window_minutes}-minutes.json").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
