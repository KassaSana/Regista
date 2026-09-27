-- Analytical layer: derived Regista tables, rebuilt deterministically from `normalized`.
-- Only matches that passed every blocking data-quality check appear here.
-- These tables summarize whole matches. In-match detectors never read them for the match being
-- replayed, and they are never a "normal for this team" baseline (see the Phase 2 specification).
-- Geometry is Regista's frame: 120 x 80, the acting team attacks toward increasing x, low y is
-- the acting team's left. Time is (period, period_seconds); 5-minute bins restart each period.
CREATE SCHEMA analytical;

-- One row per team per included match. Final goals are hindsight: research use only.
CREATE TABLE analytical.team_matches AS
WITH team_names AS (
    SELECT team_id, min(team_name) AS team_name FROM normalized.teams GROUP BY team_id
)
SELECT
    m.match_id, m.competition_id, m.season_id, cs.competition_name, cs.season_name,
    m.match_date, m.kickoff, side.team_id, own.team_name, side.is_home,
    side.opponent_team_id, opponent.team_name AS opponent_name,
    side.goals_for, side.goals_against,
    -- False when lineup spells overlap or run past a Substitution event; player minutes and
    -- intervals for such matches are approximate.
    NOT EXISTS (
        SELECT 1 FROM normalized.dq_checks AS c
        WHERE c.match_id = m.match_id AND NOT c.passed
            AND c.check_name IN ('position_spells_consistent', 'substitution_ends_lineup_spell')
    ) AS lineup_consistent,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM normalized.matches AS m
JOIN normalized.competition_seasons AS cs USING (competition_id, season_id)
CROSS JOIN LATERAL (
    VALUES
        (m.home_team_id, true, m.away_team_id, m.home_score, m.away_score),
        (m.away_team_id, false, m.home_team_id, m.away_score, m.home_score)
) AS side(team_id, is_home, opponent_team_id, goals_for, goals_against)
JOIN team_names AS own ON own.team_id = side.team_id
JOIN team_names AS opponent ON opponent.team_id = side.opponent_team_id
WHERE m.dq_status <> 'excluded';

-- Period lengths. Period 5 is a penalty shootout.
CREATE TABLE analytical.periods AS
SELECT
    e.match_id, e.period,
    greatest(
        coalesce(max(e.period_seconds) FILTER (WHERE e.event_type = 'period_end'), 0),
        max(e.period_seconds)
    ) AS end_seconds,
    e.period = 5 AS is_shootout,
    count(*) AS events,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM normalized.events AS e
WHERE e.match_id IN (SELECT match_id FROM analytical.team_matches)
GROUP BY e.match_id, e.period;

-- Home and away score before each event, excluding shootout goals.
CREATE TABLE analytical.score_states AS
WITH scored AS (
    SELECT
        e.match_id, e.event_id, e.sequence, e.period, e.period_seconds,
        (g.scoring_team_id = m.home_team_id AND NOT g.in_shootout)::INTEGER AS home_goal,
        (g.scoring_team_id = m.away_team_id AND NOT g.in_shootout)::INTEGER AS away_goal
    FROM normalized.events AS e
    JOIN normalized.matches AS m USING (match_id)
    LEFT JOIN normalized.goals AS g ON g.event_id = e.event_id
    WHERE m.dq_status <> 'excluded'
)
SELECT
    match_id, event_id, sequence, period, period_seconds,
    coalesce(sum(home_goal) OVER before, 0)::INTEGER AS home_score_before,
    coalesce(sum(away_goal) OVER before, 0)::INTEGER AS away_score_before,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM scored
WINDOW before AS (
    PARTITION BY match_id ORDER BY sequence ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
);

