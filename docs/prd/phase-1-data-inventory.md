# Phase 1 Data Inventory (Match Intelligence)

## Status: COMPLETE

Last updated: 2026-01-24

## Data Coverage Summary

| Data Type | Coverage | Source | Notes |
|-----------|----------|--------|-------|
| Fixtures | 380/380 (100%) | FBRef | 2025-26 Premier League |
| Lineups | 358/380 (94%) | Transfermarkt | Formations + starting XI |
| Odds | 220/380 (58%) | Football-Data.co.uk | Opening + closing prices |
| Injuries | 3,337 records | Transfermarkt | 481 players, 20 teams |
| TM Mappings | 358/380 (94%) | Transfermarkt | Fixture-to-match ID links |
| xG/Stats | Via FBRef | FBRef | Post-match only |
| Elo Ratings | Full season | ClubElo | Daily ratings |

---

## Current Sources

### 1. FBRef (Fixtures + xG)
- **File**: `src/ingestion/scraper.py`
- **Output**: fixtures + xG for finished matches
- **Coverage**: Premier League 2025-2026
- **Status**: Working
- **Notes**: Relies on headless Chrome; can hit 403/captcha

### 2. Transfermarkt - Injuries
- **File**: `src/ingestion/transfermarkt_injuries.py`
- **Output**: `player_injuries_historical` table
- **Coverage**: 3,337 injury records across 20 PL teams
- **Status**: COMPLETE
- **Fields**: player_id, player_name, team, injury_type, from_date, end_date, days_missed, games_missed

### 3. Transfermarkt - Lineups
- **File**: `src/ingestion/transfermarkt_lineups.py`
- **Output**: `lineups_historical` table
- **Coverage**: 358/380 fixtures (94%)
- **Status**: COMPLETE
- **Fields**: fixture_id, formation, starters (JSONB), bench (JSONB)
- **Backfill Script**: `scripts/backfill_lineups.py`

### 4. Transfermarkt - Match ID Mappings
- **File**: `src/ingestion/transfermarkt_match_ids.py`
- **Output**: `tm_match_mapping` table
- **Coverage**: 358/380 fixtures (94%)
- **Status**: COMPLETE
- **Build Script**: `scripts/build_tm_mappings.py`

### 5. Football-Data.co.uk - Odds
- **File**: `scripts/download_odds_historical.py`
- **Output**: `odds_snapshots` table
- **Coverage**: 220/380 fixtures (58% - remaining are future matches)
- **Status**: COMPLETE
- **Fields**: fixture_id, market_key (1X2), selection_key, odds_decimal, captured_at, source
- **Sources**: Opening odds (48h pre-match), Closing odds (1h pre-match)

### 6. Understat (Tactical Enrichment)
- **File**: `src/ingestion/understat_enrich.py`
- **Output**: PPDA + Field Tilt
- **Coverage**: Premier League 2025-2026
- **Status**: Working
- **Notes**: API JSON endpoint; name mapping for team alignment

### 7. ClubElo (Rating Backfill)
- **File**: `src/ingestion/elo_backfill.py`
- **Output**: `team_elo` table
- **Coverage**: EPL (Country = ENG filter)
- **Status**: Working
- **Notes**: Mapping table required; fills missing Elo rows

---

## Context Builder Integration

The context builder (`src/analysis/context_builder_v2.py`) now integrates all data sources:

```python
# Example context for Liverpool vs Bournemouth
{
    "home": {
        "identity": {"name": "Liverpool", "elo": 1985},
        "absences": {
            "total_missing": 3,
            "players": [
                {"player_name": "Alexander Isak", "injury_type": "Fitness"},
                {"player_name": "Conor Bradley", "injury_type": "Hamstring injury"}
            ]
        },
        "lineup": {
            "formation": "4-2-3-1",
            "starters": ["Alisson", "Konaté", "van Dijk", ...]
        }
    },
    "odds": {
        "home_win": 1.29,
        "draw": 6.28,
        "away_win": 8.79,
        "source": "football-data-open"
    }
}
```

---

## Gaps (Resolved)

| Gap | Status | Resolution |
|-----|--------|------------|
| Injuries/suspensions | RESOLVED | Transfermarkt scraper |
| Lineups/expected XI | RESOLVED | Transfermarkt spielbericht pages |
| Historical odds | RESOLVED | Football-Data.co.uk CSV import |
| TM match ID mapping | RESOLVED | Matchday page scraping |

---

## Remaining Gaps

| Gap | Notes |
|-----|-------|
| Future match odds | Available closer to kickoff (football-data updates weekly) |
| 22 fixtures without TM mapping | Promoted teams with incomplete data |
| Real-time lineup updates | Would require match-day scraping |
| Suspensions | Not explicitly tracked (only injuries) |

---

## Reliability Notes

- **Transfermarkt**: 2.0-2.5s delay between requests to avoid rate limiting
- **Football-Data.co.uk**: No rate limits, CSV files updated weekly
- **FBRef**: Can fail due to Cloudflare blocking or DOM changes
- **ClubElo**: Unauthenticated API, may rate-limit

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/backfill_injuries.py` | Scrape injury data for all PL teams |
| `scripts/build_tm_mappings.py` | Map fixtures to Transfermarkt match IDs |
| `scripts/backfill_lineups.py` | Scrape lineup data for mapped fixtures |
| `scripts/download_odds_historical.py` | Download/import odds from football-data.co.uk |
