-- Drop order matters: view -> child tables -> parent tables.
DROP VIEW IF EXISTS team_performance_view;
DROP TABLE IF EXISTS analysis_evaluations;
DROP TABLE IF EXISTS match_reality;
DROP TABLE IF EXISTS analysis_reports;
DROP TABLE IF EXISTS market_odds;
DROP TABLE IF EXISTS team_stats;
DROP TABLE IF EXISTS fixtures;
DROP TABLE IF EXISTS lineup_strength_metrics;
DROP TABLE IF EXISTS injury_impact_metrics;
DROP TABLE IF EXISTS player_impact_metrics;
DROP TABLE IF EXISTS player_market_values;
DROP TABLE IF EXISTS player_injuries_historical;
DROP TABLE IF EXISTS player_season_stats;
DROP TABLE IF EXISTS player_match_stats;
DROP TABLE IF EXISTS team_match_stats;
DROP TABLE IF EXISTS injuries_historical;
DROP TABLE IF EXISTS lineups_historical;
DROP TABLE IF EXISTS match_features;
DROP TABLE IF EXISTS match_outcomes;
DROP TABLE IF EXISTS odds_snapshots;
DROP TABLE IF EXISTS fixtures_historical;

CREATE TABLE fixtures (
    id TEXT PRIMARY KEY,              -- ID: "2024-08-17_Arsenal_Wolves"
    date DATE NOT NULL,
    season TEXT NOT NULL,             -- "2024-2025"
    league TEXT DEFAULT 'Premier League',  -- League name
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score INT,
    away_score INT,
    status TEXT DEFAULT 'SCHEDULED',  -- 'FINISHED', 'SCHEDULED', 'POSTPONED'
    "round" INT,                      -- Gameweek number
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. TEAM STATS (The Spokes)
CREATE TABLE team_stats (
    fixture_id TEXT REFERENCES fixtures(id) ON DELETE CASCADE,
    team_name TEXT NOT NULL,
    is_home BOOLEAN NOT NULL,
    xg DECIMAL(4,2),
    xga DECIMAL(4,2),
    ppda DECIMAL(4,1),
    field_tilt DECIMAL(4,1),
    raw_json JSONB,
    elo INT,                  -- Latest Elo before match
    PRIMARY KEY (fixture_id, team_name)
);

-- 3. MARKET ODDS (Context)
CREATE TABLE market_odds (
    fixture_id TEXT REFERENCES fixtures(id) ON DELETE CASCADE,
    home_win DECIMAL(5,2),
    draw DECIMAL(5,2),
    away_win DECIMAL(5,2),
    provider TEXT DEFAULT 'Unknown',
    PRIMARY KEY (fixture_id)
);

CREATE TABLE odds_snapshots (
    id SERIAL PRIMARY KEY,
    fixture_id TEXT REFERENCES fixtures_historical(fixture_id) ON DELETE CASCADE,
    market_key TEXT NOT NULL,
    selection_key TEXT NOT NULL,
    odds_decimal DECIMAL(8,4) NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    source TEXT DEFAULT 'manual_csv',
    data_source TEXT NOT NULL DEFAULT 'manual_csv',
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_fixtures_date ON fixtures(date);
CREATE INDEX idx_odds_fixture ON odds_snapshots(fixture_id);
CREATE INDEX idx_odds_market ON odds_snapshots(market_key, selection_key);
CREATE INDEX idx_odds_captured_at ON odds_snapshots(captured_at);
CREATE INDEX idx_fixtures_league ON fixtures(league);
CREATE INDEX idx_stats_team ON team_stats(team_name);

-- Historical data tables (time-travel safe)
CREATE TABLE IF NOT EXISTS fixtures_historical (
    fixture_id TEXT PRIMARY KEY,
    league_id INT,
    season INT,
    round TEXT,
    date TIMESTAMP NOT NULL,
    venue TEXT,
    home_team_id INT NOT NULL,
    away_team_id INT NOT NULL,
    home_score INT,
    away_score INT,
    status TEXT,
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lineups_historical (
    fixture_id TEXT REFERENCES fixtures_historical(fixture_id) ON DELETE CASCADE,
    team_id INT NOT NULL,
    formation TEXT,
    lineup_type TEXT NOT NULL,
    players JSONB NOT NULL,
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (fixture_id, team_id, lineup_type)
);

CREATE TABLE IF NOT EXISTS injuries_historical (
    fixture_id TEXT REFERENCES fixtures_historical(fixture_id) ON DELETE CASCADE,
    player_id INT NOT NULL,
    injury_type TEXT,
    reason TEXT,
    expected_return DATE,
    valid_at TIMESTAMP NOT NULL,
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (fixture_id, player_id, valid_at)
);

CREATE TABLE IF NOT EXISTS team_match_stats (
    fixture_id TEXT REFERENCES fixtures_historical(fixture_id) ON DELETE CASCADE,
    team_id INT NOT NULL,
    is_home BOOLEAN NOT NULL,
    season INT NOT NULL,
    league_id INT NOT NULL,
    xg DECIMAL(6,3),
    xga DECIMAL(6,3),
    shots INT,
    possession DECIMAL(5,2),
    ppda DECIMAL(6,3),
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (fixture_id, team_id)
);

CREATE TABLE IF NOT EXISTS player_match_stats (
    fixture_id TEXT REFERENCES fixtures_historical(fixture_id) ON DELETE CASCADE,
    team_id INT NOT NULL,
    player_id INT NOT NULL,
    season INT NOT NULL,
    league_id INT NOT NULL,
    minutes INT,
    position TEXT,
    xg DECIMAL(6,3),
    xa DECIMAL(6,3),
    shots INT,
    key_passes INT,
    progressive_passes INT,
    progressive_carries INT,
    tackles INT,
    interceptions INT,
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (fixture_id, player_id)
);

CREATE TABLE IF NOT EXISTS player_season_stats (
    player_id INT NOT NULL,
    team_id INT NOT NULL,
    season INT NOT NULL,
    league_id INT NOT NULL,
    minutes INT,
    position TEXT,
    xg DECIMAL(6,3),
    xa DECIMAL(6,3),
    shots INT,
    key_passes INT,
    progressive_passes INT,
    progressive_carries INT,
    tackles INT,
    interceptions INT,
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (player_id, season, league_id)
);

CREATE TABLE IF NOT EXISTS player_market_values (
    player_id INT NOT NULL,
    market_value_eur DECIMAL(12,2),
    valuation_date DATE NOT NULL,
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (player_id, valuation_date)
);

CREATE TABLE IF NOT EXISTS player_injuries_historical (
    player_id INT NOT NULL,
    season TEXT,
    injury_reason TEXT,
    from_date DATE NOT NULL,
    end_date DATE,
    days_missed INT,
    games_missed INT,
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (player_id, from_date, injury_reason)
);

CREATE TABLE IF NOT EXISTS player_impact_metrics (
    player_id INT NOT NULL,
    season INT NOT NULL,
    league_id INT NOT NULL,
    minutes INT,
    xg_per90 DECIMAL(7,3),
    xa_per90 DECIMAL(7,3),
    key_passes_per90 DECIMAL(7,3),
    progressive_passes_per90 DECIMAL(7,3),
    tackles_per90 DECIMAL(7,3),
    interceptions_per90 DECIMAL(7,3),
    offensive_impact DECIMAL(7,3),
    defensive_impact DECIMAL(7,3),
    replacement_player_id INT,
    replacement_delta JSONB,
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (player_id, season, league_id)
);

CREATE TABLE IF NOT EXISTS injury_impact_metrics (
    fixture_id TEXT REFERENCES fixtures_historical(fixture_id) ON DELETE CASCADE,
    team_id INT NOT NULL,
    offensive_impact DECIMAL(7,3),
    defensive_impact DECIMAL(7,3),
    adjusted_xg DECIMAL(7,3),
    adjusted_xga DECIMAL(7,3),
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (fixture_id, team_id)
);

CREATE TABLE IF NOT EXISTS lineup_strength_metrics (
    fixture_id TEXT REFERENCES fixtures_historical(fixture_id) ON DELETE CASCADE,
    team_id INT NOT NULL,
    avg_player_rating DECIMAL(6,3),
    total_market_value DECIMAL(12,2),
    offensive_strength DECIMAL(7,3),
    defensive_strength DECIMAL(7,3),
    bench_strength DECIMAL(7,3),
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (fixture_id, team_id)
);

CREATE TABLE IF NOT EXISTS match_outcomes (
    fixture_id TEXT REFERENCES fixtures_historical(fixture_id) ON DELETE CASCADE,
    home_score INT,
    away_score INT,
    home_xg DECIMAL(6,3),
    away_xg DECIMAL(6,3),
    result TEXT,
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (fixture_id)
);

CREATE TABLE IF NOT EXISTS match_features (
    fixture_id TEXT REFERENCES fixtures_historical(fixture_id) ON DELETE CASCADE,
    season INT NOT NULL,
    league_id INT NOT NULL,
    feature_key TEXT NOT NULL,
    feature_value DECIMAL(10,4),
    computed_at TIMESTAMP DEFAULT NOW(),
    data_source TEXT NOT NULL,
    ingested_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (fixture_id, feature_key)
);

CREATE INDEX IF NOT EXISTS idx_fixtures_historical_date ON fixtures_historical(date);
CREATE INDEX IF NOT EXISTS idx_fixtures_historical_season_league ON fixtures_historical(season, league_id);
CREATE INDEX IF NOT EXISTS idx_lineups_historical_fixture ON lineups_historical(fixture_id);
CREATE INDEX IF NOT EXISTS idx_lineups_historical_team ON lineups_historical(team_id);
CREATE INDEX IF NOT EXISTS idx_injuries_historical_fixture ON injuries_historical(fixture_id);
CREATE INDEX IF NOT EXISTS idx_injuries_historical_player ON injuries_historical(player_id);
CREATE INDEX IF NOT EXISTS idx_team_match_stats_fixture ON team_match_stats(fixture_id);
CREATE INDEX IF NOT EXISTS idx_team_match_stats_team ON team_match_stats(team_id);
CREATE INDEX IF NOT EXISTS idx_team_match_stats_season_league ON team_match_stats(season, league_id);
CREATE INDEX IF NOT EXISTS idx_player_match_stats_fixture ON player_match_stats(fixture_id);
CREATE INDEX IF NOT EXISTS idx_player_match_stats_player ON player_match_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_match_stats_team ON player_match_stats(team_id);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_player ON player_season_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_team ON player_season_stats(team_id);
CREATE INDEX IF NOT EXISTS idx_player_season_stats_season_league ON player_season_stats(season, league_id);
CREATE INDEX IF NOT EXISTS idx_player_market_values_player ON player_market_values(player_id);
CREATE INDEX IF NOT EXISTS idx_player_injuries_historical_player ON player_injuries_historical(player_id);
CREATE INDEX IF NOT EXISTS idx_player_impact_metrics_player ON player_impact_metrics(player_id);
CREATE INDEX IF NOT EXISTS idx_injury_impact_metrics_fixture ON injury_impact_metrics(fixture_id);
CREATE INDEX IF NOT EXISTS idx_lineup_strength_metrics_fixture ON lineup_strength_metrics(fixture_id);
CREATE INDEX IF NOT EXISTS idx_match_features_fixture ON match_features(fixture_id);
CREATE INDEX IF NOT EXISTS idx_match_features_season_league ON match_features(season, league_id);

-- 3b. ANALYSIS REPORTS (LLM Cache)
CREATE TABLE analysis_reports (
    id SERIAL PRIMARY KEY,
    fixture_id TEXT REFERENCES fixtures(id) ON DELETE CASCADE,

    -- Metadata
    prompt_version TEXT NOT NULL,     -- e.g. "hybrid", "contrarian"
    model_name TEXT NOT NULL,         -- e.g. "gpt-4o"
    created_at TIMESTAMP DEFAULT NOW(),

    -- Outputs (Structured for fast SQL queries)
    headline TEXT,
    predicted_score TEXT,
    confidence INT,
    betting_recommendation TEXT,

    -- Logic Storage (For Glass Box transparency)
    weights JSONB,

    -- The Full Payload (Crucial for the Dashboard to re-render)
    full_json JSONB,

    -- Validation (Filled later)
    actual_score TEXT,
    is_correct BOOLEAN,
    pnl DECIMAL(6,2)
);

CREATE INDEX idx_reports_fixture ON analysis_reports(fixture_id);
CREATE INDEX idx_reports_version ON analysis_reports(prompt_version);

-- 4. MATCH REALITY (Post-match forensic audit)
CREATE TABLE IF NOT EXISTS match_reality (
    fixture_id TEXT PRIMARY KEY REFERENCES fixtures(id) ON DELETE CASCADE,
    score_home INT,
    score_away INT,
    xg_home DECIMAL(4,2),
    xg_away DECIMAL(4,2),
    possession_home DECIMAL(4,1),
    key_events JSONB,
    narrative_summary TEXT,
    luck_factor TEXT,
    source_type TEXT DEFAULT 'forensic_auditor',
    created_at TIMESTAMP DEFAULT NOW()
);

-- 5. ANALYSIS EVALUATIONS (AI evaluation of predictions vs reality)
CREATE TABLE IF NOT EXISTS analysis_evaluations (
    id SERIAL PRIMARY KEY,
    report_id INT NOT NULL UNIQUE REFERENCES analysis_reports(id) ON DELETE CASCADE,
    fixture_id TEXT NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
    prompt_version TEXT NOT NULL,
    
    -- Dimensão 1: Narrative Quality
    narrative_score INT, -- 0-100
    narrative_feedback TEXT,
    narrative_critical_flags JSONB, -- ["missed_key_event", "overemphasized_factor"]
    
    -- Dimensão 2: Score Prediction
    score_accuracy BOOLEAN,
    score_explanation TEXT,
    
    -- Dimensão 3: Betting Tip
    tip_accuracy BOOLEAN,
    tip_explanation TEXT,
    
    -- Meta
    evaluation_json JSONB, -- Full response
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evaluations_fixture ON analysis_evaluations(fixture_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_prompt ON analysis_evaluations(prompt_version);
CREATE INDEX IF NOT EXISTS idx_evaluations_report ON analysis_evaluations(report_id);

-- ============================================================
-- FOTMOB TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS fotmob_matches (
    fotmob_match_id   INT PRIMARY KEY,
    league_id         INT NOT NULL DEFAULT 47,
    season            TEXT NOT NULL,
    round_number      INT,
    match_date        DATE NOT NULL,
    kickoff_time      TIMESTAMP,
    home_team_id      INT NOT NULL,
    home_team_name    TEXT NOT NULL,
    away_team_id      INT NOT NULL,
    away_team_name    TEXT NOT NULL,
    home_score        INT,
    away_score        INT,
    ht_home_score     INT,
    ht_away_score     INT,
    status            TEXT NOT NULL,
    venue             TEXT,
    attendance        INT,
    referee           TEXT,
    formation_home    TEXT,
    formation_away    TEXT,
    events            JSONB,
    stats             JSONB,
    home_lineup       JSONB,
    away_lineup       JSONB,
    shotmap           JSONB,
    commentary        JSONB,
    match_facts       JSONB,
    momentum          JSONB,
    home_avg_rating   DECIMAL(4,2),
    away_avg_rating   DECIMAL(4,2),
    motm_player_id    INT,
    motm_player_name  TEXT,
    raw_json          JSONB NOT NULL,
    fetched_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    clarity_fixture_id TEXT
);

CREATE TABLE IF NOT EXISTS fotmob_player_performances (
    id SERIAL PRIMARY KEY,
    fotmob_match_id   INT REFERENCES fotmob_matches(fotmob_match_id) ON DELETE CASCADE,
    player_id         INT,
    player_name       TEXT NOT NULL,
    team_id           INT,
    team_name         TEXT NOT NULL,
    is_home           BOOLEAN,
    is_starter        BOOLEAN,
    position_id       INT,
    shirt_number      TEXT,
    rating            DECIMAL(3,1),
    minutes_played    INT,
    goals             INT DEFAULT 0,
    assists           INT DEFAULT 0,
    xg                DECIMAL(5,3),
    xgot              DECIMAL(5,3),
    xa                DECIMAL(5,3),
    shots             INT,
    shots_on_target   INT,
    passes            INT,
    passes_accurate   INT,
    chances_created   INT,
    tackles           INT,
    interceptions     INT,
    defensive_actions INT,
    fantasy_score     TEXT,
    sub_in_minute     INT,
    sub_out_minute    INT,
    stats_json        JSONB,
    UNIQUE(fotmob_match_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_fpp_match ON fotmob_player_performances(fotmob_match_id);
CREATE INDEX IF NOT EXISTS idx_fpp_player ON fotmob_player_performances(player_id);
CREATE INDEX IF NOT EXISTS idx_fpp_player_name ON fotmob_player_performances(player_name);
CREATE INDEX IF NOT EXISTS idx_fpp_rating ON fotmob_player_performances(rating);
CREATE INDEX IF NOT EXISTS idx_fpp_team ON fotmob_player_performances(team_name);
CREATE INDEX IF NOT EXISTS idx_fotmob_matches_date ON fotmob_matches(match_date);
CREATE INDEX IF NOT EXISTS idx_fotmob_matches_round ON fotmob_matches(round_number);
CREATE INDEX IF NOT EXISTS idx_fotmob_matches_season ON fotmob_matches(season);

-- 6. ANALYTICAL VIEW (The "Smart" Layer)
-- This is the block you were asking for!
-- It joins the Hub (fixtures) and Spoke (stats) and does the math.
CREATE OR REPLACE VIEW team_performance_view AS
SELECT 
    t.fixture_id,
    f.date,
    f.season,
    t.team_name,
    t.is_home,
    f.home_team,
    f.away_team,
    -- The Core Metrics
    t.xg,
    t.xga,
    t.ppda,
    t.field_tilt,
    -- The Calculated Metrics (The DB does this for you)
    (t.xg - t.xga) AS xg_diff,
    -- Simple Points Calculation (3 for win, 1 draw, 0 loss)
    CASE 
        WHEN (t.is_home AND f.home_score > f.away_score) OR (NOT t.is_home AND f.away_score > f.home_score) THEN 3
        WHEN f.home_score = f.away_score THEN 1
        ELSE 0
    END AS points_earned
FROM team_stats t
JOIN fixtures f ON t.fixture_id = f.id;
