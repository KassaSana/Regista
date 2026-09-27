"""Contract checks pinning provider assumptions the warehouse relies on.

They read the locally built development warehouse (``regista data ingest``) and
skip when it is absent. They never copy provider records into the repository.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from regista.adapters.statsbomb.events import load_events
from regista.adapters.statsbomb.lineups import PERIOD_START_MINUTES
from regista.domain.entries import channel_of, is_final_third_entry
from regista.domain.ids import MatchId
from regista.warehouse.research import connect_research

pytestmark = pytest.mark.contract

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE = REPOSITORY_ROOT / "data/warehouse/regista.duckdb"
Query = Callable[[str], list[tuple[object, ...]]]


@pytest.fixture(scope="module")
def rows() -> Iterator[Query]:
    if not WAREHOUSE.exists():
        pytest.skip(f"no development warehouse at {WAREHOUSE}")
    connection = connect_research(WAREHOUSE)

    def run(sql: str) -> list[tuple[object, ...]]:
        return connection.execute(sql).fetchall()

    yield run
    connection.close()


def test_the_continuous_minute_restarts_at_the_pinned_period_offsets(rows: Query) -> None:
    observed = rows(
        "SELECT period, min(minute), max(minute) FROM normalized.events "
        "WHERE event_type = 'period_start' GROUP BY period ORDER BY period"
    )
    for period, first, last in observed:
        assert first == last == PERIOD_START_MINUTES[int(str(period))]


def test_own_goal_for_is_credited_to_its_event_team(rows: Query) -> None:
    own_goals = rows("SELECT count(*) FROM normalized.goals WHERE kind = 'own_goal'")[0][0]
    unreconciled = rows(
        "SELECT count(*) FROM normalized.dq_checks "
        "WHERE check_name = 'score_reconciles' AND NOT passed"
    )[0][0]

    assert int(str(own_goals)) > 0
    assert unreconciled == 0


def test_the_warehouse_holds_development_matches_only(rows: Query) -> None:
    buckets = rows(
        "SELECT DISTINCT s.bucket FROM normalized.matches AS m "
        "JOIN normalized.splits AS s USING (match_id)"
    )
    raw_buckets = rows(
        "SELECT DISTINCT split_bucket FROM normalized.raw_files WHERE kind IN ('events', 'lineups')"
    )

    assert buckets == [("development",)]
    assert raw_buckets == [("development",)]


def test_large_clock_regressions_are_only_final_first_half_ball_receipts(rows: Query) -> None:
    # Pinned for research note 04: the provider stamps some last first-half Ball Receipt at 00:00.
    regressions = rows(
        "WITH steps AS (SELECT period, provider_event_type, period_seconds - max(period_seconds) "
        "OVER (PARTITION BY match_id, period ORDER BY sequence "
        "ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS step FROM normalized.events) "
        "SELECT DISTINCT period, provider_event_type FROM steps WHERE step < -5"
    )

    assert regressions in ([], [(1, "Ball Receipt*")])


def test_consistent_lineups_never_put_more_than_eleven_players_on(rows: Query) -> None:
    ratios = rows(
        "WITH team AS (SELECT match_id, team_id, sum(seconds_on_pitch) AS seconds "
        "FROM analytical.player_period_spans GROUP BY ALL), "
        "played AS (SELECT match_id, sum(end_seconds) AS seconds FROM analytical.periods "
        "WHERE NOT is_shootout GROUP BY ALL) "
        "SELECT max(team.seconds / played.seconds) FROM team JOIN played USING (match_id) "
        "JOIN analytical.team_matches AS tm USING (match_id, team_id) WHERE tm.lineup_consistent"
    )

    assert float(str(ratios[0][0])) <= 11.02


def test_sql_entries_equal_the_domain_definition_on_a_real_match(rows: Query) -> None:
    match_id = 3_773_497
    commit = rows("SELECT source_commit FROM normalized.ingest_runs")[0][0]
    events_path = (
        REPOSITORY_ROOT / f"data/raw/statsbomb-open-data/{commit}/data/events/{match_id}.json"
    )
    if not events_path.exists():
        pytest.skip(f"no raw event file at {events_path}")

    expected = {
        (str(event.identifier), channel_of(event.movement.end).value)
        for event in load_events(events_path, MatchId(match_id))
        if event.movement is not None and is_final_third_entry(event)
    }
    actual = {
        (str(event_id), str(channel))
        for event_id, channel in rows(
            "SELECT event_id, channel FROM analytical.final_third_entries "
            f"WHERE match_id = {match_id}"
        )
    }

    assert actual == expected
    assert len(expected) == 126  # Barcelona 96 + Real Madrid 30 (Phase 1 record)
