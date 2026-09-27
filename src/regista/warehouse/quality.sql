-- Mechanical data-quality checks for every match the adapter accepted.
-- Blocking failures exclude a match from the analytical layer; warnings are reported only.
-- raw_checksum and adapter_validation are recorded by the ingestion pipeline before this runs.
CREATE TEMP TABLE accepted AS
SELECT m.*
FROM normalized.matches AS m
JOIN normalized.dq_checks AS c
    ON c.match_id = m.match_id AND c.check_name = 'adapter_validation' AND c.passed;

CREATE TEMP TABLE event_facts AS
SELECT
    e.match_id,
    count(*) AS event_count,
    count(DISTINCT e.sequence) AS distinct_sequences,
    min(e.sequence) AS first_sequence,
    max(e.sequence) AS last_sequence,
    count(DISTINCT e.team_id) AS team_count,
    bool_or(e.team_id = a.home_team_id) AS home_seen,
    bool_or(e.team_id = a.away_team_id) AS away_seen,
    count(*) FILTER (
        WHERE e.x NOT BETWEEN 0 AND 120 OR e.y NOT BETWEEN 0 AND 80
        OR e.end_x NOT BETWEEN 0 AND 120 OR e.end_y NOT BETWEEN 0 AND 80
    ) AS off_pitch
FROM normalized.events AS e
JOIN accepted AS a USING (match_id)
GROUP BY e.match_id;

INSERT INTO normalized.dq_checks
SELECT
    a.match_id, 'teams_present', 'blocking',
    coalesce(f.team_count = 2 AND f.home_seen AND f.away_seen, false),
    format('{} teams on events; home seen {}, away seen {}',
        coalesce(f.team_count, 0), coalesce(f.home_seen, false), coalesce(f.away_seen, false)),
    getvariable('ingest_run_id')
FROM accepted AS a LEFT JOIN event_facts AS f USING (match_id);

-- A full match has thousands of events; far fewer means a truncated or partial file.
INSERT INTO normalized.dq_checks
SELECT
    a.match_id, 'event_count_plausible', 'blocking',
    coalesce(f.event_count, 0) >= 1000,
    format('{} events (minimum 1000)', coalesce(f.event_count, 0)),
    getvariable('ingest_run_id')
FROM accepted AS a LEFT JOIN event_facts AS f USING (match_id);

INSERT INTO normalized.dq_checks
SELECT
    a.match_id, 'sequence_contiguous', 'blocking',
    coalesce(
        f.first_sequence = 1 AND f.last_sequence = f.event_count
        AND f.distinct_sequences = f.event_count,
        false
    ),
    format('sequence {}..{} over {} events ({} distinct)',
        coalesce(f.first_sequence, 0), coalesce(f.last_sequence, 0), coalesce(f.event_count, 0),
        coalesce(f.distinct_sequences, 0)),
    getvariable('ingest_run_id')
FROM accepted AS a LEFT JOIN event_facts AS f USING (match_id);

-- Shootout goals (period 5) decide nothing about the recorded score.
INSERT INTO normalized.dq_checks
WITH derived AS (
    SELECT
        a.match_id,
        count(*) FILTER (WHERE g.scoring_team_id = a.home_team_id AND NOT g.in_shootout) AS home,
        count(*) FILTER (WHERE g.scoring_team_id = a.away_team_id AND NOT g.in_shootout) AS away
    FROM accepted AS a
    LEFT JOIN normalized.goals AS g USING (match_id)
    GROUP BY a.match_id
)
SELECT
    a.match_id, 'score_reconciles', 'blocking',
    d.home = a.home_score AND d.away = a.away_score,
    format('events {}-{}, match index {}-{}', d.home, d.away, a.home_score, a.away_score),
    getvariable('ingest_run_id')
FROM accepted AS a JOIN derived AS d USING (match_id);

INSERT INTO normalized.dq_checks
WITH missing AS (
    SELECT s.match_id, count(*) AS players
    FROM normalized.substitutions AS s
    CROSS JOIN LATERAL (VALUES (s.player_off_id), (s.player_on_id)) AS p(player_id)
    LEFT JOIN normalized.appearances AS ap
        ON ap.match_id = s.match_id AND ap.team_id = s.team_id AND ap.player_id = p.player_id
    WHERE ap.player_id IS NULL
    GROUP BY s.match_id
)
SELECT
    a.match_id, 'substitutes_in_lineup', 'blocking',
    coalesce(m.players, 0) = 0,
    format('{} substitution players missing from the team lineup', coalesce(m.players, 0)),
    getvariable('ingest_run_id')
FROM accepted AS a LEFT JOIN missing AS m USING (match_id);

