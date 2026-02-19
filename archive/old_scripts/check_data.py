import sys
import os
import pandas as pd

# Add project root to path so we can import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from database.config import get_connection

def check_data():
    conn = get_connection()
    if not conn:
        return

    print("\n📊 CLARITY DATABASE AUDIT")
    print("=========================")

    # 1. TOTAL COUNTS
    df_fixtures = pd.read_sql("SELECT status, COUNT(*) as count FROM fixtures GROUP BY status", conn)
    print("\n1. Fixture Status Breakdown:")
    print(df_fixtures.to_string(index=False))

    # 2. DATA QUALITY CHECK (xG)
    # We want to see if we actually have xG data for finished games
    sql_quality = """
        SELECT 
            COUNT(*) as total_rows,
            COUNT(xg) as rows_with_xg,
            ROUND(COUNT(xg)::numeric / COUNT(*)::numeric * 100, 1) as coverage_pct
        FROM team_stats
    """
    df_quality = pd.read_sql(sql_quality, conn)
    print("\n2. Data Quality (Team Stats):")
    print(df_quality.to_string(index=False))

    # 3. LATEST RESULTS (Sanity Check)
    # Join fixtures and stats to see a human-readable table
    print("\n3. Last 5 Matches (with xG):")
    sql_recent = """
        SELECT 
            f.date, 
            f.home_team, 
            f.home_score, 
            f.away_score, 
            f.away_team,
            ts_home.xg as home_xg,
            ts_away.xg as away_xg
        FROM fixtures f
        LEFT JOIN team_stats ts_home ON f.id = ts_home.fixture_id AND ts_home.is_home = TRUE
        LEFT JOIN team_stats ts_away ON f.id = ts_away.fixture_id AND ts_away.is_home = FALSE
        WHERE f.status = 'FINISHED'
        ORDER BY f.date DESC
        LIMIT 5
    """
    df_recent = pd.read_sql(sql_recent, conn)
    print(df_recent.to_string(index=False))

    conn.close()

if __name__ == "__main__":
    check_data()