-- A wide, research-friendly event table: location zones, open play, completion, xG, score.
CREATE TABLE analytical.event_context AS
SELECT
    e.match_id, e.event_id, e.sequence, e.period, e.period_seconds, e.minute, e.second,
    floor(e.period_seconds / 300)::INTEGER AS time_bin,
    -- True when the provider timestamp is earlier than an event before it in the same period
    -- (for example a final first-half Ball Receipt stamped 00:00). Kept, never corrected.
    coalesce(e.period_seconds < max(e.period_seconds) OVER (
        PARTITION BY e.match_id, e.period ORDER BY e.sequence
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ), false) AS clock_out_of_order,
    e.team_id, tm.opponent_team_id, tm.is_home, e.player_id, e.position,
    e.event_type, e.provider_event_type,
    e.x, e.y, e.end_x, e.end_y,
    CASE WHEN e.x < 40 THEN 'defensive' WHEN e.x < 80 THEN 'middle' WHEN e.x >= 80 THEN 'final' END
        AS third,
    CASE WHEN e.y < 80.0 / 3 THEN 'left' WHEN e.y > 160.0 / 3 THEN 'right'
        WHEN e.y IS NOT NULL THEN 'center' END AS channel,
    least(greatest(floor(e.x / 20), 0), 5)::INTEGER AS zone_x,
    least(greatest(floor(e.y / 16), 0), 4)::INTEGER AS zone_y,
    e.x >= 102 AND e.y BETWEEN 18 AND 62 AS in_box,
    CASE WHEN e.end_x < 40 THEN 'defensive' WHEN e.end_x < 80 THEN 'middle'
        WHEN e.end_x >= 80 THEN 'final' END AS end_third,
    CASE WHEN e.end_y < 80.0 / 3 THEN 'left' WHEN e.end_y > 160.0 / 3 THEN 'right'
        WHEN e.end_y IS NOT NULL THEN 'center' END AS end_channel,
    e.end_x >= 102 AND e.end_y BETWEEN 18 AND 62 AS end_in_box,
    CASE e.event_type
        WHEN 'pass' THEN p.open_play
        WHEN 'carry' THEN true
        WHEN 'shot' THEN s.shot_type = 'Open Play'
    END AS open_play,
    p.set_piece_type,
    CASE e.event_type WHEN 'pass' THEN p.completed WHEN 'carry' THEN true END AS completed,
    s.shot_type,
    -- Exact decimal (the provider value has at most 10 decimals), so sums are order-independent.
    s.provider_xg::DECIMAL(18, 12) AS provider_xg,
    g.event_id IS NOT NULL AND NOT g.in_shootout AS scores_goal,
    e.under_pressure,
    CASE WHEN tm.is_home THEN ss.home_score_before ELSE ss.away_score_before END
        AS goals_for_before,
    CASE WHEN tm.is_home THEN ss.away_score_before ELSE ss.home_score_before END
        AS goals_against_before,
    goals_for_before - goals_against_before AS goal_difference_before,
    CASE sign(goals_for_before - goals_against_before)
        WHEN 1 THEN 'leading' WHEN 0 THEN 'level' ELSE 'trailing' END AS score_state,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM normalized.events AS e
JOIN analytical.team_matches AS tm ON tm.match_id = e.match_id AND tm.team_id = e.team_id
JOIN analytical.score_states AS ss ON ss.event_id = e.event_id
LEFT JOIN normalized.passes AS p ON p.event_id = e.event_id
LEFT JOIN normalized.shots AS s ON s.event_id = e.event_id
LEFT JOIN normalized.goals AS g ON g.event_id = e.event_id;

-- Locked definition (AGENTS.md): an open-play completed pass or carry starting before x = 80
-- and ending at or beyond x = 80. Channel from the end location.
CREATE TABLE analytical.final_third_entries AS
SELECT
    match_id, event_id, sequence, period, period_seconds, time_bin, team_id, opponent_team_id,
    player_id, event_type, x, y, end_x, end_y, end_channel AS channel, score_state,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM analytical.event_context
WHERE event_type IN ('pass', 'carry') AND completed AND open_play AND x < 80 AND end_x >= 80;

-- Provisional definition v1 (owner review pending): an open-play completed pass or carry
-- starting outside the penalty area and ending inside it (x >= 102, 18 <= y <= 62).
CREATE TABLE analytical.box_entries AS
SELECT
    match_id, event_id, sequence, period, period_seconds, time_bin, team_id, opponent_team_id,
    player_id, event_type, x, y, end_x, end_y, end_channel AS channel, score_state,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM analytical.event_context
WHERE event_type IN ('pass', 'carry') AND completed AND open_play
    AND NOT coalesce(in_box, false) AND end_in_box;

