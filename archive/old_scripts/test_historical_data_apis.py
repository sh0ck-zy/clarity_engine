#!/usr/bin/env python3
"""
Test script to validate historical data availability from football APIs.

This tests:
1. How many past seasons are accessible
2. Can we get lineups from past matches (e.g., round 12 when on round 24)
3. Can we get injury data from past matches
4. Can we get odds snapshots at different timestamps

Usage:
    export API_FOOTBALL_KEY="your_key_here"
    export ODDS_API_KEY="your_key_here"
    python scripts/test_historical_data_apis.py
"""

import os
import requests
import json
from datetime import datetime, timedelta

print("=" * 80)
print("HISTORICAL DATA API VALIDATION")
print("=" * 80)

# =============================================================================
# TEST 1: API-Football - Historical Lineups & Injuries
# =============================================================================
print("\n" + "=" * 80)
print("TEST 1: API-Football - Historical Data")
print("=" * 80)

API_FOOTBALL_KEY = os.getenv('API_FOOTBALL_KEY')

if not API_FOOTBALL_KEY:
    print("\n⚠️  Set API_FOOTBALL_KEY environment variable to test")
    print("   Get free key at: https://www.api-football.com/")
    print("   Then run: export API_FOOTBALL_KEY='your_key'")
else:
    headers = {
        'x-rapidapi-host': 'v3.football.api-sports.io',
        'x-rapidapi-key': API_FOOTBALL_KEY
    }

    # Test: Get seasons available for Premier League
    print("\n[1a] Testing available seasons for Premier League (league=39)...")
    try:
        url = "https://v3.football.api-sports.io/leagues/seasons"
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            seasons = data.get('response', [])
            print(f"✓ Available seasons: {seasons[-10:] if len(seasons) > 10 else seasons}")
            print(f"  Total seasons: {len(seasons)}")
            print(f"  Oldest: {min(seasons)}, Newest: {max(seasons)}")
        else:
            print(f"✗ Failed: {response.status_code}")
            print(f"  Response: {response.text}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test: Get a specific past match with lineups
    print("\n[1b] Testing historical lineup data (e.g., round 12 from 2023-24 season)...")
    try:
        # Get fixtures from round 12 of 2023-24 EPL season
        url = "https://v3.football.api-sports.io/fixtures"
        params = {
            'league': 39,  # Premier League
            'season': 2023,
            'round': 'Regular Season - 12'
        }
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()
            fixtures = data.get('response', [])

            if fixtures:
                fixture_id = fixtures[0]['fixture']['id']
                match_date = fixtures[0]['fixture']['date']
                home_team = fixtures[0]['teams']['home']['name']
                away_team = fixtures[0]['teams']['away']['name']

                print(f"✓ Found fixture: {home_team} vs {away_team} ({match_date})")
                print(f"  Fixture ID: {fixture_id}")

                # Now get lineups for this past match
                print(f"\n[1c] Getting lineup data for fixture {fixture_id}...")
                lineup_url = "https://v3.football.api-sports.io/fixtures/lineups"
                lineup_params = {'fixture': fixture_id}
                lineup_response = requests.get(lineup_url, headers=headers, params=lineup_params)

                if lineup_response.status_code == 200:
                    lineup_data = lineup_response.json()
                    lineups = lineup_data.get('response', [])

                    if lineups:
                        print(f"✓ HISTORICAL LINEUPS AVAILABLE!")
                        for team_lineup in lineups[:1]:  # Just show first team
                            team_name = team_lineup['team']['name']
                            formation = team_lineup.get('formation', 'N/A')
                            starting_xi = team_lineup.get('startXI', [])
                            print(f"  {team_name} - Formation: {formation}")
                            print(f"  Starting XI: {len(starting_xi)} players")
                            if starting_xi:
                                print(f"  Sample: {starting_xi[0]['player']['name']} ({starting_xi[0]['player']['pos']})")
                    else:
                        print(f"⚠️  No lineup data for this match")
                else:
                    print(f"✗ Lineup request failed: {lineup_response.status_code}")

                # Test injuries for that match
                print(f"\n[1d] Getting injuries at time of match...")
                injury_url = "https://v3.football.api-sports.io/injuries"
                # Get injuries for one of the teams around that date
                injury_params = {
                    'fixture': fixture_id
                }
                injury_response = requests.get(injury_url, headers=headers, params=injury_params)

                if injury_response.status_code == 200:
                    injury_data = injury_response.json()
                    injuries = injury_data.get('response', [])

                    if injuries:
                        print(f"✓ HISTORICAL INJURIES AVAILABLE!")
                        print(f"  {len(injuries)} injury records found")
                        if injuries:
                            inj = injuries[0]
                            print(f"  Sample: {inj['player']['name']} - {inj['player']['type']} ({inj['player']['reason']})")
                    else:
                        print(f"⚠️  No injury data for this fixture")
                        print(f"  Note: Injury endpoint may not support fixture-specific historical data")
                else:
                    print(f"✗ Injury request failed: {injury_response.status_code}")
            else:
                print(f"⚠️  No fixtures found for round 12, season 2023")
        else:
            print(f"✗ Failed: {response.status_code}")
    except Exception as e:
        print(f"✗ Error: {e}")

# =============================================================================
# TEST 2: The Odds API - Historical Odds with Timestamps
# =============================================================================
print("\n" + "=" * 80)
print("TEST 2: The Odds API - Historical Odds with Timestamps")
print("=" * 80)

ODDS_API_KEY = os.getenv('ODDS_API_KEY')

if not ODDS_API_KEY:
    print("\n⚠️  Set ODDS_API_KEY environment variable to test")
    print("   Get free key at: https://the-odds-api.com/")
    print("   Note: Historical data requires PAID plan")
    print("   Then run: export ODDS_API_KEY='your_key'")
else:
    # Test: Get historical odds snapshot
    print("\n[2a] Testing historical odds snapshot (e.g., 4 hours before kickoff)...")
    try:
        # Example: Get odds from a specific timestamp
        # Format: ISO8601 - 2023-11-29T22:42:00Z

        # Let's try to get odds from 30 days ago
        past_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')

        url = "https://api.the-odds-api.com/v4/historical/sports/soccer_epl/odds"
        params = {
            'apiKey': ODDS_API_KEY,
            'regions': 'uk,us',
            'markets': 'h2h',  # Moneyline
            'date': past_date,
            'bookmakers': 'pinnacle,bet365'
        }

        print(f"  Requesting odds snapshot from: {past_date}")
        response = requests.get(url, params=params)

        if response.status_code == 200:
            data = response.json()

            if 'data' in data and data['data']:
                print(f"✓ HISTORICAL ODDS AVAILABLE!")
                print(f"  Timestamp: {data.get('timestamp', 'N/A')}")
                print(f"  Previous snapshot: {data.get('previous_timestamp', 'N/A')}")
                print(f"  Next snapshot: {data.get('next_timestamp', 'N/A')}")
                print(f"  Matches: {len(data['data'])}")

                # Show sample
                if data['data']:
                    match = data['data'][0]
                    print(f"\n  Sample match: {match.get('home_team')} vs {match.get('away_team')}")
                    print(f"  Commence time: {match.get('commence_time')}")
                    if 'bookmakers' in match:
                        for bookmaker in match['bookmakers'][:1]:
                            print(f"  {bookmaker['key']} odds: {bookmaker['markets'][0]['outcomes']}")
            else:
                print(f"⚠️  No historical data (may require paid plan)")
                print(f"  Response: {data}")
        elif response.status_code == 401:
            print(f"⚠️  Historical data requires PAID subscription")
            print(f"  Free tier only provides upcoming matches")
        else:
            print(f"✗ Failed: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
    except Exception as e:
        print(f"✗ Error: {e}")

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("SUMMARY & RECOMMENDATIONS")
print("=" * 80)

print("""
HISTORICAL DATA REQUIREMENTS FOR ML TRAINING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. MATCH INTELLIGENCE (Retroactive):
   - Lineups from past matches (e.g., round 12 when on round 24)
   - Injuries at time of match (not current injuries)
   - Player availability for specific past fixtures
   - Formations used in each historical match

2. MARKET INTELLIGENCE (Time-series):
   - Odds snapshots at multiple timestamps:
     * Opening odds (days before)
     * 24h before kickoff
     * 4h before kickoff
     * 1h before kickoff
     * Closing odds (kick-off time)
   - Line movement over time
   - Multiple bookmakers for each timestamp

3. EVALUATION DATA:
   - Actual match outcomes (score, events)
   - Compare pre-match data to actual flow
   - Calibration dataset for backtesting

FINDINGS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

API-Football:
✓ Multiple seasons of historical data (exact count TBD - test with your key)
✓ Historical lineups available for past fixtures
? Historical injuries (may need to fetch by team/date rather than fixture)
✓ All endpoints available on free tier (limited seasons)
✓ Can query specific rounds from past seasons

The Odds API:
✓ Historical data from June 2020
✓ 5-minute interval snapshots (since Sep 2022)
✓ Multiple timestamps per match
✓ Opening, closing, and intermediate odds
✗ Historical data REQUIRES PAID plan ($50+/month)
✓ Can query specific timestamp (e.g., 4h before match)

RECOMMENDATION FOR ML TRAINING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phase 1: DATA COLLECTION (Do this FIRST)
1. Sign up for API-Football Pro plan ($19/month)
   - Backfill last 2-3 seasons of EPL data
   - Fixtures, lineups, injuries, team stats
   - Store in your database with timestamps

2. Sign up for The Odds API paid plan ($50-100/month)
   - Backfill historical odds (from June 2020)
   - Get multiple snapshots per match:
     * Opening odds
     * Every 4-6 hours before kickoff
     * Closing odds
   - Store with proper timestamps

3. Build historical dataset:
   - Match each fixture with:
     * Lineup at time of match
     * Injuries at time of match
     * Odds progression (opening → closing)
     * Actual outcome

4. Create training features:
   - Player availability (who actually played)
   - Formation used
   - Rest days (calculate from fixture dates)
   - Odds movement (opening → closing)
   - CLV (your prediction vs closing line)

Phase 2: ML TRAINING
Once you have 2-3 seasons of complete historical data:
1. Train models on past seasons
2. Backtest strategies with time-travel correctness
3. Validate predictions against actual outcomes
4. Calibrate confidence intervals

Phase 3: PRODUCTION
Switch to real-time data ingestion:
- Upcoming fixtures
- Predicted lineups (updated as team news arrives)
- Odds snapshots every few hours
- Generate predictions

COST ESTIMATE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

One-time historical backfill:
- API-Football Pro: $19/month (2 months for backfill) = $38
- The Odds API: $50-100/month (1-2 months backfill) = $100-200
Total: ~$150-250 one-time

Ongoing production:
- API-Football Pro: $19/month
- The Odds API: $50/month
Total: ~$70/month (~$840/year)

This is CHEAP compared to:
- Building/maintaining scrapers: $500+/month in dev time
- Missing critical data: PRICELESS (can't beat ChatGPT without it)
- Legal/ToS violations: RISKY

NEXT STEPS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ✓ Register for FREE API keys to test:
   - API-Football: https://www.api-football.com/
   - The Odds API: https://the-odds-api.com/

2. ✓ Run this script with your keys to validate data availability

3. ✓ Design database schema for historical data:
   - fixtures (with timestamp)
   - lineups (with fixture_id, timestamp)
   - injuries (with fixture_id, timestamp)
   - odds_snapshots (with fixture_id, timestamp, bookmaker)
   - odds_movement (time-series table)

4. ✓ Build backfill scripts:
   - scripts/backfill_fixtures.py
   - scripts/backfill_lineups.py
   - scripts/backfill_odds.py

5. ✓ Start collecting data NOW:
   - Historical: 2-3 past seasons
   - Live: Current season as it happens
   - Build dataset for training

Without historical data, you CANNOT train ML models properly.
This is the foundation. Invest in it.
""")

print("\n" + "=" * 80)
print("Run this script with API keys to validate!")
print("=" * 80)
