import pandas as pd
import sys
import warnings
from pathlib import Path

# Silenciar avisos do Pandas/SQLAlchemy
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection

class MatchContextBuilder:
    def __init__(self):
        self.conn = get_connection()

    def build_context(self, fixture_id):
        if not self.conn: return {"error": "No DB Connection"}

        # 1. Get Target Match
        match = self._get_match_details(fixture_id)
        if match is None: return {"error": f"Fixture {fixture_id} not found"}

        match_date = match['date']
        season = match['season']

        # 2. Build Profiles (Pure Stats Only)
        return {
            "home": self._analyze_team(match['home_team'], match_date, season, is_home=True),
            "away": self._analyze_team(match['away_team'], match_date, season, is_home=False),
            "market_odds": { "home_win": None, "draw": None, "away_win": None } 
        }

    def _get_match_details(self, fixture_id):
        df = pd.read_sql("SELECT * FROM fixtures WHERE id = %s", self.conn, params=(fixture_id,))
        return df.iloc[0] if not df.empty else None

    def _analyze_team(self, team_name, match_date, season, is_home):
        # A. IDENTITY (Season Long)
        sql_ident = """
            SELECT AVG(ts.ppda) as ppda, AVG(ts.field_tilt) as tilt, AVG(ts.xg) as xg, AVG(ts.xga) as xga
            FROM team_stats ts JOIN fixtures f ON ts.fixture_id = f.id
            WHERE ts.team_name = %s AND f.season = %s AND f.date < %s
        """
        ident = pd.read_sql(sql_ident, self.conn, params=(team_name, season, match_date)).iloc[0]

        # Get Current Elo
        sql_elo = """
            SELECT elo FROM team_stats ts JOIN fixtures f ON ts.fixture_id = f.id
            WHERE ts.team_name = %s AND f.date < %s ORDER BY f.date DESC LIMIT 1
        """
        elo_df = pd.read_sql(sql_elo, self.conn, params=(team_name, match_date))
        curr_elo = int(elo_df.iloc[0]['elo']) if not elo_df.empty and pd.notna(elo_df.iloc[0]['elo']) else 1500

        # B. FORM (Last 5 Games - WITH OPPONENT ELO)
        # Note: We use LEFT JOIN to calculate opponent strength accurately
        sql_form = """
            SELECT 
                f.date, ts.xg, ts.xga, ts.ppda, ts.field_tilt,
                f.home_score, f.away_score, ts.is_home,
                ts_opp.elo as opponent_elo
            FROM team_stats ts
            JOIN fixtures f ON ts.fixture_id = f.id
            LEFT JOIN team_stats ts_opp ON f.id = ts_opp.fixture_id AND ts_opp.team_name != ts.team_name
            WHERE ts.team_name = %s AND f.date < %s
            ORDER BY f.date DESC LIMIT 5
        """
        form = pd.read_sql(sql_form, self.conn, params=(team_name, match_date))

        # Calculate Results
        results = []
        goal_diff = 0
        for _, row in form.iterrows():
            my_s = row['home_score'] if row['is_home'] else row['away_score']
            opp_s = row['away_score'] if row['is_home'] else row['home_score']
            goal_diff += (my_s - opp_s)
            results.append("W" if my_s > opp_s else "L" if my_s < opp_s else "D")

        days_rest = (match_date - form.iloc[0]['date']).days if not form.empty else 7

        return {
            "name": team_name,
            "identity": {
                "elo": curr_elo,
                "season_ppda": round(ident['ppda'] or 0, 1),
                "season_field_tilt": round(ident['tilt'] or 50, 1),
                "season_overall_xg": round(ident['xg'] or 0, 2),
                "season_overall_xga": round(ident['xga'] or 0, 2),
                "season_overall_xg_diff": round((ident['xg'] or 0) - (ident['xga'] or 0), 2)
            },
            "form": {
                "last_5_results": "-".join(results),
                "last_5_xg_diff": round((form['xg'] - form['xga']).sum(), 2) if not form.empty else 0,
                "last_5_goal_diff": goal_diff,
                "last_5_ppda": round(form['ppda'].mean() or 0, 1),
                "last_5_field_tilt": round(form['field_tilt'].mean() or 50, 1),
                "last_5_opponent_avg_elo": int(form['opponent_elo'].mean()) if not form.empty and pd.notna(form['opponent_elo'].mean()) else 1500,
                "days_rest": days_rest
            },
            "context": { "key_injuries": [], "is_home": is_home }
        }

    def close(self):
        self.conn.close()