-- Every team, period, and 5-minute bin, including empty ones, so rolling windows are correct.
-- The last bin of a period may be shorter or longer than 300 s; see bin_seconds.
CREATE TABLE analytical.team_time_bins AS
WITH grid AS (
    SELECT
        tm.match_id, tm.team_id, tm.opponent_team_id, p.period, bin.time_bin,
        bin.time_bin * 300 AS bin_start_seconds,
        CASE WHEN bin.time_bin = floor(p.end_seconds / 300) THEN p.end_seconds
            ELSE (bin.time_bin + 1) * 300 END AS bin_end_seconds
    FROM analytical.team_matches AS tm
    JOIN analytical.periods AS p ON p.match_id = tm.match_id AND NOT p.is_shootout
    CROSS JOIN LATERAL generate_series(0, floor(p.end_seconds / 300)::INTEGER) AS bin(time_bin)
),
counts AS (
    SELECT
        match_id, team_id, period, time_bin,
        count(*) FILTER (WHERE event_type = 'pass') AS pass_attempts,
        count(*) FILTER (WHERE event_type = 'pass' AND completed) AS completed_passes,
        count(*) FILTER (WHERE event_type = 'pass' AND open_play) AS open_play_passes,
        count(*) FILTER (WHERE event_type = 'pass' AND NOT open_play) AS set_piece_passes,
        count(*) FILTER (WHERE event_type = 'pass' AND completed AND open_play AND x >= 80)
            AS tilt_passes,
        count(*) FILTER (WHERE event_type = 'carry') AS carries,
        count(*) FILTER (WHERE event_type = 'shot') AS shots,
        count(*) FILTER (WHERE event_type = 'shot' AND open_play) AS open_play_shots,
        coalesce(sum(provider_xg), 0) AS provider_xg,
        coalesce(sum(provider_xg) FILTER (WHERE open_play), 0) AS open_play_provider_xg,
        count(*) FILTER (WHERE scores_goal) AS goals,
        count(*) FILTER (WHERE event_type = 'pressure') AS pressures,
        count(*) FILTER (WHERE event_type = 'ball_recovery') AS ball_recoveries
    FROM analytical.event_context
    GROUP BY ALL
),
entries AS (
    SELECT
        match_id, team_id, period, time_bin,
        count(*) AS final_third_entries,
        count(*) FILTER (WHERE channel = 'left') AS entries_left,
        count(*) FILTER (WHERE channel = 'center') AS entries_center,
        count(*) FILTER (WHERE channel = 'right') AS entries_right
    FROM analytical.final_third_entries
    GROUP BY ALL
),
box AS (
    SELECT match_id, team_id, period, time_bin, count(*) AS box_entries
    FROM analytical.box_entries
    GROUP BY ALL
)
SELECT
    g.match_id, g.team_id, g.opponent_team_id, g.period, g.time_bin,
    g.bin_start_seconds, g.bin_end_seconds, g.bin_end_seconds - g.bin_start_seconds AS bin_seconds,
    coalesce(c.pass_attempts, 0) AS pass_attempts,
    coalesce(c.completed_passes, 0) AS completed_passes,
    coalesce(c.open_play_passes, 0) AS open_play_passes,
    coalesce(c.set_piece_passes, 0) AS set_piece_passes,
    coalesce(c.carries, 0) AS carries,
    coalesce(en.final_third_entries, 0) AS final_third_entries,
    coalesce(en.entries_left, 0) AS entries_left,
    coalesce(en.entries_center, 0) AS entries_center,
    coalesce(en.entries_right, 0) AS entries_right,
    coalesce(b.box_entries, 0) AS box_entries,
    coalesce(c.tilt_passes, 0) AS tilt_passes,
    coalesce(o.tilt_passes, 0) AS opponent_tilt_passes,
    CASE WHEN coalesce(c.tilt_passes, 0) + coalesce(o.tilt_passes, 0) > 0
        THEN coalesce(c.tilt_passes, 0) / (coalesce(c.tilt_passes, 0) + coalesce(o.tilt_passes, 0))
    END AS field_tilt,
    coalesce(c.shots, 0) AS shots,
    coalesce(c.open_play_shots, 0) AS open_play_shots,
    coalesce(c.provider_xg, 0) AS provider_xg,
    coalesce(c.open_play_provider_xg, 0) AS open_play_provider_xg,
    coalesce(c.goals, 0) AS goals,
    coalesce(c.pressures, 0) AS pressures,
    coalesce(c.ball_recoveries, 0) AS ball_recoveries,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM grid AS g
LEFT JOIN counts AS c USING (match_id, team_id, period, time_bin)
LEFT JOIN counts AS o
    ON o.match_id = g.match_id AND o.team_id = g.opponent_team_id
    AND o.period = g.period AND o.time_bin = g.time_bin
