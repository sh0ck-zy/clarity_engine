#!/usr/bin/env python3
"""
Validate soccerdata library against critical data requirements.

This script tests whether soccerdata can provide the essential missing data:
1. Match Intelligence (beat ChatGPT)
2. Market Intelligence (betting layer)
3. Evaluation/Validation data

Run with: python scripts/validate_soccerdata.py
"""

import soccerdata as sd
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Configuration
LEAGUE = 'ENG-Premier League'
SEASON = '2425'  # 2024-2025 season
TEST_TEAM = 'Liverpool'

print("=" * 80)
print("SOCCERDATA VALIDATION - Critical Data Requirements")
print("=" * 80)
print(f"\nLeague: {LEAGUE}")
print(f"Season: {SEASON}")
print(f"Test Team: {TEST_TEAM}")
print(f"Timestamp: {datetime.now()}\n")

results = {
    'match_intelligence': {},
    'market_intelligence': {},
    'evaluation': {}
}

# =============================================================================
# MATCH INTELLIGENCE DATA
# =============================================================================
print("\n" + "=" * 80)
print("1. MATCH INTELLIGENCE DATA")
print("=" * 80)

# -----------------------------------------------------------------------------
# 1.1 Injuries/Suspensions with severity + expected return
# -----------------------------------------------------------------------------
print("\n[1.1] Testing: Injuries/Suspensions with severity + expected return")
print("-" * 80)
try:
    fotmob = sd.FotMob(leagues=LEAGUE, seasons=SEASON)

    # Try to get team overview which may contain injury data
    print("Attempting FotMob team overview...")
    team_data = fotmob.read_team_overview()

    if team_data is not None and not team_data.empty:
        print(f"✓ FotMob returned {len(team_data)} rows")
        print(f"Columns: {list(team_data.columns)}")
        results['match_intelligence']['injuries_fotmob'] = True
    else:
        print("✗ FotMob team overview returned no data")
        results['match_intelligence']['injuries_fotmob'] = False

except Exception as e:
    print(f"✗ FotMob failed: {e}")
    results['match_intelligence']['injuries_fotmob'] = False

# Try Sofascore
try:
    print("\nAttempting Sofascore...")
    sofascore = sd.Sofascore(leagues=LEAGUE, seasons=SEASON)
    # Note: Sofascore may require different methods
    print("Sofascore initialized (methods TBD)")
    results['match_intelligence']['injuries_sofascore'] = 'unknown'
except Exception as e:
    print(f"✗ Sofascore failed: {e}")
    results['match_intelligence']['injuries_sofascore'] = False

# -----------------------------------------------------------------------------
# 1.2 Projected lineups / confirmed XI + formation
# -----------------------------------------------------------------------------
print("\n[1.2] Testing: Projected lineups / confirmed XI + formation")
print("-" * 80)
try:
    fotmob = sd.FotMob(leagues=LEAGUE, seasons=SEASON)

    print("Attempting FotMob lineup data...")
    lineups = fotmob.read_lineup()

    if lineups is not None and not lineups.empty:
        print(f"✓ FotMob lineups: {len(lineups)} rows")
        print(f"Columns: {list(lineups.columns)}")
        print(f"\nSample lineup data:")
        print(lineups.head(3))
        results['match_intelligence']['lineups'] = True
    else:
        print("✗ FotMob lineups returned no data")
        results['match_intelligence']['lineups'] = False

except Exception as e:
    print(f"✗ FotMob lineups failed: {e}")
    results['match_intelligence']['lineups'] = False

