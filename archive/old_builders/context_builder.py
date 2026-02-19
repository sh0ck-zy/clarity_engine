"""
Context Builder v1.1 - Builder v1 + Form Interpreter
Gera contexto enriquecido com interpretação narrativa para o LLM
"""

import pandas as pd
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.builders.form_interpreter import interpret_form


class ContextBuilder:
    """Builder v1.1 - Dados limpos + Interpretação narrativa"""
    
    def __init__(self):
        self.conn = get_connection()

    def build_context(self, fixture_id: str) -> dict:
        """
        Constrói contexto enriquecido para um jogo.
        
        Returns:
            Dict com dados brutos + interpretação narrativa
        """
        if not self.conn:
            return {"error": "No DB Connection"}

        match = self._get_match_details(fixture_id)
        if match is None:
            return {"error": f"Fixture {fixture_id} not found"}

        match_date = match['date']
        season = match['season']

        home_data = self._analyze_team(match['home_team'], match_date, season, is_home=True)
        away_data = self._analyze_team(match['away_team'], match_date, season, is_home=False)

        return {
            "fixture_id": fixture_id,
            "date": str(match_date),
            "home": home_data,
            "away": away_data,
            "matchup_summary": self._generate_matchup_summary(home_data, away_data)
        }

    def _get_match_details(self, fixture_id: str):
        df = pd.read_sql("SELECT * FROM fixtures WHERE id = %s", self.conn, params=(fixture_id,))
        return df.iloc[0] if not df.empty else None

    def _analyze_team(self, team_name: str, match_date, season: str, is_home: bool) -> dict:
        """Analisa equipa com dados + interpretação"""
        
        # A. IDENTITY (Season Long)
        sql_ident = """
            SELECT AVG(ts.ppda) as ppda, AVG(ts.field_tilt) as tilt, 
                   AVG(ts.xg) as xg, AVG(ts.xga) as xga
            FROM team_stats ts 
            JOIN fixtures f ON ts.fixture_id = f.id
            WHERE ts.team_name = %s AND f.season = %s AND f.date < %s
        """
        ident = pd.read_sql(sql_ident, self.conn, params=(team_name, season, match_date)).iloc[0]

        # Get Current Elo
        sql_elo = """
            SELECT elo FROM team_stats ts 
            JOIN fixtures f ON ts.fixture_id = f.id
            WHERE ts.team_name = %s AND f.date < %s 
            ORDER BY f.date DESC LIMIT 1
        """
        elo_df = pd.read_sql(sql_elo, self.conn, params=(team_name, match_date))
        curr_elo = int(elo_df.iloc[0]['elo']) if not elo_df.empty and pd.notna(elo_df.iloc[0]['elo']) else 1500

        # B. FORM (Last 5 Games)
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

        # Calculate Results String
        results = []
        goal_diff = 0
        xg_diff_total = 0
        
        for _, row in form.iterrows():
            my_s = row['home_score'] if row['is_home'] else row['away_score']
            opp_s = row['away_score'] if row['is_home'] else row['home_score']
            goal_diff += (my_s - opp_s)
            xg_diff_total += (row['xg'] - row['xga']) if pd.notna(row['xg']) else 0
            results.append("W" if my_s > opp_s else "L" if my_s < opp_s else "D")

        results_str = "-".join(results)
        days_rest = (match_date - form.iloc[0]['date']).days if not form.empty else 7

        # C. INTERPRETAÇÃO (form_interpreter)
        interpretation = interpret_form(results_str, round(xg_diff_total, 2), goal_diff)

        return {
            "name": team_name,
            "is_home": is_home,
            
            # Raw Identity
            "identity": {
                "elo": curr_elo,
                "season_ppda": round(ident['ppda'] or 0, 1),
                "season_field_tilt": round(ident['tilt'] or 50, 1),
                "season_xg": round(ident['xg'] or 0, 2),
                "season_xga": round(ident['xga'] or 0, 2),
                "season_xg_diff": round((ident['xg'] or 0) - (ident['xga'] or 0), 2)
            },
            
            # Raw Form
            "form": {
                "last_5_results": results_str,
                "last_5_xg_diff": round(xg_diff_total, 2),
                "last_5_goal_diff": goal_diff,
                "last_5_ppda": round(form['ppda'].mean() or 0, 1),
                "last_5_field_tilt": round(form['field_tilt'].mean() or 50, 1),
                "opponent_avg_elo": int(form['opponent_elo'].mean()) if not form.empty and pd.notna(form['opponent_elo'].mean()) else 1500,
                "days_rest": days_rest
            },
            
            # INTERPRETAÇÃO NARRATIVA (novo!)
            "interpretation": {
                "form_label": interpretation["form_label"],
                "form_description": interpretation["form_description"],
                "momentum": interpretation["momentum"],
                "momentum_description": interpretation["momentum_description"],
                "psychological_state": interpretation["psychological_state"],
                "xg_narrative": interpretation["xg_narrative"],
                "goals_narrative": interpretation["goals_narrative"]
            }
        }

    def _generate_matchup_summary(self, home: dict, away: dict) -> str:
        """Gera resumo narrativo do confronto"""
        
        home_state = home["interpretation"]["form_label"]
        away_state = away["interpretation"]["form_label"]
        home_psych = home["interpretation"]["psychological_state"]
        away_psych = away["interpretation"]["psychological_state"]
        
        # Detectar assimetrias claras
        if home_state == "CRISIS" and away_state in ["HOT", "GOOD"]:
            return f"UPSET ALERT: {home['name']} in crisis at home vs {away['name']} riding momentum"
        
        if away_state == "CRISIS" and home_state in ["HOT", "GOOD", "STABILIZING"]:
            return f"HOME ADVANTAGE: {home['name']} should exploit {away['name']}'s fragile state"
        
        if home_state == "STABILIZING" and away_state == "CRISIS":
            return f"MOMENTUM MISMATCH: {home['name']} building vs {away['name']} collapsing"
        
        if home_state == "CRISIS" and away_state == "CRISIS":
            return f"CHAOS GAME: Both teams struggling - high variance expected"
        
        if home_state == "HOT" and away_state == "HOT":
            return f"CLASH OF FORM: Both teams flying - goals expected"
        
        # Default
        return f"{home['name']} ({home_state}) vs {away['name']} ({away_state})"

    def format_for_llm(self, context: dict) -> str:
        """Formata o contexto como texto para enviar ao LLM"""
        
        if "error" in context:
            return f"ERROR: {context['error']}"
        
        home = context["home"]
        away = context["away"]
        
        text = f"""
{home['name'].upper()} (Home)
- Elo: {home['identity']['elo']}
- Season: xG {home['identity']['season_xg']}, xGA {home['identity']['season_xga']}
- Form: {home['form']['last_5_results']}
  → {home['interpretation']['form_description']}
  → {home['interpretation']['momentum_description']}
  → Psychological: {home['interpretation']['psychological_state']}
- Last 5 xG diff: {home['form']['last_5_xg_diff']}
- Last 5 goal diff: {home['form']['last_5_goal_diff']:+d}
- Opponent strength: avg Elo {home['form']['opponent_avg_elo']}

{away['name'].upper()} (Away)
- Elo: {away['identity']['elo']}
- Season: xG {away['identity']['season_xg']}, xGA {away['identity']['season_xga']}
- Form: {away['form']['last_5_results']}
  → {away['interpretation']['form_description']}
  → {away['interpretation']['momentum_description']}
  → Psychological: {away['interpretation']['psychological_state']}
- Last 5 xG diff: {away['form']['last_5_xg_diff']}
- Last 5 goal diff: {away['form']['last_5_goal_diff']:+d}
- Opponent strength: avg Elo {away['form']['opponent_avg_elo']}

MATCHUP: {context['matchup_summary']}
"""
        return text.strip()

    def close(self):
        if self.conn:
            self.conn.close()


# Quick test
if __name__ == "__main__":
    builder = ContextBuilder()
    ctx = builder.build_context("2026-02-06_Leeds_United_Nott'ham_Forest")
    
    print("=== RAW CONTEXT ===")
    import json
    print(json.dumps(ctx, indent=2, default=str))
    
    print("\n=== LLM FORMAT ===")
    print(builder.format_for_llm(ctx))
    
    builder.close()
