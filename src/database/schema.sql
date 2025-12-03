-- 1. FIXTURES (The Hub)
DROP TABLE IF EXISTS market_odds;
DROP TABLE IF EXISTS team_stats;
DROP TABLE IF EXISTS fixtures;
-- We drop the view first if it exists to avoid errors when recreating tables it depends on
DROP VIEW IF EXISTS team_performance_view;

CREATE TABLE fixtures (
    id TEXT PRIMARY KEY,              -- ID: "2024-08-17_Arsenal_Wolves"
    date DATE NOT NULL,
    season TEXT NOT NULL,             -- "2024-2025"
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score INT,
    away_score INT,
    status TEXT DEFAULT 'SCHEDULED',  -- 'FINISHED', 'SCHEDULED', 'POSTPONED'
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

CREATE INDEX idx_fixtures_date ON fixtures(date);
CREATE INDEX idx_stats_team ON team_stats(team_name);

-- 4. ANALYTICAL VIEW (The "Smart" Layer)
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