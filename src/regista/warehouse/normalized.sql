-- Normalized layer: Regista-owned tables, one row per provider fact.
-- Every table ends with ingest_run_id, the run and code version that produced it.
-- Field availability (known_at_event, delayed, hindsight) is in normalized.field_availability.
CREATE SCHEMA normalized;

CREATE TABLE normalized.ingest_runs (
    ingest_run_id VARCHAR PRIMARY KEY,
    regista_version VARCHAR NOT NULL,
    git_commit VARCHAR NOT NULL,
    git_dirty BOOLEAN NOT NULL,
    adapter_version VARCHAR NOT NULL,
    duckdb_version VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    source_commit VARCHAR NOT NULL,
    split_version INTEGER NOT NULL,
    split_sha256 VARCHAR NOT NULL,
    selection VARCHAR NOT NULL,
    selected_matches INTEGER NOT NULL,
    normalized_matches INTEGER NOT NULL,
    excluded_matches INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    status VARCHAR NOT NULL
);

CREATE TABLE normalized.raw_files (
    provider VARCHAR NOT NULL,
    dataset VARCHAR NOT NULL,
    source_commit VARCHAR NOT NULL,
    relative_path VARCHAR PRIMARY KEY,
    url VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    provider_match_id BIGINT,
    sha256 VARCHAR NOT NULL,
    bytes BIGINT NOT NULL,
    retrieved_at VARCHAR NOT NULL,
    provider_last_updated VARCHAR,
    license_class VARCHAR NOT NULL,
    split_bucket VARCHAR,
    split_sha256 VARCHAR,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.splits (
    split_version INTEGER NOT NULL,
    provider VARCHAR NOT NULL,
    competition_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    match_id BIGINT NOT NULL,
    bucket VARCHAR NOT NULL,
    human_review BOOLEAN NOT NULL,
    ingest_run_id VARCHAR NOT NULL,
    PRIMARY KEY (split_version, match_id)
);

CREATE TABLE normalized.competition_seasons (
    provider VARCHAR NOT NULL,
    competition_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    competition_name VARCHAR,
    season_name VARCHAR,
    role VARCHAR NOT NULL,
    coverage VARCHAR NOT NULL,
    expected_matches INTEGER NOT NULL,
    known_missing_matches INTEGER NOT NULL,
    catalog_matches INTEGER NOT NULL,
    development_matches INTEGER NOT NULL,
    validation_matches INTEGER NOT NULL,
    test_matches INTEGER NOT NULL,
    ingested_matches INTEGER NOT NULL,
    ingest_run_id VARCHAR NOT NULL,
    PRIMARY KEY (competition_id, season_id)
);

CREATE TABLE normalized.matches (
    provider VARCHAR NOT NULL,
    match_id BIGINT PRIMARY KEY,
    competition_id INTEGER NOT NULL,
    season_id INTEGER NOT NULL,
    match_date DATE NOT NULL,
    kickoff TIME NOT NULL,
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    home_score INTEGER NOT NULL,
    away_score INTEGER NOT NULL,
    match_week INTEGER,
    stage VARCHAR,
    stadium VARCHAR,
    data_version VARCHAR,
    xy_fidelity_version VARCHAR,
    shot_fidelity_version VARCHAR,
    provider_last_updated VARCHAR,
    has_three_sixty BOOLEAN NOT NULL,
    events_sha256 VARCHAR,
    lineups_sha256 VARCHAR,
    dq_status VARCHAR,
    provider_record JSON NOT NULL,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.teams (
    provider VARCHAR NOT NULL,
    team_id INTEGER NOT NULL,
    team_name VARCHAR NOT NULL,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.players (
    provider VARCHAR NOT NULL,
    player_id INTEGER NOT NULL,
    player_name VARCHAR NOT NULL,
    player_nickname VARCHAR,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.appearances (
    match_id BIGINT NOT NULL,
    team_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    jersey_number INTEGER,
    started BOOLEAN NOT NULL,
    provider_record JSON NOT NULL,
    ingest_run_id VARCHAR NOT NULL,
    PRIMARY KEY (match_id, player_id)
);

CREATE TABLE normalized.position_spells (
    match_id BIGINT NOT NULL,
    team_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    spell_number INTEGER NOT NULL,
    position VARCHAR NOT NULL,
    start_period INTEGER NOT NULL,
    start_period_seconds INTEGER NOT NULL,
    end_period INTEGER,
    end_period_seconds INTEGER,
    start_reason VARCHAR NOT NULL,
    end_reason VARCHAR NOT NULL,
    ingest_run_id VARCHAR NOT NULL,
    PRIMARY KEY (match_id, player_id, spell_number)
);

-- The spine. Replay order is sequence, never the timestamp.
CREATE TABLE normalized.events (
    provider VARCHAR NOT NULL,
    match_id BIGINT NOT NULL,
    event_id VARCHAR PRIMARY KEY,
    sequence INTEGER NOT NULL,
    period INTEGER NOT NULL,
    period_seconds DECIMAL(8, 3) NOT NULL,
    minute INTEGER NOT NULL,
    second INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    player_id INTEGER,
    position VARCHAR,
    possession INTEGER,
    possession_team_id INTEGER,
    event_type VARCHAR NOT NULL,
    provider_event_type VARCHAR NOT NULL,
    x DOUBLE,
    y DOUBLE,
    end_x DOUBLE,
    end_y DOUBLE,
    under_pressure BOOLEAN NOT NULL,
    source VARCHAR NOT NULL,
    provider_record JSON NOT NULL,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.passes (
    match_id BIGINT NOT NULL,
    event_id VARCHAR PRIMARY KEY,
    recipient_player_id INTEGER,
    completed BOOLEAN NOT NULL,
    outcome VARCHAR,
    pass_type VARCHAR,
    set_piece_type VARCHAR,
    open_play BOOLEAN NOT NULL,
    height VARCHAR,
    is_cross BOOLEAN NOT NULL,
    is_shot_assist BOOLEAN NOT NULL,
    is_goal_assist BOOLEAN NOT NULL,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.carries (
    match_id BIGINT NOT NULL,
    event_id VARCHAR PRIMARY KEY,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.shots (
    match_id BIGINT NOT NULL,
    event_id VARCHAR PRIMARY KEY,
    provider_xg DOUBLE,
    outcome VARCHAR NOT NULL,
    is_goal BOOLEAN NOT NULL,
    shot_type VARCHAR NOT NULL,
    body_part VARCHAR,
    key_pass_event_id VARCHAR,
    end_x DOUBLE,
    end_y DOUBLE,
    end_z DOUBLE,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.substitutions (
    match_id BIGINT NOT NULL,
    event_id VARCHAR PRIMARY KEY,
    team_id INTEGER NOT NULL,
    player_off_id INTEGER NOT NULL,
    player_on_id INTEGER NOT NULL,
    reason VARCHAR,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.formation_changes (
    match_id BIGINT NOT NULL,
    event_id VARCHAR PRIMARY KEY,
    team_id INTEGER NOT NULL,
    formation VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.goals (
    match_id BIGINT NOT NULL,
    event_id VARCHAR PRIMARY KEY,
    scoring_team_id INTEGER NOT NULL,
    kind VARCHAR NOT NULL,
    in_shootout BOOLEAN NOT NULL,
    ingest_run_id VARCHAR NOT NULL
);

CREATE TABLE normalized.field_availability (
    table_name VARCHAR NOT NULL,
    column_name VARCHAR NOT NULL,
    availability VARCHAR NOT NULL,
    note VARCHAR NOT NULL,
    ingest_run_id VARCHAR NOT NULL,
    PRIMARY KEY (table_name, column_name)
);

CREATE TABLE normalized.dq_checks (
    match_id BIGINT NOT NULL,
    check_name VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    passed BOOLEAN NOT NULL,
    detail VARCHAR NOT NULL,
    ingest_run_id VARCHAR NOT NULL,
    PRIMARY KEY (match_id, check_name)
);