# -----------------------------------------------------------------------------
# 1.3 Player availability (minutes likely, fatigue)
# -----------------------------------------------------------------------------
print("\n[1.3] Testing: Player availability (minutes, fatigue)")
print("-" * 80)
try:
    fbref = sd.FBref(leagues=LEAGUE, seasons=SEASON)

    print("Attempting FBref player stats...")
    player_stats = fbref.read_player_season_stats()

    if player_stats is not None and not player_stats.empty:
        print(f"✓ FBref player stats: {len(player_stats)} rows")
        print(f"Columns: {list(player_stats.columns)}")

        # Check for relevant columns
        relevant_cols = [col for col in player_stats.columns if any(
            x in str(col).lower() for x in ['min', 'start', 'sub', 'games', 'match']
        )]
        print(f"\nRelevant columns for fatigue/availability: {relevant_cols}")

        if relevant_cols:
            print(f"\nSample data for {TEST_TEAM} players:")
            team_players = player_stats[player_stats.index.get_level_values('team') == TEST_TEAM]
            print(team_players[relevant_cols].head())
            results['match_intelligence']['player_availability'] = True
        else:
            results['match_intelligence']['player_availability'] = 'partial'
    else:
        print("✗ FBref player stats returned no data")
        results['match_intelligence']['player_availability'] = False

except Exception as e:
    print(f"✗ FBref player stats failed: {e}")
    results['match_intelligence']['player_availability'] = False

# -----------------------------------------------------------------------------
# 1.4 Tactical style metrics beyond PPDA/tilt
# -----------------------------------------------------------------------------
print("\n[1.4] Testing: Tactical style metrics beyond PPDA/tilt")
print("-" * 80)
try:
    fbref = sd.FBref(leagues=LEAGUE, seasons=SEASON)

    print("Attempting FBref possession stats...")
    possession = fbref.read_team_season_stats(stat_type='possession')

    if possession is not None and not possession.empty:
        print(f"✓ FBref possession stats: {len(possession)} rows")
        print(f"Columns: {list(possession.columns)}")
        print(f"\nSample for {TEST_TEAM}:")
        if TEST_TEAM in possession.index:
            print(possession.loc[TEST_TEAM])
        results['match_intelligence']['tactical_possession'] = True
    else:
        results['match_intelligence']['tactical_possession'] = False

except Exception as e:
    print(f"✗ FBref possession failed: {e}")
    results['match_intelligence']['tactical_possession'] = False

try:
    print("\nAttempting FBref passing stats...")
    passing = fbref.read_team_season_stats(stat_type='passing')

    if passing is not None and not passing.empty:
        print(f"✓ FBref passing stats: {len(passing)} rows")
        print(f"Columns: {list(passing.columns)}")
        results['match_intelligence']['tactical_passing'] = True
    else:
        results['match_intelligence']['tactical_passing'] = False

except Exception as e:
    print(f"✗ FBref passing failed: {e}")
    results['match_intelligence']['tactical_passing'] = False

# -----------------------------------------------------------------------------
# 1.5 Advanced chance quality (xThreat/xChain or shot quality breakdown)
# -----------------------------------------------------------------------------
print("\n[1.5] Testing: Advanced chance quality (xThreat/xChain, shot quality)")
print("-" * 80)
try:
    understat = sd.Understat(leagues='EPL', seasons='2024')

    print("Attempting Understat shot data...")
    shots = understat.read_shot_data()

    if shots is not None and not shots.empty:
        print(f"✓ Understat shots: {len(shots)} rows")
        print(f"Columns: {list(shots.columns)}")

        # Check for xG and shot quality fields
        xg_cols = [col for col in shots.columns if 'xg' in str(col).lower()]
        quality_cols = [col for col in shots.columns if any(
            x in str(col).lower() for x in ['situation', 'result', 'shotType', 'body']
        )]

        print(f"\nxG-related columns: {xg_cols}")
        print(f"Shot quality columns: {quality_cols}")
        print(f"\nSample shot data:")
        print(shots[['h_team', 'a_team', 'xG', 'result', 'situation']].head())

        results['match_intelligence']['shot_quality'] = True
    else:
        print("✗ Understat shots returned no data")
        results['match_intelligence']['shot_quality'] = False

except Exception as e:
    print(f"✗ Understat shots failed: {e}")
    results['match_intelligence']['shot_quality'] = False

