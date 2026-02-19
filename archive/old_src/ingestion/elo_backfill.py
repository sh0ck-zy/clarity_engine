import pandas as pd
import requests
import io
import sys
from pathlib import Path
import time

# Setup Path to import DB
SRC_PATH = Path(__file__).resolve().parents[1]
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from database.config import get_connection

# CORRECTED MAPPINGS (Based on check_elo_names.py output)
ELO_MAPPING = {
    # The Big Mismatches
    "Manchester Utd": "Man United",
    "Manchester City": "Man City",
    "Newcastle Utd": "Newcastle",
    "Nott'ham Forest": "Forest",
    "Sheffield Utd": "Sheffield United",
    "Leicester City": "Leicester",   # <--- ADDED
    "Ipswich Town": "Ipswich",       # <--- ADDED
    "Luton Town": "Luton",
    "Leeds United": "Leeds",
    "Tottenham": "Tottenham",        
    "Wolves": "Wolves",              
    
    # Standardizing just in case
    "West Ham": "West Ham",
    "Brighton": "Brighton",
    "Brentford": "Brentford",
    "Chelsea": "Chelsea",
    "Arsenal": "Arsenal",
    "Liverpool": "Liverpool",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Aston Villa": "Aston Villa",
    "Crystal Palace": "Crystal Palace",
    "Bournemouth": "Bournemouth",
    "Burnley": "Burnley",
    "Sunderland": "Sunderland",
    "Southampton": "Southampton"
}

def get_elo_for_date(date_str):
    url = f"http://api.clubelo.com/{date_str}"
    try:
        headers = {'User-Agent': 'ClarityFootball/1.0'}
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return pd.read_csv(io.StringIO(r.content.decode('utf-8')))
    except Exception as e:
        print(f"   ⚠️ API Error for {date_str}: {e}")
    return None

def run_elo_backfill():
    print("⏳ Starting Elo Backfill (Fixing Gaps)...")
    conn = get_connection()
    if not conn:
        return

    # 1. Get dates where Elo is NULL or 0
    sql_dates = """
        SELECT DISTINCT f.date 
        FROM fixtures f
        JOIN team_stats ts ON f.id = ts.fixture_id
        WHERE (ts.elo IS NULL OR ts.elo = 0)
        AND f.status = 'FINISHED'
        ORDER BY f.date DESC
    """
    try:
        dates = pd.read_sql(sql_dates, conn)['date'].tolist()
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return
    
    print(f"   📅 Found {len(dates)} matchdays needing repairs.")

    updates = 0
    cur = conn.cursor()

    for date_obj in dates:
        date_str = date_obj.strftime("%Y-%m-%d")
        
        df_elo = get_elo_for_date(date_str)
        if df_elo is None: continue
            
        df_eng = df_elo[df_elo['Country'] == 'ENG']
        
        cur.execute("""
            SELECT ts.team_name 
            FROM team_stats ts 
            JOIN fixtures f ON ts.fixture_id = f.id 
            WHERE f.date = %s
        """, (date_str,))
        
        teams_playing = [row[0] for row in cur.fetchall()]
        
        for team in teams_playing:
            lookup_name = ELO_MAPPING.get(team, team)
            match = df_eng[df_eng['Club'] == lookup_name]
            
            if not match.empty:
                elo_rating = int(match.iloc[0]['Elo'])
                
                cur.execute("""
                    UPDATE team_stats ts
                    SET elo = %s
                    FROM fixtures f
                    WHERE ts.fixture_id = f.id 
                      AND f.date = %s 
                      AND ts.team_name = %s
                """, (elo_rating, date_str, team))
                
                updates += cur.rowcount
        
        conn.commit()
        # time.sleep(0.1) # Fast enough to not need sleep for repairs

    print(f"✅ Repairs Complete. Updated {updates} missing Elo ratings.")
    conn.close()

if __name__ == "__main__":
    run_elo_backfill()