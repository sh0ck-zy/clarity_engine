-- Migration 002: Add league_id to team_states
-- Required for multi-league support (Portuguese + Brazilian leagues)
--
-- Run with: psql -d clarity_football -f scripts/migrations/002_add_league_id_team_states.sql

-- Add league_id column (default 47 = Premier League for existing rows)
ALTER TABLE team_states ADD COLUMN IF NOT EXISTS league_id INT NOT NULL DEFAULT 47;

-- Drop old unique constraint and create new one including league_id
ALTER TABLE team_states DROP CONSTRAINT IF EXISTS team_states_team_id_round_number_key;
ALTER TABLE team_states ADD CONSTRAINT team_states_team_league_round_key
    UNIQUE(team_id, round_number, league_id);

-- Index for league-filtered queries
CREATE INDEX IF NOT EXISTS idx_team_states_league ON team_states(league_id);

-- Also add league_id to player_states for consistency
ALTER TABLE player_states ADD COLUMN IF NOT EXISTS league_id INT NOT NULL DEFAULT 47;
ALTER TABLE player_states DROP CONSTRAINT IF EXISTS player_states_player_id_round_number_key;
ALTER TABLE player_states ADD CONSTRAINT player_states_player_league_round_key
    UNIQUE(player_id, round_number, league_id);
