-- ============================================
-- CLARITY ENGINE - Knowledge Graph Tables
-- Temporal states for teams and players
-- ============================================

-- Drop if exists (for clean recreation)
DROP TABLE IF EXISTS player_states CASCADE;
DROP TABLE IF EXISTS team_states CASCADE;
DROP TABLE IF EXISTS teams CASCADE;
DROP TABLE IF EXISTS players CASCADE;

-- ============================================
-- TEAMS (canonical team registry)
-- ============================================
CREATE TABLE teams (
    team_id INTEGER PRIMARY KEY,
    team_name TEXT NOT NULL,
    short_name TEXT,
    league_id INTEGER DEFAULT 47,  -- Premier League
    created_at TIMESTAMP DEFAULT now()
);

-- ============================================
-- PLAYERS (canonical player registry)
-- ============================================
CREATE TABLE players (
    player_id INTEGER PRIMARY KEY,
    player_name TEXT NOT NULL,
    current_team_id INTEGER REFERENCES teams(team_id),
    position TEXT,
    created_at TIMESTAMP DEFAULT now()
);

-- ============================================
-- TEAM_STATES (state per team per round)
-- This is the core of the KG
-- ============================================
CREATE TABLE team_states (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    round_number INTEGER NOT NULL,
    as_of_date DATE,
    
    -- POSITION LAYER
    position INTEGER,
    points INTEGER DEFAULT 0,
    played INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    goal_difference INTEGER DEFAULT 0,
    
    -- FORM LAYER (last 5 games)
    form_string TEXT,              -- "WWDLW"
    form_points INTEGER DEFAULT 0, -- out of 15
    goals_scored_last5 INTEGER DEFAULT 0,
    goals_conceded_last5 INTEGER DEFAULT 0,
    clean_sheets_last5 INTEGER DEFAULT 0,
    
    -- xG LAYER (last 5 games)
    xg_for_last5 DECIMAL(5,2) DEFAULT 0,
    xg_against_last5 DECIMAL(5,2) DEFAULT 0,
    xg_diff_last5 DECIMAL(5,2) DEFAULT 0,
    
    -- STYLE LAYER
    avg_possession DECIMAL(4,1),
    primary_formation TEXT,
    
    -- ATTACK LAYER (averages)
    shots_per_game DECIMAL(4,1),
    shots_on_target_per_game DECIMAL(4,1),
    xg_per_game DECIMAL(4,2),
    big_chances_per_game DECIMAL(4,1),
    
    -- DEFENSE LAYER (averages)
    shots_against_per_game DECIMAL(4,1),
    xg_against_per_game DECIMAL(4,2),
    
    -- MOMENTUM LAYER
    form_trend TEXT,               -- "improving", "stable", "declining"
    position_change_last5 INTEGER DEFAULT 0,
    
    -- HOME/AWAY SPLITS
    home_wins INTEGER DEFAULT 0,
    home_draws INTEGER DEFAULT 0,
    home_losses INTEGER DEFAULT 0,
    away_wins INTEGER DEFAULT 0,
    away_draws INTEGER DEFAULT 0,
    away_losses INTEGER DEFAULT 0,
    home_points INTEGER DEFAULT 0,
    away_points INTEGER DEFAULT 0,
    
    -- META
    computed_at TIMESTAMP DEFAULT now(),
    
    UNIQUE(team_id, round_number)
);

CREATE INDEX idx_team_states_team ON team_states(team_id);
CREATE INDEX idx_team_states_round ON team_states(round_number);
CREATE INDEX idx_team_states_position ON team_states(round_number, position);

-- ============================================
-- PLAYER_STATES (state per player per round)
-- ============================================
CREATE TABLE player_states (
    id SERIAL PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    team_id INTEGER NOT NULL REFERENCES teams(team_id),
    round_number INTEGER NOT NULL,
    as_of_date DATE,
    
    -- SEASON TOTALS (up to this round)
    appearances INTEGER DEFAULT 0,
    starts INTEGER DEFAULT 0,
    minutes INTEGER DEFAULT 0,
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    xg_total DECIMAL(5,2) DEFAULT 0,
    xa_total DECIMAL(5,2) DEFAULT 0,
    
    -- FORM LAYER (last 5 games)
    goals_last5 INTEGER DEFAULT 0,
    assists_last5 INTEGER DEFAULT 0,
    xg_last5 DECIMAL(4,2) DEFAULT 0,
    xa_last5 DECIMAL(4,2) DEFAULT 0,
    minutes_last5 INTEGER DEFAULT 0,
    avg_rating_last5 DECIMAL(3,1),
    
    -- SEASON AVERAGES
    avg_rating_season DECIMAL(3,1),
    goals_per_90 DECIMAL(4,2),
    assists_per_90 DECIMAL(4,2),
    xg_per_90 DECIMAL(4,2),
    
    -- META
    computed_at TIMESTAMP DEFAULT now(),
    
    UNIQUE(player_id, round_number)
);

CREATE INDEX idx_player_states_player ON player_states(player_id);
CREATE INDEX idx_player_states_team ON player_states(team_id);
CREATE INDEX idx_player_states_round ON player_states(round_number);

-- ============================================
-- Verification queries
-- ============================================
-- After running populate script, verify with:
-- SELECT COUNT(*) FROM teams;  -- Should be 20
-- SELECT COUNT(*) FROM team_states;  -- Should be 20 * 26 = 520
-- SELECT * FROM team_states WHERE team_id = 8650 ORDER BY round_number;  -- Liverpool progression