-- The provider timestamp may step backwards within a period. Replay uses sequence, so this
-- is a warning; clock-window analyses should know how often and how far it happens.
INSERT INTO normalized.dq_checks
WITH steps AS (
    SELECT
        match_id,
        period_seconds - max(period_seconds) OVER (
            PARTITION BY match_id, period ORDER BY sequence
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS step
    FROM normalized.events
    WHERE match_id IN (SELECT match_id FROM accepted)
),
regressions AS (
    SELECT match_id, count(*) FILTER (WHERE step < 0) AS count, min(step) AS largest
    FROM steps
    GROUP BY match_id
)
SELECT
    a.match_id, 'clock_monotonic', 'warning',
    coalesce(r.count, 0) = 0,
    format('{} backward steps; largest {} s', coalesce(r.count, 0),
        coalesce(-least(r.largest, 0), 0)),
    getvariable('ingest_run_id')
FROM accepted AS a LEFT JOIN regressions AS r USING (match_id);

INSERT INTO normalized.dq_checks
SELECT
    a.match_id, 'coordinates_on_pitch', 'warning',
    coalesce(f.off_pitch, 0) = 0,
    format('{} events with a start or end location outside 120 x 80', coalesce(f.off_pitch, 0)),
    getvariable('ingest_run_id')
FROM accepted AS a LEFT JOIN event_facts AS f USING (match_id);

INSERT INTO normalized.dq_checks
SELECT
    match_id, 'provider_metadata_present', 'warning',
    data_version IS NOT NULL AND xy_fidelity_version IS NOT NULL
        AND shot_fidelity_version IS NOT NULL,
    format('data {}, xy fidelity {}, shot fidelity {}',
        coalesce(data_version, 'missing'), coalesce(xy_fidelity_version, 'missing'),
        coalesce(shot_fidelity_version, 'missing')),
    getvariable('ingest_run_id')
FROM accepted;

INSERT INTO normalized.dq_checks
WITH missing AS (
    SELECT e.match_id, count(DISTINCT e.player_id) AS players
    FROM normalized.events AS e
    LEFT JOIN normalized.appearances AS ap
        ON ap.match_id = e.match_id AND ap.team_id = e.team_id AND ap.player_id = e.player_id
    WHERE e.player_id IS NOT NULL AND ap.player_id IS NULL
    GROUP BY e.match_id
)
SELECT
    a.match_id, 'event_players_in_lineup', 'warning',
    coalesce(m.players, 0) = 0,
    format('{} event players missing from their team lineup', coalesce(m.players, 0)),
    getvariable('ingest_run_id')
FROM accepted AS a LEFT JOIN missing AS m USING (match_id);

-- Position spells should neither end before they start nor overlap another spell of the same
-- player. Player intervals take the union, so this is a warning.
INSERT INTO normalized.dq_checks
WITH keyed AS (
    SELECT
        match_id, player_id, spell_number,
        start_period * 10000 + start_period_seconds AS start_key,
        end_period * 10000 + end_period_seconds AS end_key
    FROM normalized.position_spells
),
compared AS (
    SELECT
        *,
        lead(start_key) OVER (
            PARTITION BY match_id, player_id ORDER BY start_key, spell_number
        ) AS next_start_key
    FROM keyed
),
problems AS (
    SELECT match_id, count(*) AS spells
    FROM compared
    WHERE end_key < start_key OR end_key > next_start_key OR (end_key IS NULL AND next_start_key IS NOT NULL)
    GROUP BY match_id
)
SELECT
    a.match_id, 'position_spells_consistent', 'warning',
    coalesce(p.spells, 0) = 0,
    format('{} spells end before they start or overlap a later spell', coalesce(p.spells, 0)),
    getvariable('ingest_run_id')
FROM accepted AS a LEFT JOIN problems AS p USING (match_id);

-- A substituted player's lineup spells should end at the Substitution event (within a minute).
INSERT INTO normalized.dq_checks
WITH substitutions AS (
    SELECT s.match_id, s.player_off_id, e.period * 10000 + e.period_seconds AS off_key
    FROM normalized.substitutions AS s
    JOIN normalized.events AS e ON e.event_id = s.event_id
),
late AS (
    SELECT s.match_id, count(DISTINCT s.player_off_id) AS players
    FROM substitutions AS s
    JOIN normalized.position_spells AS p
        ON p.match_id = s.match_id AND p.player_id = s.player_off_id
    WHERE coalesce(p.end_period * 10000 + p.end_period_seconds, 1e9) > s.off_key + 60
    GROUP BY s.match_id
)
SELECT
    a.match_id, 'substitution_ends_lineup_spell', 'warning',
    coalesce(l.players, 0) = 0,
    format('{} substituted players whose lineup spell runs over a minute past the substitution',
        coalesce(l.players, 0)),
    getvariable('ingest_run_id')
FROM accepted AS a LEFT JOIN late AS l USING (match_id);

UPDATE normalized.matches AS m
SET dq_status = CASE
    WHEN EXISTS (
        SELECT 1 FROM normalized.dq_checks AS c
        WHERE c.match_id = m.match_id AND c.severity = 'blocking' AND NOT c.passed
    ) THEN 'excluded'
    WHEN EXISTS (
        SELECT 1 FROM normalized.dq_checks AS c
        WHERE c.match_id = m.match_id AND NOT c.passed
    ) THEN 'passed_with_warnings'
    ELSE 'passed'
END;

DROP TABLE accepted;
DROP TABLE event_facts;
