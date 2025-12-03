import soccerdata as sd
import pandas as pd
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection

LEAGUE = "ENG-Premier League"
SEASON = "2526"

NAME_MAP = {
    "Manchester Utd": "Manchester United",
    "Newcastle Utd": "Newcastle United",
    "Nott'ham Forest": "Nottingham Forest",
    "Wolves": "Wolverhampton Wanderers",
    "Brighton": "Brighton",
    "Leicester City": "Leicester",
    "Leeds United": "Leeds",
    "West Ham": "West Ham",
    "Tottenham": "Tottenham",
}

def _calculate_tilt(team_deep, opponent_deep):
    """Calculates Field Tilt % based on Deep Completions."""
    total = team_deep + opponent_deep
    if total == 0:
        return 50.0 # Neutral if nothing happened
    return round((team_deep / total) * 100, 1)

def _update_db(cur, date_str, team_name, ppda, field_tilt):
    """
    Updates the database with PPDA and Field Tilt.
    """
    if pd.isna(ppda):
        return 0

    sql_update = """
    UPDATE team_stats ts
    SET ppda = %s, field_tilt = %s
    FROM fixtures f
    WHERE ts.fixture_id = f.id
      AND f.date = %s
      AND ts.team_name = %s
    """
    
    # Attempt 1: Direct Match
    cur.execute(sql_update, (ppda, field_tilt, date_str, team_name))
    if cur.rowcount > 0:
        return 1
        
    # Attempt 2: Mapped Match
    fbref_name = next((k for k, v in NAME_MAP.items() if v == team_name), None)
    if fbref_name:
        cur.execute(sql_update, (ppda, field_tilt, date_str, fbref_name))
        if cur.rowcount > 0:
            return 1
            
    return 0

def run_enrichment():
    print(f"🕵️  Starting Tactical Enrichment (Understat {SEASON})...")
    
    conn = get_connection()
    if not conn:
        return

    try:
        # Initialize scraper
        understat = sd.Understat(leagues=LEAGUE, seasons=SEASON, no_cache=True)
        
        print("   📥 Fetching PPDA & Deep Completions...")
        df_tactics = understat.read_team_match_stats()
        df_tactics = df_tactics.reset_index()
        
        print(f"   📊 Found {len(df_tactics)} records.")
        
    except Exception as e:
        print(f"❌ Understat scraping failed: {e}")
        return

    updates = 0
    cur = conn.cursor()

    for _, row in df_tactics.iterrows():
        try:
            date_str = row['date'].strftime('%Y-%m-%d')
            
            if 'home_team' in row and 'away_team' in row:
                # 1. Get Deep Completions (Soccerdata column names)
                # Note: Soccerdata 1.5+ standardizes these to home_deep_completions / away_deep_completions
                home_deep = row.get('home_deep_completions', 0)
                away_deep = row.get('away_deep_completions', 0)

                # 2. Calculate Tilt
                home_tilt = _calculate_tilt(home_deep, away_deep)
                away_tilt = _calculate_tilt(away_deep, home_deep)

                # 3. Update DB
                # Update Home Row
                updates += _update_db(cur, date_str, row['home_team'], row['home_ppda'], home_tilt)
                # Update Away Row
                updates += _update_db(cur, date_str, row['away_team'], row['away_ppda'], away_tilt)

        except Exception as e:
            print(f"   ⚠️  Error processing row: {e}")
            continue

    conn.commit()
    conn.close()
    
    print(f"✅ Enrichment Complete!")
    print(f"   - {updates} Team Stats rows updated with PPDA & Field Tilt.")

if __name__ == "__main__":
    run_enrichment()