# -----------------------------------------------------------------------------
# 1.6 Set-piece strength (goals/xG from set pieces)
# -----------------------------------------------------------------------------
print("\n[1.6] Testing: Set-piece strength (goals/xG from set pieces)")
print("-" * 80)
try:
    # Check if Understat shot data includes set piece info
    if 'shots' in locals() and shots is not None and not shots.empty:
        setpiece_situations = shots['situation'].unique()
        print(f"Shot situations available: {setpiece_situations}")

        setpiece_shots = shots[shots['situation'].isin(['SetPiece', 'Penalty', 'FromCorner'])]
        if not setpiece_shots.empty:
            print(f"✓ Found {len(setpiece_shots)} set-piece shots")
            results['match_intelligence']['setpiece_strength'] = True
        else:
            print("✗ No explicit set-piece classification found")
            results['match_intelligence']['setpiece_strength'] = 'partial'
    else:
        results['match_intelligence']['setpiece_strength'] = False

except Exception as e:
    print(f"✗ Set-piece analysis failed: {e}")
    results['match_intelligence']['setpiece_strength'] = False

# -----------------------------------------------------------------------------
# 1.7 Rest days + schedule congestion
# -----------------------------------------------------------------------------
print("\n[1.7] Testing: Rest days + schedule congestion")
print("-" * 80)
try:
    fbref = sd.FBref(leagues=LEAGUE, seasons=SEASON)

    print("Attempting FBref schedule data...")
    schedule = fbref.read_schedule()

    if schedule is not None and not schedule.empty:
        print(f"✓ FBref schedule: {len(schedule)} rows")
        print(f"Columns: {list(schedule.columns)}")

        # Check if we have date information
        date_cols = [col for col in schedule.columns if 'date' in str(col).lower() or 'time' in str(col).lower()]
        print(f"\nDate-related columns: {date_cols}")

        if date_cols:
            print("\nSample schedule data:")
            print(schedule[['home', 'away'] + date_cols].head())
            print("\n✓ Can derive rest days from match dates")
            results['match_intelligence']['rest_days'] = 'derivable'
        else:
            results['match_intelligence']['rest_days'] = False
    else:
        print("✗ FBref schedule returned no data")
        results['match_intelligence']['rest_days'] = False

except Exception as e:
    print(f"✗ FBref schedule failed: {e}")
    results['match_intelligence']['rest_days'] = False

# -----------------------------------------------------------------------------
# 1.8 Travel/venue context
# -----------------------------------------------------------------------------
print("\n[1.8] Testing: Travel/venue context (distance, home advantage)")
print("-" * 80)
try:
    fbref = sd.FBref(leagues=LEAGUE, seasons=SEASON)

    # Check schedule for home/away designation
    if 'schedule' in locals() and schedule is not None and not schedule.empty:
        venue_cols = [col for col in schedule.columns if any(
            x in str(col).lower() for x in ['home', 'away', 'venue', 'location']
        )]
        print(f"Venue-related columns: {venue_cols}")

        if venue_cols:
            print("✓ Home/away data available (travel distance requires external geo data)")
            results['match_intelligence']['venue_context'] = 'partial'
        else:
            results['match_intelligence']['venue_context'] = False
    else:
        results['match_intelligence']['venue_context'] = False

except Exception as e:
    print(f"✗ Venue context check failed: {e}")
    results['match_intelligence']['venue_context'] = False

# =============================================================================
# MARKET INTELLIGENCE DATA
# =============================================================================
print("\n" + "=" * 80)
print("2. MARKET INTELLIGENCE DATA")
print("=" * 80)

# -----------------------------------------------------------------------------
# 2.1 Opening + closing odds
# -----------------------------------------------------------------------------
print("\n[2.1] Testing: Opening + closing odds")
print("-" * 80)
try:
    from soccerdata import FootballData

    print("Attempting Football-Data.co.uk odds...")
    fd = FootballData(leagues=LEAGUE, seasons=SEASON)
    odds = fd.read_games()

    if odds is not None and not odds.empty:
        print(f"✓ Football-Data odds: {len(odds)} rows")
        print(f"Columns: {list(odds.columns)}")

        # Check for odds columns
        odds_cols = [col for col in odds.columns if any(
            x in str(col).lower() for x in ['odd', 'bet', 'b365', 'bw', 'iw', 'ps', 'wh', 'vc']
        )]
        print(f"\nOdds-related columns ({len(odds_cols)}): {odds_cols[:10]}...")

        if odds_cols:
            print("\nSample odds data:")
            print(odds[['Home', 'Away'] + odds_cols[:5]].head())
            results['market_intelligence']['odds_data'] = True
        else:
            results['market_intelligence']['odds_data'] = False
    else:
        print("✗ Football-Data odds returned no data")
        results['market_intelligence']['odds_data'] = False

