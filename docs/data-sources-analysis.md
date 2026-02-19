# Data Sources Analysis & Improvement Plan

## Current Situation (from phase-1-data-inventory.md)

### Active Data Sources
1. **FBRef** (Selenium scraper)
   - File: [src/ingestion/scraper.py](src/ingestion/scraper.py)
   - Data: Fixtures + xG for finished matches
   - Coverage: Premier League only (2025-2026)
   - Issues: Cloudflare blocking, captcha, DOM changes, headless Chrome dependency

2. **Understat** (API enrichment)
   - File: [src/ingestion/understat_enrich.py](src/ingestion/understat_enrich.py)
   - Data: PPDA + Field Tilt
   - Coverage: Premier League only
   - Issues: Team name mapping, may miss promotions/renames

3. **ClubElo** (Rating backfill)
   - File: [src/ingestion/elo_backfill.py](src/ingestion/elo_backfill.py)
   - Data: Elo ratings per team/date
   - Coverage: EPL only
   - Issues: Unauthenticated, may rate-limit

4. **Manual Odds Import**
   - File: [scripts/import_odds_csv.py](scripts/import_odds_csv.py)
   - Data: 1X2 odds
   - Issues: Requires manual CSV availability

### Critical Data Gaps
- ❌ Injuries / suspensions
- ❌ Lineups / expected XI
- ❌ Form and trend features beyond xG
- ❌ Scheduling context (rest days, travel)
- ❌ Limited tactical style data
- ❌ Multi-league support

## Installed But Not Used: soccerdata Library

### Status
- **Installed**: soccerdata==1.8.7 in requirements.txt
- **Used**: ❌ NO - Not imported anywhere in codebase
- **Working**: ❌ NO - Has dependency issue (missing distutils)

### Error Encountered
```
ModuleNotFoundError: No module named 'distutils'
```
This is because Python 3.12 removed distutils, but undetected-chromedriver (a soccerdata dependency) still uses it.

### Fix Required
```bash
pip install setuptools  # Provides distutils for Python 3.12+
```

## Why soccerdata is Superior

### Multi-Source Unified API
The library wraps **10+ data sources** with a consistent pandas DataFrame interface:

1. **FBref** - Match stats, player stats, shooting, passing, possession
2. **Understat** - xG data, shots data, match stats
3. **WhoScored** - Detailed match events and player ratings
4. **SoFIFA** - FIFA player ratings and attributes
5. **Sofascore** - Match results, lineups, player stats
6. **FotMob** - Match details, lineups, player performance
7. **ESPN** - Schedules, results, standings
8. **ClubElo** - Historical Elo ratings
9. **FiveThirtyEight** - Predictions and ratings
10. **Football-Data.co.uk** - Historical odds and results

### Key Advantages Over Current Setup

#### 1. No More Selenium Headaches
- Uses HTTP requests where possible (faster, more reliable)
- Only uses Selenium when absolutely necessary
- Built-in anti-blocking measures
- Automatic retry logic

#### 2. Consistent Data Format
- All sources return pandas DataFrames
- Matching column names across datasets
- Standardized team identifiers
- Easy to merge data from multiple sources

#### 3. Built-in Caching
- Automatic data caching to avoid rate limits
- Faster subsequent runs
- Configurable cache directory

#### 4. Much More Data Available

**Currently Missing Data That soccerdata Provides:**

##### Lineups & Team Selection
```python
import soccerdata as sd
fotmob = sd.FotMob(leagues='ENG-Premier League', seasons='2425')
lineups = fotmob.read_lineup()  # Starting XIs, formations, substitutions
```

##### Detailed Player Performance
```python
fbref = sd.FBref(leagues='ENG-Premier League', seasons='2425')
player_stats = fbref.read_player_season_stats()  # Goals, assists, xG, xA, etc.
passing = fbref.read_player_season_stats(stat_type='passing')
shooting = fbref.read_player_season_stats(stat_type='shooting')
```

##### Injuries (via FotMob/Sofascore)
```python
fotmob = sd.FotMob(leagues='ENG-Premier League', seasons='2425')
team_overview = fotmob.read_team_overview()  # Includes injury status
```

##### Match Events & Shot Maps
```python
understat = sd.Understat(leagues='EPL', seasons='2024')
shots = understat.read_shot_data()  # Every shot with xG, location, situation
```

##### Odds from Multiple Bookmakers
```python
fd = sd.FootballData(leagues='ENG-Premier League', seasons='2425')
odds = fd.read_odds()  # Multiple bookmakers, closing odds, etc.
```

