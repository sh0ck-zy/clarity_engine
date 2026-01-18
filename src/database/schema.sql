-- Drop order matters: view -> child tables -> parent tables.
DROP VIEW IF EXISTS team_performance_view;
DROP TABLE IF EXISTS analysis_evaluations;
DROP TABLE IF EXISTS match_reality;
DROP TABLE IF EXISTS analysis_reports;
DROP TABLE IF EXISTS market_odds;
DROP TABLE IF EXISTS odds_snapshots;
DROP TABLE IF EXISTS team_stats;
DROP TABLE IF EXISTS fixtures;

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
    fixture_id TEXT REFERENCES fixtures(id) ON DELETE CASCADE,
    market_key TEXT NOT NULL,
    selection_key TEXT NOT NULL,
    odds_decimal DECIMAL(8,4) NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    source TEXT DEFAULT 'manual_csv'
);

CREATE INDEX idx_fixtures_date ON fixtures(date);
CREATE INDEX idx_odds_fixture ON odds_snapshots(fixture_id);
CREATE INDEX idx_odds_market ON odds_snapshots(market_key, selection_key);
CREATE INDEX idx_odds_captured_at ON odds_snapshots(captured_at);
CREATE INDEX idx_fixtures_league ON fixtures(league);
CREATE INDEX idx_stats_team ON team_stats(team_name);

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