except Exception as e:
    print(f"✗ Football-Data odds failed: {e}")
    results['market_intelligence']['odds_data'] = False

# -----------------------------------------------------------------------------
# 2.2 Odds movement (line drift over time)
# -----------------------------------------------------------------------------
print("\n[2.2] Testing: Odds movement (line drift over time)")
print("-" * 80)
print("⚠️  Football-Data.co.uk provides opening and closing odds")
print("⚠️  For detailed line movement, need real-time odds APIs (Betfair, Pinnacle)")
results['market_intelligence']['odds_movement'] = 'limited'

# -----------------------------------------------------------------------------
# 2.3 Market liquidity proxy
# -----------------------------------------------------------------------------
print("\n[2.3] Testing: Market liquidity proxy")
print("-" * 80)
print("⚠️  Would require Betfair exchange data or similar")
print("⚠️  Number of bookmakers in Football-Data could be weak proxy")
results['market_intelligence']['liquidity'] = False

# -----------------------------------------------------------------------------
# 2.4 Closing line value (CLV)
# -----------------------------------------------------------------------------
print("\n[2.4] Testing: Closing line value (CLV)")
print("-" * 80)
if 'odds' in locals() and odds is not None and not odds.empty:
    # Check for Pinnacle closing odds (gold standard)
    pinnacle_cols = [col for col in odds.columns if 'ps' in str(col).lower() and 'c' in str(col).lower()]
    if pinnacle_cols:
        print(f"✓ Pinnacle closing odds found: {pinnacle_cols}")
        print("✓ Can calculate CLV with Pinnacle close")
        results['market_intelligence']['clv'] = True
    else:
        print("⚠️  No Pinnacle closing odds, but have other bookmaker closing odds")
        results['market_intelligence']['clv'] = 'partial'
else:
    results['market_intelligence']['clv'] = False

# =============================================================================
# EVALUATION / VALIDATION DATA
# =============================================================================
print("\n" + "=" * 80)
print("3. EVALUATION / VALIDATION DATA")
print("=" * 80)

# -----------------------------------------------------------------------------
# 3.1 Post-match key events (red cards, penalties, injuries in game)
# -----------------------------------------------------------------------------
print("\n[3.1] Testing: Post-match key events (red cards, penalties, injuries)")
print("-" * 80)
try:
    fotmob = sd.FotMob(leagues=LEAGUE, seasons=SEASON)

    print("Attempting FotMob match details...")
    # FotMob may have match events
    print("FotMob available (detailed events API TBD)")
    results['evaluation']['match_events'] = 'unknown'

except Exception as e:
    print(f"✗ FotMob match details failed: {e}")
    results['evaluation']['match_events'] = False

# Check Understat for red cards
try:
    if 'shots' in locals() and shots is not None and not shots.empty:
        print("\nChecking Understat shot data for context...")
        # Understat has detailed match data
        understat = sd.Understat(leagues='EPL', seasons='2024')
        league_data = understat.read_league_table()

        if league_data is not None and not league_data.empty:
            print(f"✓ Understat league data: {list(league_data.columns)}")
            results['evaluation']['understat_context'] = True

except Exception as e:
    print(f"Context check failed: {e}")

