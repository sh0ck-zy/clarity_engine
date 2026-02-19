import sys
from pathlib import Path

import pandas as pd
import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection

LEAGUE = "ENG-Premier League"
SEASON = "2526"

UNDERSTAT_SLUGS = {
    "ENG-Premier League": "EPL",
}

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


def _season_start_year(season_code: str) -> str:
    """
    Convert multi-year season codes (e.g., '2526') to the start year string expected by
    the Understat API (e.g., '2025').
    """
    code = str(season_code)
    if len(code) == 4:
        start = int(code[:2])
        end = int(code[2:])
        if (start + 1) % 100 == end % 100:
            century = 1900 if start > 80 else 2000
            return str(century + start)
        if code.startswith(("19", "20")):
            return code
    if len(code) == 2:
        return str(2000 + int(code))
    raise ValueError(f"Unrecognized season code: {season_code}")


def _compute_ppda(ppda_blob):
    """Calculate PPDA (att/def) with safe fallbacks."""
    try:
        att = float(ppda_blob.get("att"))
        defe = float(ppda_blob.get("def"))
        if defe == 0:
            return pd.NA
        return att / defe
    except Exception:
        return pd.NA


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _fetch_understat_stats(league: str, season: str) -> pd.DataFrame:
    """Call Understat's AJAX endpoint (getLeagueData) and return a tidy DataFrame."""
    if league not in UNDERSTAT_SLUGS:
        raise ValueError(f"League '{league}' is not configured for Understat scraping.")

    slug = UNDERSTAT_SLUGS[league]
    season_param = _season_start_year(season)
    url = f"https://understat.com/getLeagueData/{slug}/{season_param}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://understat.com/league/{slug}",
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()

    matches = payload.get("dates") or []
    teams = payload.get("teams") or {}
    history_lookup = {
        _safe_int(team_id): {m.get("date"): m for m in team.get("history", [])}
        for team_id, team in teams.items()
    }

    records = []
    for match in matches:
        try:
            date_str = match["datetime"]
            home_blob = match["h"]
            away_blob = match["a"]
            home_id = _safe_int(home_blob.get("id"))
            away_id = _safe_int(away_blob.get("id"))
            home_history = history_lookup.get(home_id, {}).get(date_str)
            away_history = history_lookup.get(away_id, {}).get(date_str)
            if not home_history or not away_history:
                continue

            records.append(
                {
                    "date": pd.to_datetime(date_str, format="%Y-%m-%d %H:%M:%S"),
                    "home_team": home_blob.get("title"),
                    "away_team": away_blob.get("title"),
                    "home_ppda": _compute_ppda(home_history.get("ppda", {})),
                    "away_ppda": _compute_ppda(away_history.get("ppda", {})),
                    "home_deep_completions": _safe_int(home_history.get("deep")),
                    "away_deep_completions": _safe_int(away_history.get("deep")),
                }
            )
        except Exception:
            continue

    return pd.DataFrame.from_records(records)


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
        print("   📥 Fetching PPDA & Deep Completions...")
        df_tactics = _fetch_understat_stats(LEAGUE, SEASON).reset_index(drop=True)
        
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