LEFT JOIN entries AS en USING (match_id, team_id, period, time_bin)
LEFT JOIN box AS b USING (match_id, team_id, period, time_bin);

-- Time on the pitch: the union of a player's position spells. Touching or overlapping spells
-- (provider lineups occasionally overlap) form one interval; a gap (for example a temporary
-- "Player Off") starts a new one. An open end means the final whistle; shootout time is excluded.
-- clock_key = period * 10000 + period seconds orders (period, seconds) pairs; it is never a
-- duration.
CREATE TABLE analytical.player_intervals AS
WITH match_end AS (
    SELECT match_id, max(period) AS last_period
    FROM analytical.periods WHERE NOT is_shootout GROUP BY match_id
),
bounded AS (
    SELECT
        s.match_id, s.team_id, s.player_id, s.spell_number,
        s.start_period, s.start_period_seconds::DECIMAL(8, 3) AS start_period_seconds,
        CASE WHEN s.end_period IS NULL OR s.end_period > me.last_period THEN me.last_period
            ELSE s.end_period END AS end_period,
        CASE WHEN s.end_period IS NULL OR s.end_period > me.last_period THEN final.end_seconds
            ELSE s.end_period_seconds::DECIMAL(8, 3) END AS end_period_seconds,
        s.start_reason, s.end_reason
    FROM normalized.position_spells AS s
    JOIN match_end AS me USING (match_id)
    JOIN analytical.periods AS final
        ON final.match_id = s.match_id AND final.period = me.last_period
    WHERE s.start_period <= me.last_period
        AND s.match_id IN (SELECT match_id FROM analytical.team_matches)
),
substituted_off AS (
    SELECT s.match_id, s.player_off_id AS player_id, min(e.period * 10000 + e.period_seconds) AS off_key
    FROM normalized.substitutions AS s
    JOIN normalized.events AS e ON e.event_id = s.event_id
    GROUP BY ALL
),
lineup_keyed AS (
    SELECT
        b.*,
        b.start_period * 10000 + b.start_period_seconds AS start_key,
        greatest(
            b.end_period * 10000 + b.end_period_seconds,
            b.start_period * 10000 + b.start_period_seconds
        ) AS lineup_end_key,
        o.off_key
    FROM bounded AS b
    LEFT JOIN substituted_off AS o USING (match_id, player_id)
),
-- A Substitution event is known when it happens; a lineup spell end is recorded afterwards.
-- When they disagree, the substitution event ends the spell (flagged by a quality warning).
keyed AS (
    SELECT
        * EXCLUDE (lineup_end_key, off_key),
        coalesce(lineup_end_key > off_key, false) AS cut_by_substitution,
        CASE WHEN lineup_end_key > off_key THEN off_key ELSE lineup_end_key END AS end_key
    FROM lineup_keyed
    WHERE off_key IS NULL OR start_key < off_key
),
ordered AS (
    SELECT
        *,
        max(end_key) OVER (
            PARTITION BY match_id, player_id ORDER BY start_key, spell_number
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS previous_end_key
    FROM keyed
),
numbered AS (
    SELECT
        *,
        sum(CASE WHEN start_key <= previous_end_key THEN 0 ELSE 1 END) OVER (
            PARTITION BY match_id, player_id ORDER BY start_key, spell_number
        )::INTEGER AS interval_number
    FROM ordered
)
SELECT
    match_id, team_id, player_id, interval_number,
    arg_min(start_period, [start_key, spell_number]) AS start_period,
    arg_min(start_period_seconds, [start_key, spell_number]) AS start_period_seconds,
    floor(arg_max(end_key, [end_key, spell_number]) / 10000)::INTEGER AS end_period,
    (arg_max(end_key, [end_key, spell_number]) % 10000)::DECIMAL(8, 3) AS end_period_seconds,
    arg_min(start_reason, [start_key, spell_number]) AS start_reason,
    arg_max(end_reason, [end_key, spell_number]) AS end_reason,
    bool_or(cut_by_substitution) AS cut_by_substitution,
    count(*) AS position_spells,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM numbered
GROUP BY match_id, team_id, player_id, interval_number;

-- Each interval split by period, for joining events and bins by (period, period_seconds).
CREATE TABLE analytical.player_period_spans AS
SELECT
    match_id, team_id, player_id, interval_number, period, span_start AS start_seconds,
    span_end AS end_seconds, span_end - span_start AS seconds_on_pitch,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM (
    SELECT
        i.match_id, i.team_id, i.player_id, i.interval_number, p.period,
        CASE WHEN p.period = i.start_period THEN i.start_period_seconds ELSE 0 END AS span_start,
        CASE WHEN p.period = i.end_period THEN i.end_period_seconds ELSE p.end_seconds END
            AS span_end
    FROM analytical.player_intervals AS i
    JOIN analytical.periods AS p
        ON p.match_id = i.match_id AND p.period BETWEEN i.start_period AND i.end_period
        AND NOT p.is_shootout
);

-- Per player and match: time on the pitch and involvement. pass_share is the player's pass
-- attempts divided by the team's pass attempts while the player was on the pitch.
CREATE TABLE analytical.player_match_involvement AS
WITH player_names AS (
    SELECT player_id, min(player_name) AS player_name FROM normalized.players GROUP BY player_id
),
on_pitch AS (
    SELECT match_id, player_id, sum(seconds_on_pitch) AS seconds_on_pitch
    FROM analytical.player_period_spans GROUP BY ALL
),
team_passes AS (
    SELECT s.match_id, s.player_id, count(*) AS team_pass_attempts_while_on
    FROM analytical.player_period_spans AS s
    JOIN analytical.event_context AS e
        ON e.match_id = s.match_id AND e.team_id = s.team_id AND e.period = s.period
        AND e.period_seconds BETWEEN s.start_seconds AND s.end_seconds
    WHERE e.event_type = 'pass'
    GROUP BY ALL
),
actions AS (
    SELECT
        match_id, player_id,
        count(*) FILTER (WHERE x IS NOT NULL) AS located_events,
        count(*) FILTER (WHERE event_type = 'pass') AS pass_attempts,
        count(*) FILTER (WHERE event_type = 'pass' AND completed) AS completed_passes,
        count(*) FILTER (WHERE event_type = 'carry') AS carries,
        count(*) FILTER (WHERE event_type = 'shot') AS shots,
        coalesce(sum(provider_xg), 0) AS provider_xg,
        count(*) FILTER (WHERE scores_goal AND event_type = 'shot') AS goals,
        count(*) FILTER (WHERE event_type = 'pressure') AS pressures,
        count(*) FILTER (WHERE event_type = 'ball_recovery') AS ball_recoveries
    FROM analytical.event_context
    WHERE player_id IS NOT NULL AND period <> 5
    GROUP BY ALL
),
entries AS (
    SELECT match_id, player_id, count(*) AS final_third_entries
    FROM analytical.final_third_entries GROUP BY ALL
),
box AS (
    SELECT match_id, player_id, count(*) AS box_entries
    FROM analytical.box_entries GROUP BY ALL
)
SELECT
    ap.match_id, ap.team_id, ap.player_id, n.player_name, ap.started,
    coalesce(op.seconds_on_pitch, 0) AS seconds_on_pitch,
    round(coalesce(op.seconds_on_pitch, 0) / 60, 1) AS minutes_on_pitch,
    coalesce(a.located_events, 0) AS located_events,
    coalesce(a.pass_attempts, 0) AS pass_attempts,
    coalesce(a.completed_passes, 0) AS completed_passes,
    coalesce(tp.team_pass_attempts_while_on, 0) AS team_pass_attempts_while_on,
    CASE WHEN tp.team_pass_attempts_while_on > 0
        THEN coalesce(a.pass_attempts, 0) / tp.team_pass_attempts_while_on END AS pass_share,
    coalesce(a.carries, 0) AS carries,
    coalesce(en.final_third_entries, 0) AS final_third_entries,
    coalesce(b.box_entries, 0) AS box_entries,
    coalesce(a.shots, 0) AS shots,
    coalesce(a.provider_xg, 0) AS provider_xg,
    coalesce(a.goals, 0) AS goals,
    coalesce(a.pressures, 0) AS pressures,
    coalesce(a.ball_recoveries, 0) AS ball_recoveries,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM normalized.appearances AS ap
JOIN analytical.team_matches AS tm ON tm.match_id = ap.match_id AND tm.team_id = ap.team_id
JOIN player_names AS n ON n.player_id = ap.player_id
LEFT JOIN on_pitch AS op ON op.match_id = ap.match_id AND op.player_id = ap.player_id
LEFT JOIN team_passes AS tp ON tp.match_id = ap.match_id AND tp.player_id = ap.player_id
LEFT JOIN actions AS a ON a.match_id = ap.match_id AND a.player_id = ap.player_id
LEFT JOIN entries AS en ON en.match_id = ap.match_id AND en.player_id = ap.player_id
LEFT JOIN box AS b ON b.match_id = ap.match_id AND b.player_id = ap.player_id;

-- Per player and 5-minute bin while on the pitch (including bins with no actions).
-- team_pass_attempts covers the whole bin, even if the player was on for part of it.
CREATE TABLE analytical.player_time_bins AS
WITH presence AS (
    SELECT
        s.match_id, s.team_id, s.player_id, b.period, b.time_bin,
        b.bin_start_seconds, b.bin_end_seconds,
        least(s.end_seconds, b.bin_end_seconds) - greatest(s.start_seconds, b.bin_start_seconds)
            AS seconds_on_pitch,
        b.pass_attempts AS team_pass_attempts
    FROM analytical.player_period_spans AS s
    JOIN analytical.team_time_bins AS b
        ON b.match_id = s.match_id AND b.team_id = s.team_id AND b.period = s.period
        AND s.start_seconds < b.bin_end_seconds AND s.end_seconds > b.bin_start_seconds
),
actions AS (
    SELECT
        match_id, player_id, period, time_bin,
        count(*) FILTER (WHERE x IS NOT NULL) AS located_events,
        count(*) FILTER (WHERE event_type = 'pass') AS pass_attempts,
        count(*) FILTER (WHERE event_type = 'pass' AND completed) AS completed_passes,
        count(*) FILTER (WHERE event_type = 'shot') AS shots,
        coalesce(sum(provider_xg), 0) AS provider_xg
    FROM analytical.event_context
    WHERE player_id IS NOT NULL
    GROUP BY ALL
)
SELECT
    p.match_id, p.team_id, p.player_id, p.period, p.time_bin,
    sum(p.seconds_on_pitch) AS seconds_on_pitch,
    any_value(p.team_pass_attempts) AS team_pass_attempts,
    coalesce(any_value(a.located_events), 0) AS located_events,
    coalesce(any_value(a.pass_attempts), 0) AS pass_attempts,
    coalesce(any_value(a.completed_passes), 0) AS completed_passes,
    CASE WHEN any_value(p.team_pass_attempts) > 0
        THEN coalesce(any_value(a.pass_attempts), 0) / any_value(p.team_pass_attempts)
    END AS pass_share,
    coalesce(any_value(a.shots), 0) AS shots,
    coalesce(any_value(a.provider_xg), 0) AS provider_xg,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM presence AS p
LEFT JOIN actions AS a
    ON a.match_id = p.match_id AND a.player_id = p.player_id
    AND a.period = p.period AND a.time_bin = p.time_bin
GROUP BY p.match_id, p.team_id, p.player_id, p.period, p.time_bin;

-- Possessions use the provider's possession grouping, which is hindsight: retrospective
-- research only, never a detector input. Measures count only the possessing team's events.
CREATE TABLE analytical.possessions AS
SELECT
    e.match_id, e.possession,
    arg_min(e.possession_team_id, e.sequence) AS team_id,
    min(e.sequence) AS first_sequence, max(e.sequence) AS last_sequence,
    arg_min(e.period, e.sequence) AS start_period,
    arg_min(e.period_seconds, e.sequence) AS start_seconds,
    arg_max(e.period, e.sequence) AS end_period,
    arg_max(e.period_seconds, e.sequence) AS end_seconds,
    CASE WHEN start_period = end_period THEN end_seconds - start_seconds END AS duration_seconds,
    count(*) AS events,
    count(*) FILTER (WHERE c.team_id = e.possession_team_id AND c.event_type = 'pass')
        AS pass_attempts,
    max(greatest(c.x, CASE WHEN c.completed THEN c.end_x END))
        FILTER (WHERE c.team_id = e.possession_team_id) AS furthest_x,
    coalesce(furthest_x >= 80, false) AS reached_final_third,
    count(*) FILTER (WHERE c.team_id = e.possession_team_id AND c.event_type = 'shot') AS shots,
    coalesce(sum(c.provider_xg) FILTER (WHERE c.team_id = e.possession_team_id), 0)
        AS provider_xg,
    count(*) FILTER (WHERE c.scores_goal) AS goals,
    arg_min(c.score_state, e.sequence) FILTER (WHERE c.team_id = e.possession_team_id)
        AS start_score_state,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM normalized.events AS e
JOIN analytical.event_context AS c ON c.event_id = e.event_id
WHERE e.possession IS NOT NULL
GROUP BY e.match_id, e.possession;

-- Per-match team totals, for exploration and data-quality checks. Never a baseline for how
-- unusual an in-match spell is. Shootout events are excluded (bins cover periods 1-4).
CREATE TABLE analytical.team_match_summary AS
WITH totals AS (
    SELECT
        match_id, team_id,
        sum(pass_attempts) AS pass_attempts, sum(completed_passes) AS completed_passes,
        sum(open_play_passes) AS open_play_passes, sum(set_piece_passes) AS set_piece_passes,
        sum(carries) AS carries,
        sum(final_third_entries) AS final_third_entries,
        sum(entries_left) AS entries_left, sum(entries_center) AS entries_center,
        sum(entries_right) AS entries_right, sum(box_entries) AS box_entries,
        sum(tilt_passes) AS tilt_passes, sum(opponent_tilt_passes) AS opponent_tilt_passes,
        sum(shots) AS shots, sum(open_play_shots) AS open_play_shots,
        sum(provider_xg) AS provider_xg, sum(open_play_provider_xg) AS open_play_provider_xg,
        sum(goals) AS goals_from_events,
        sum(pressures) AS pressures, sum(ball_recoveries) AS ball_recoveries
    FROM analytical.team_time_bins
    GROUP BY ALL
),
possession_counts AS (
    SELECT match_id, team_id, count(*) AS possessions
    FROM analytical.possessions GROUP BY ALL
)
SELECT
    tm.match_id, tm.competition_id, tm.season_id, tm.match_date, tm.team_id, tm.team_name,
    tm.is_home, tm.opponent_team_id, tm.opponent_name, tm.goals_for, tm.goals_against,
    t.* EXCLUDE (match_id, team_id),
    t.completed_passes / nullif(t.pass_attempts, 0) AS pass_completion,
    t.tilt_passes / nullif(t.tilt_passes + t.opponent_tilt_passes, 0) AS field_tilt,
    coalesce(pc.possessions, 0) AS possessions,
    1 AS definition_version, getvariable('ingest_run_id') AS ingest_run_id
FROM analytical.team_matches AS tm
JOIN totals AS t USING (match_id, team_id)
LEFT JOIN possession_counts AS pc USING (match_id, team_id);

CREATE TABLE analytical.definitions AS
SELECT *, getvariable('ingest_run_id') AS ingest_run_id
FROM (VALUES
    ('team_matches', 1, 'One row per team per included match; goals are the final score (hindsight).'),
    ('periods', 1, 'Period end = latest period-end event or event timestamp; period 5 is a shootout.'),
    ('score_states', 1, 'Home and away goals before each event by sequence; shootout goals excluded.'),
    ('event_context', 1, 'Events with thirds (x 40/80), channels (y 80/3, 160/3), 6 x 5 zones of 20 x 16, box x >= 102 and 18 <= y <= 62, open play, completion, provider xG, score before the event.'),
    ('final_third_entries', 1, 'Locked AGENTS.md definition: open-play completed pass or carry from x < 80 to x >= 80; channel from the end location.'),
    ('box_entries', 1, 'Provisional, owner review pending: open-play completed pass or carry from outside to inside the penalty area.'),
    ('team_time_bins', 1, 'Full grid of 5-minute bins per team and period (1-4); field_tilt = team tilt passes / both teams, no minimum applied.'),
    ('player_intervals', 1, 'Union of position spells (touching or overlapping spells merge), cut at the player''s Substitution event when the lineup runs past it; open ends close at the final regular period end.'),
    ('player_period_spans', 1, 'Player intervals split by period.'),
    ('player_match_involvement', 1, 'pass_share = player pass attempts / team pass attempts while the player was on the pitch.'),
    ('player_time_bins', 1, 'Player presence per team bin; team_pass_attempts covers the whole bin.'),
    ('possessions', 1, 'Provider possession grouping (hindsight); measures use the possessing team only.'),
    ('team_match_summary', 1, 'Whole-match totals summed from team_time_bins; exploration and data quality only.')
) AS d(table_name, definition_version, definition);