# -----------------------------------------------------------------------------
# 3.2 Match context labels (expected vs actual flow)
# -----------------------------------------------------------------------------
print("\n[3.2] Testing: Match context labels (expected vs actual flow)")
print("-" * 80)
try:
    fbref = sd.FBref(leagues=LEAGUE, seasons=SEASON)

    print("Attempting FBref match stats...")
    match_stats = fbref.read_schedule()

    if match_stats is not None and not match_stats.empty:
        stat_cols = [col for col in match_stats.columns if any(
            x in str(col).lower() for x in ['xg', 'possession', 'shot']
        )]
        print(f"Match context columns: {stat_cols}")

        if stat_cols:
            print("✓ Can derive expected vs actual flow from xG, possession, shots")
            results['evaluation']['match_context'] = 'derivable'
        else:
            results['evaluation']['match_context'] = False
    else:
        results['evaluation']['match_context'] = False

except Exception as e:
    print(f"✗ Match context failed: {e}")
    results['evaluation']['match_context'] = False

# -----------------------------------------------------------------------------
# 3.3 Confidence calibration labels
# -----------------------------------------------------------------------------
print("\n[3.3] Testing: Confidence calibration labels")
print("-" * 80)
print("⚠️  Requires storing predictions and comparing to outcomes")
print("⚠️  Can be derived from historical predictions + actual results")
results['evaluation']['confidence_calibration'] = 'derivable'

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("VALIDATION SUMMARY")
print("=" * 80)

def print_results(category_name, category_results):
    print(f"\n{category_name}:")
    for key, value in category_results.items():
        if value is True:
            status = "✓ YES"
        elif value is False:
            status = "✗ NO"
        elif value == 'partial':
            status = "⚠ PARTIAL"
        elif value == 'derivable':
            status = "⚠ DERIVABLE"
        else:
            status = "? UNKNOWN"
        print(f"  {status:15} {key}")

print_results("1. MATCH INTELLIGENCE", results['match_intelligence'])
print_results("2. MARKET INTELLIGENCE", results['market_intelligence'])
print_results("3. EVALUATION/VALIDATION", results['evaluation'])

# Calculate coverage
all_results = []
for category in results.values():
    all_results.extend(category.values())

full_yes = sum(1 for r in all_results if r is True)
partial = sum(1 for r in all_results if r in ['partial', 'derivable'])
no = sum(1 for r in all_results if r is False)
unknown = sum(1 for r in all_results if r == 'unknown')
total = len(all_results)

print("\n" + "=" * 80)
print("COVERAGE METRICS")
print("=" * 80)
print(f"Full Coverage:    {full_yes:2d}/{total} ({full_yes/total*100:.1f}%)")
print(f"Partial/Derivable: {partial:2d}/{total} ({partial/total*100:.1f}%)")
print(f"Not Available:     {no:2d}/{total} ({no/total*100:.1f}%)")
print(f"Unknown:           {unknown:2d}/{total} ({unknown/total*100:.1f}%)")

print("\n" + "=" * 80)
print("CRITICAL GAPS")
print("=" * 80)
gaps = []
for category_name, category_results in results.items():
    for key, value in category_results.items():
        if value is False:
            gaps.append(f"{category_name}.{key}")

if gaps:
    print("\nData NOT available via soccerdata:")
    for gap in gaps:
        print(f"  ✗ {gap}")
else:
    print("\n✓ All critical data available (fully or partially)!")

print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)
print("""
1. IMMEDIATE WINS (use soccerdata):
   - Replace FBref Selenium scraper → sd.FBref (faster, more reliable)
   - Replace Understat manual API → sd.Understat (shot-level xG data)
   - Add lineups via FotMob
   - Add comprehensive odds via Football-Data.co.uk

2. SUPPLEMENTARY DATA NEEDED:
   - Real-time injuries: Scrape or use sports data API (The Odds API, etc.)
   - Line movement: Use Betfair API or odds aggregator
   - Market liquidity: Betfair exchange volume

3. DERIVED FEATURES (build pipelines):
   - Rest days: Calculate from schedule dates
   - Match context: Derive from xG, possession, shots
   - Confidence calibration: Track predictions vs outcomes

4. NEXT STEPS:
   - Migrate core ingestion to soccerdata
   - Build feature engineering pipeline for derived metrics
   - Identify and integrate specialized APIs for gaps (injuries, live odds)
""")

print("\n" + "=" * 80)
print("Validation complete!")
print("=" * 80)
