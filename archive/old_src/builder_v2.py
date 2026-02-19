import pandas as pd
import sys
import warnings
from datetime import date
from pathlib import Path

# Silence Pandas/SQLAlchemy warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection


class MatchContextBuilderV2:
    def __init__(self):
        self.conn = get_connection()
        self.market_values_available = self._table_exists("player_market_values")

    def build_context(self, fixture_id):
        if not self.conn:
            return {"error": "No DB Connection"}

        match = self._get_match_details(fixture_id)
        if match is None:
            return {"error": f"Fixture {fixture_id} not found"}

        match_date = match["date"]
        season = match["season"]

        return {
            "home": self._analyze_team(match["home_team"], match_date, season, is_home=True),
            "away": self._analyze_team(match["away_team"], match_date, season, is_home=False),
            "market_odds": {"home_win": None, "draw": None, "away_win": None},
        }

    def _get_match_details(self, fixture_id):
        df = pd.read_sql("SELECT * FROM fixtures WHERE id = %s", self.conn, params=(fixture_id,))
        return df.iloc[0] if not df.empty else None

    def _analyze_team(self, team_name, match_date, season, is_home):
        sql_ident = """
            SELECT AVG(ts.ppda) as ppda, AVG(ts.field_tilt) as tilt, AVG(ts.xg) as xg, AVG(ts.xga) as xga
            FROM team_stats ts JOIN fixtures f ON ts.fixture_id = f.id
            WHERE ts.team_name = %s AND f.season = %s AND f.date < %s
        """
        ident = pd.read_sql(sql_ident, self.conn, params=(team_name, season, match_date)).iloc[0]

        sql_elo = """
            SELECT elo FROM team_stats ts JOIN fixtures f ON ts.fixture_id = f.id
            WHERE ts.team_name = %s AND f.date < %s ORDER BY f.date DESC LIMIT 1
        """
        elo_df = pd.read_sql(sql_elo, self.conn, params=(team_name, match_date))
        curr_elo = int(elo_df.iloc[0]["elo"]) if not elo_df.empty and pd.notna(elo_df.iloc[0]["elo"]) else 1500

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

        results = []
        goal_diff = 0
        for _, row in form.iterrows():
            is_home_row = self._safe_bool(row["is_home"])
            my_s = row["home_score"] if is_home_row else row["away_score"]
            opp_s = row["away_score"] if is_home_row else row["home_score"]
            goal_diff += (my_s - opp_s)
            results.append("W" if my_s > opp_s else "L" if my_s < opp_s else "D")

        days_rest = (match_date - form.iloc[0]["date"]).days if not form.empty else 7
        injuries = self._get_active_injuries(team_name, match_date, season)
        market_values = self._fetch_market_values(
            [injury["player_id"] for injury in injuries if injury.get("player_id")],
            match_date,
        )
        self._attach_market_values(injuries, market_values)
        key_injuries = self._select_key_injuries(injuries)

        ident_ppda = self._safe_number(ident["ppda"], 0)
        ident_tilt = self._safe_number(ident["tilt"], 50)
        ident_xg = self._safe_number(ident["xg"], 0)
        ident_xga = self._safe_number(ident["xga"], 0)
        form_ppda = self._safe_number(form["ppda"].mean() if not form.empty else None, 0)
        form_tilt = self._safe_number(form["field_tilt"].mean() if not form.empty else None, 50)
        opp_elo_mean = form["opponent_elo"].mean() if not form.empty else None
        opp_elo = self._safe_number(opp_elo_mean, 1500)

        return {
            "name": team_name,
            "identity": {
                "elo": curr_elo,
                "season_ppda": round(ident_ppda, 1),
                "season_field_tilt": round(ident_tilt, 1),
                "season_overall_xg": round(ident_xg, 2),
                "season_overall_xga": round(ident_xga, 2),
                "season_overall_xg_diff": round(ident_xg - ident_xga, 2),
            },
            "form": {
                "last_5_results": "-".join(results),
                "last_5_xg_diff": round((form["xg"] - form["xga"]).sum(), 2) if not form.empty else 0,
                "last_5_goal_diff": goal_diff,
                "last_5_ppda": round(form_ppda, 1),
                "last_5_field_tilt": round(form_tilt, 1),
                "last_5_opponent_avg_elo": int(opp_elo),
                "days_rest": days_rest,
            },
            "absences": {
                "total_missing": len(injuries),
                "total_market_value_eur": self._sum_market_values(injuries),
                "players": injuries,
            },
            "context": {"key_injuries": key_injuries, "is_home": is_home},
        }

    def _get_active_injuries(self, team_name, match_date, season):
        tm_season = self._to_tm_season(season)
        if not tm_season:
            return []

        tm_team_name = self._normalize_team_name(team_name)

        sql = """
            SELECT player_id, player_name, injury_reason, from_date, end_date, days_missed, games_missed, ingested_at
            FROM player_injuries_historical
            WHERE season = %s
              AND team_name = %s
              AND from_date <= %s
              AND (end_date IS NULL OR end_date > %s)
            ORDER BY player_name, ingested_at DESC
        """
        df = pd.read_sql(sql, self.conn, params=(tm_season, tm_team_name, match_date, match_date))
        if df.empty:
            return []

        seen = set()
        results = []
        for _, row in df.iterrows():
            key = (row["player_id"], row["injury_reason"], row["from_date"], row["end_date"])
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "player_id": row["player_id"],
                    "player_name": row["player_name"],
                    "injury_reason": row["injury_reason"],
                    "from_date": self._date_to_str(row["from_date"]),
                    "end_date": self._date_to_str(row["end_date"]),
                    "days_missed": self._safe_int(row["days_missed"]),
                    "games_missed": self._safe_int(row["games_missed"]),
                    "market_value_eur": None,
                }
            )
        return results

    def _fetch_market_values(self, player_ids, match_date):
        if not self.market_values_available:
            return {}
        numeric_ids = []
        for player_id in player_ids:
            if player_id is None or pd.isna(player_id):
                continue
            try:
                numeric_ids.append(int(player_id))
            except (TypeError, ValueError):
                continue
        if not numeric_ids:
            return {}

        sql = """
            SELECT DISTINCT ON (player_id)
                   player_id,
                   market_value_eur
            FROM player_market_values
            WHERE player_id = ANY(%s)
              AND valuation_date <= %s
            ORDER BY player_id, valuation_date DESC
        """
        df = pd.read_sql(sql, self.conn, params=(numeric_ids, match_date))
        if df.empty:
            return {}
        return {int(row["player_id"]): float(row["market_value_eur"]) for _, row in df.iterrows()}

    def _table_exists(self, table_name):
        if not self.conn:
            return False
        query = """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name=%s
            )
        """
        df = pd.read_sql(query, self.conn, params=(table_name,))
        if df.empty:
            return False
        return bool(df.iloc[0][0])

    @staticmethod
    def _attach_market_values(injuries, market_values):
        for injury in injuries:
            player_id = injury.get("player_id")
            try:
                player_id_int = int(player_id)
            except (TypeError, ValueError):
                player_id_int = None
            if player_id_int is not None and player_id_int in market_values:
                injury["market_value_eur"] = market_values[player_id_int]

    @staticmethod
    def _sum_market_values(injuries):
        total = 0.0
        has_value = False
        for injury in injuries:
            value = injury.get("market_value_eur")
            if value is None:
                continue
            has_value = True
            total += float(value)
        return round(total, 2) if has_value else None

    @staticmethod
    def _select_key_injuries(injuries):
        if not injuries:
            return []
        def sort_key(entry):
            value = entry.get("market_value_eur")
            if value is None:
                return (1, 0)
            return (0, -value)
        ordered = sorted(injuries, key=sort_key)
        return [entry["player_name"] for entry in ordered[:5]]

    @staticmethod
    def _safe_int(value):
        if value is None or pd.isna(value):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_bool(value):
        if value is None or pd.isna(value):
            return False
        return bool(value)

    @staticmethod
    def _safe_number(value, default):
        if value is None or pd.isna(value):
            return default
        return value

    @staticmethod
    def _date_to_str(value):
        if value is None or pd.isna(value):
            return None
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _to_tm_season(season):
        if not season:
            return None
        if "/" in season and len(season) == 5:
            return season
        if "-" in season:
            parts = season.split("-")
            if len(parts) >= 2 and len(parts[0]) == 4 and len(parts[1]) >= 2:
                start = parts[0][-2:]
                end = parts[1][-2:]
                return f"{start}/{end}"
        return None

    @staticmethod
    def _normalize_team_name(team_name):
        if not team_name:
            return team_name
        mapping = {
            "Manchester Utd": "Man United",
            "Man United": "Man United",
            "Manchester City": "Man City",
            "Nott'ham Forest": "Nottingham Forest",
            "Newcastle Utd": "Newcastle",
            "Wolves": "Wolves",
            "Tottenham": "Tottenham",
            "West Ham": "West Ham",
            "Brighton": "Brighton",
        }
        return mapping.get(team_name, team_name)

    def close(self):
        if self.conn:
            self.conn.close()
