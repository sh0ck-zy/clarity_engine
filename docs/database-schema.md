# Database Schema

This document reflects the historical schema defined in src/database/schema.sql.

## Historical data (time-travel safe)

### fixtures_historical
- fixture_id (TEXT, PK)
- league_id (INT)
- season (INT)
- round (TEXT)
- date (TIMESTAMP)
- venue (TEXT)
- home_team_id (INT)
- away_team_id (INT)
- home_score (INT)
- away_score (INT)
- status (TEXT)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_fixtures_historical_date (date)
- idx_fixtures_historical_season_league (season, league_id)

### lineups_historical
- fixture_id (TEXT, FK fixtures_historical)
- team_id (INT)
- formation (TEXT)
- lineup_type (TEXT)
- players (JSONB)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_lineups_historical_fixture (fixture_id)
- idx_lineups_historical_team (team_id)

### injuries_historical
- fixture_id (TEXT, FK fixtures_historical)
- player_id (INT)
- injury_type (TEXT)
- reason (TEXT)
- expected_return (DATE)
- valid_at (TIMESTAMP)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_injuries_historical_fixture (fixture_id)
- idx_injuries_historical_player (player_id)

### team_match_stats
- fixture_id (TEXT, FK fixtures_historical)
- team_id (INT)
- is_home (BOOLEAN)
- season (INT)
- league_id (INT)
- xg (DECIMAL)
- xga (DECIMAL)
- shots (INT)
- possession (DECIMAL)
- ppda (DECIMAL)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_team_match_stats_fixture (fixture_id)
- idx_team_match_stats_team (team_id)
- idx_team_match_stats_season_league (season, league_id)

### player_match_stats
- fixture_id (TEXT, FK fixtures_historical)
- team_id (INT)
- player_id (INT)
- season (INT)
- league_id (INT)
- minutes (INT)
- position (TEXT)
- xg (DECIMAL)
- xa (DECIMAL)
- shots (INT)
- key_passes (INT)
- progressive_passes (INT)
- progressive_carries (INT)
- tackles (INT)
- interceptions (INT)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_player_match_stats_fixture (fixture_id)
- idx_player_match_stats_player (player_id)
- idx_player_match_stats_team (team_id)

### player_season_stats
- player_id (INT)
- team_id (INT)
- season (INT)
- league_id (INT)
- minutes (INT)
- position (TEXT)
- xg (DECIMAL)
- xa (DECIMAL)
- shots (INT)
- key_passes (INT)
- progressive_passes (INT)
- progressive_carries (INT)
- tackles (INT)
- interceptions (INT)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_player_season_stats_player (player_id)
- idx_player_season_stats_team (team_id)
- idx_player_season_stats_season_league (season, league_id)

### player_market_values
- player_id (INT)
- market_value_eur (DECIMAL)
- valuation_date (DATE)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_player_market_values_player (player_id)

### player_injuries_historical
- player_id (INT)
- season (TEXT)
- injury_reason (TEXT)
- from_date (DATE)
- end_date (DATE)
- days_missed (INT)
- games_missed (INT)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_player_injuries_historical_player (player_id)

### player_impact_metrics
- player_id (INT)
- season (INT)
- league_id (INT)
- minutes (INT)
- xg_per90 (DECIMAL)
- xa_per90 (DECIMAL)
- key_passes_per90 (DECIMAL)
- progressive_passes_per90 (DECIMAL)
- tackles_per90 (DECIMAL)
- interceptions_per90 (DECIMAL)
- offensive_impact (DECIMAL)
- defensive_impact (DECIMAL)
- replacement_player_id (INT)
- replacement_delta (JSONB)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_player_impact_metrics_player (player_id)

### injury_impact_metrics
- fixture_id (TEXT, FK fixtures_historical)
- team_id (INT)
- offensive_impact (DECIMAL)
- defensive_impact (DECIMAL)
- adjusted_xg (DECIMAL)
- adjusted_xga (DECIMAL)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_injury_impact_metrics_fixture (fixture_id)

### lineup_strength_metrics
- fixture_id (TEXT, FK fixtures_historical)
- team_id (INT)
- avg_player_rating (DECIMAL)
- total_market_value (DECIMAL)
- offensive_strength (DECIMAL)
- defensive_strength (DECIMAL)
- bench_strength (DECIMAL)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_lineup_strength_metrics_fixture (fixture_id)

### match_outcomes
- fixture_id (TEXT, FK fixtures_historical)
- home_score (INT)
- away_score (INT)
- home_xg (DECIMAL)
- away_xg (DECIMAL)
- result (TEXT)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

### match_features
- fixture_id (TEXT, FK fixtures_historical)
- season (INT)
- league_id (INT)
- feature_key (TEXT)
- feature_value (DECIMAL)
- computed_at (TIMESTAMP)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_match_features_fixture (fixture_id)
- idx_match_features_season_league (season, league_id)

## Odds snapshots

### odds_snapshots
- id (SERIAL, PK)
- fixture_id (TEXT, FK fixtures_historical)
- market_key (TEXT)
- selection_key (TEXT)
- odds_decimal (DECIMAL)
- captured_at (TIMESTAMP)
- source (TEXT)
- data_source (TEXT)
- ingested_at (TIMESTAMP)
- updated_at (TIMESTAMP)

Indexes:
- idx_odds_fixture (fixture_id)
- idx_odds_market (market_key, selection_key)
- idx_odds_captured_at (captured_at)
