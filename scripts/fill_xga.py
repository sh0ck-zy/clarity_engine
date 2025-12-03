import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from database.config import get_connection

def fill_xga_values():
    print("🔄 Mirroring xG to xGA...")
    conn = get_connection()
    if not conn:
        return

    # This SQL query does the magic:
    # It finds the opponent (t2) for every team (t1) in the same match
    # And updates t1.xga with t2.xg
    sql = """
    UPDATE team_stats t1
    SET xga = t2.xg
    FROM team_stats t2
    WHERE t1.fixture_id = t2.fixture_id 
      AND t1.team_name != t2.team_name
      AND t1.xga IS NULL;
    """
    
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    
    print(f"✅ Updated {cur.rowcount} rows with xGA data.")
    conn.close()

if __name__ == "__main__":
    fill_xga_values()