#### 5. Multi-League Support Out of the Box
```python
# Easy to expand beyond Premier League
fbref = sd.FBref(
    leagues=['ENG-Premier League', 'ESP-La Liga', 'GER-Bundesliga'],
    seasons=['2425']
)
```

## Recommended Implementation Plan

### Phase 1: Fix & Test soccerdata (Priority: HIGH)

1. **Fix Dependency Issue**
   ```bash
   pip install setuptools
   # Update requirements.txt to include it
   ```

2. **Create Test Script**
   Create `scripts/test_soccerdata.py` to verify:
   - FBref fixture data retrieval
   - Understat xG/tactical data
   - FotMob lineup data
   - Sofascore injury data
   - Football-Data.co.uk odds

3. **Compare Data Quality**
   - Run current scrapers vs soccerdata
   - Compare coverage, freshness, reliability
   - Identify which sources to migrate

### Phase 2: Migrate Core Data Pipelines

1. **Replace FBRef Selenium Scraper**
   - Create `src/ingestion/soccerdata_fbref.py`
   - Much faster and more reliable than Selenium
   - Can get more detailed stats (passing, shooting, possession)

2. **Replace Understat Scraper**
   - Use `sd.Understat()` instead of manual API calls
   - Better error handling
   - Consistent with other sources

3. **Enhanced ClubElo**
   - Use `sd.ClubElo()` for better coverage
   - Already built-in team name mapping

### Phase 3: Add Missing Critical Data

1. **Lineups & Expected XI**
   ```python
   fotmob = sd.FotMob(leagues='ENG-Premier League', seasons='2425')
   lineups = fotmob.read_lineup()
   ```

2. **Injuries & Suspensions**
   ```python
   sofascore = sd.SoFIFA(leagues='ENG-Premier League')
   # Or use FotMob team overview
   ```

3. **Better Odds Coverage**
   ```python
   fd = sd.FootballData(leagues='ENG-Premier League', seasons='2425')
   odds = fd.read_odds()  # Multiple bookmakers
   ```

4. **Shot Maps & Detailed Events**
   ```python
   understat = sd.Understat(leagues='EPL', seasons='2024')
   shots = understat.read_shot_data()
   ```

### Phase 4: Multi-League Expansion
- Use soccerdata's unified interface
- Add La Liga, Bundesliga, Serie A, Ligue 1
- Single codebase handles all leagues

## Quick Win: Sample soccerdata Script

Here's what a modern ingestion script would look like:

```python
import soccerdata as sd
import pandas as pd
from datetime import datetime

def fetch_comprehensive_match_data(league='ENG-Premier League', season='2425'):
    """
    Get ALL relevant match data using soccerdata.
    Much more data than current scrapers with less fragility.
    """

    # Basic match data
    fbref = sd.FBref(leagues=league, seasons=season)
    fixtures = fbref.read_schedule()  # Replaces current scraper.py

    # xG and tactical
    understat = sd.Understat(leagues='EPL', seasons='2024')
    xg_data = understat.read_league_table()  # PPDA, xG, etc.
    shots = understat.read_shot_data()  # Every shot with location

    # Lineups (NEW - not currently available)
    fotmob = sd.FotMob(leagues=league, seasons=season)
    lineups = fotmob.read_lineup()

    # Odds from multiple bookmakers (NEW - better than manual CSV)
    fd = sd.FootballData(leagues=league, seasons=season)
    odds = fd.read_odds()

    # Elo ratings
    clubelo = sd.ClubElo(leagues=league)
    elo = clubelo.read_by_date()

    return {
        'fixtures': fixtures,
        'xg_data': xg_data,
        'shots': shots,
        'lineups': lineups,
        'odds': odds,
        'elo': elo
    }
```

## Immediate Next Steps

1. ✅ **Fix soccerdata** - Add setuptools to requirements
2. ✅ **Create test script** - Verify data quality
3. ✅ **Pilot migration** - Start with FBref replacement
4. ✅ **Add lineups** - Critical missing feature
5. ✅ **Add injuries** - Critical missing feature
6. ✅ **Better odds** - Replace manual CSV
7. ✅ **Multi-league** - Easy expansion path

## Conclusion

**Current State**: Fragile Selenium scrapers, limited data, single league, missing critical features

**With soccerdata**: 10+ data sources, unified API, more reliable, much more data, multi-league ready

**ROI**: High - Library is already installed, just needs dependency fix and migration scripts

The soccerdata library solves nearly all the gaps mentioned in phase-1-data-inventory.md and provides a much more maintainable, scalable foundation for data ingestion.
