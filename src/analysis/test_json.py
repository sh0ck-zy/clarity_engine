import json
import sys
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.analysis.builder import MatchContextBuilder
from src.database.config import get_connection

def verify_json_generation():
    print("🔍 Picking a random match to test JSON generation...")
    conn = get_connection()
    # Pick a recent game that DEFINITELY has history
    df = pd.read_sql("SELECT id FROM fixtures WHERE status='FINISHED' ORDER BY date DESC LIMIT 1", conn)
    conn.close()
    
    if df.empty:
        print("❌ No matches found.")
        return

    fixture_id = df.iloc[0]['id']
    print(f"🎯 Target Fixture: {fixture_id}")

    builder = MatchContextBuilder()
    data = builder.build_context(fixture_id)
    builder.close()

    print("\n✅ GENERATED JSON:")
    print(json.dumps(data, indent=2))
    
    # Validation Checks
    try:
        h_form = data['home']['form']
        print(f"\n----- VALIDATION -----")
        print(f"Home Name: {data['home']['name']}")
        print(f"Last 5 Results: {h_form['last_5_results']}")
        print(f"Opponent Avg Elo: {h_form['last_5_opponent_avg_elo']}")
        
        if h_form['last_5_opponent_avg_elo'] == 0:
            print("⚠️ WARNING: Opponent Elo is 0. Check database Elo coverage.")
        else:
            print("✅ Opponent Elo calculation works.")
            
    except Exception as e:
        print(f"❌ Validation Failed: {e}")

if __name__ == "__main__":
    verify_json_generation()