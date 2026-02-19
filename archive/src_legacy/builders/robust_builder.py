"""
Robust Builder - Builder principal do Clarity Engine
Usa fixtures directamente para form (dados sempre actuais)
Enriquece com xG quando disponível em team_stats
"""

from typing import Optional
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.builders.form_interpreter import interpret_form


class RobustBuilder:
    """Builder principal - funciona mesmo com dados incompletos"""
    
    def __init__(self):
        self.conn = get_connection()

    def build_context(self, fixture_id: str) -> dict:
        """Constrói contexto para um jogo"""
        if not self.conn:
            return {"error": "No DB Connection"}

        match = self._get_match(fixture_id)
        if not match:
            return {"error": f"Fixture {fixture_id} not found"}

        home = self._analyze_team(match['home_team'], match['date'], match['season'], is_home=True)
        away = self._analyze_team(match['away_team'], match['date'], match['season'], is_home=False)

        return {
            "fixture_id": fixture_id,
            "date": str(match['date']),
            "home": home,
            "away": away,
            "matchup": self._matchup_summary(home, away),
            "data_quality": {
                "home_has_xg": home.get("has_xg", False),
                "away_has_xg": away.get("has_xg", False)
            }
        }

    def _get_match(self, fixture_id: str) -> Optional[dict]:
        """Busca dados do jogo"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, date, season, home_team, away_team, home_score, away_score, status
                FROM fixtures WHERE id = %s
            """, (fixture_id,))
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0], "date": row[1], "season": row[2],
                    "home_team": row[3], "away_team": row[4],
                    "home_score": row[5], "away_score": row[6], "status": row[7]
                }
        return None

    def _analyze_team(self, team_name: str, match_date, season: str, is_home: bool) -> dict:
        """Analisa equipa usando fixtures + xG se disponível"""
        
        # Buscar form dos fixtures (sempre actualizado)
        form_data = self._get_form_from_fixtures(team_name, match_date)
        
        # Enriquecer com xG se disponível
        xg_data = self._get_xg_for_games(team_name, form_data.get("fixture_ids", []))
        if xg_data:
            form_data["xg_diff"] = xg_data["xg_diff"]
            has_xg = True
        else:
            has_xg = False

        # Interpretar forma
        interpretation = interpret_form(
            form_data["results_str"],
            form_data.get("xg_diff", 0),
            form_data["goal_diff"]
        )

        # Obter Elo
        elo = self._get_elo(team_name, match_date)

        return {
            "name": team_name,
            "is_home": is_home,
            "has_xg": has_xg,
            "elo": elo,
            "form": {
                "last_5_results": form_data["results_str"],
                "last_5_goal_diff": form_data["goal_diff"],
                "last_5_xg_diff": form_data.get("xg_diff", 0),
                "games_analyzed": form_data["games_count"]
            },
            "interpretation": {
                "form_label": interpretation["form_label"],
                "form_description": interpretation["form_description"],
                "momentum": interpretation["momentum"],
                "psychological_state": interpretation["psychological_state"]
            }
        }

    def _get_form_from_fixtures(self, team_name: str, match_date) -> dict:
        """Calcula form dos últimos 5 jogos via fixtures"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT f.id, f.home_team, f.home_score, f.away_score
                FROM fixtures f
                WHERE (f.home_team = %s OR f.away_team = %s)
                  AND f.date < %s
                  AND f.status = 'FINISHED'
                  AND f.home_score IS NOT NULL
                ORDER BY f.date DESC
                LIMIT 5
            """, (team_name, team_name, match_date))
            rows = cur.fetchall()

        results = []
        goal_diff = 0
        fixture_ids = []
        
        for fix_id, home, home_s, away_s in rows:
            fixture_ids.append(fix_id)
            is_home = (home == team_name)
            my_score = home_s if is_home else away_s
            opp_score = away_s if is_home else home_s
            
            goal_diff += (my_score - opp_score)
            results.append("W" if my_score > opp_score else "L" if my_score < opp_score else "D")

        # Inverter: mostrar do mais antigo → mais recente
        results.reverse()
        fixture_ids.reverse()
        
        return {
            "results_str": "-".join(results) if results else "?",
            "goal_diff": goal_diff,
            "xg_diff": 0,
            "games_count": len(results),
            "fixture_ids": fixture_ids
        }

    def _get_xg_for_games(self, team_name: str, fixture_ids: list) -> Optional[dict]:
        """Busca xG para jogos específicos"""
        if not fixture_ids:
            return None
            
        with self.conn.cursor() as cur:
            placeholders = ','.join(['%s'] * len(fixture_ids))
            cur.execute(f"""
                SELECT ts.xg, ts.xga
                FROM team_stats ts
                WHERE ts.fixture_id IN ({placeholders})
                  AND ts.team_name = %s
            """, fixture_ids + [team_name])
            rows = cur.fetchall()
        
        if not rows:
            return None
            
        xg_diff = sum((r[0] or 0) - (r[1] or 0) for r in rows)
        return {"xg_diff": round(xg_diff, 2)}

    def _get_elo(self, team_name: str, match_date) -> int:
        """Busca último Elo disponível"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT ts.elo
                FROM team_stats ts
                JOIN fixtures f ON ts.fixture_id = f.id
                WHERE ts.team_name = %s AND f.date < %s AND ts.elo IS NOT NULL
                ORDER BY f.date DESC
                LIMIT 1
            """, (team_name, match_date))
            row = cur.fetchone()
            return row[0] if row else 1500

    def _matchup_summary(self, home: dict, away: dict) -> str:
        """Gera resumo do confronto"""
        h_label = home["interpretation"]["form_label"]
        a_label = away["interpretation"]["form_label"]
        
        if h_label == "CRISIS" and a_label in ["HOT", "GOOD"]:
            return f"UPSET RISK: {home['name']} struggling vs {away['name']} in form"
        if a_label == "CRISIS" and h_label in ["HOT", "GOOD", "STABILIZING"]:
            return f"HOME ADVANTAGE: {away['name']} vulnerable away"
        if h_label == "CRISIS" and a_label == "CRISIS":
            return "CHAOS: Both teams struggling"
        
        return f"{home['name']} ({h_label}) vs {away['name']} ({a_label})"

    def format_for_llm(self, ctx: dict) -> str:
        """Formata contexto para enviar ao LLM"""
        if "error" in ctx:
            return f"ERROR: {ctx['error']}"
        
        h, a = ctx["home"], ctx["away"]
        
        xg_note = ""
        if not h.get("has_xg") or not a.get("has_xg"):
            xg_note = "\n⚠️ xG data incomplete for some games."
        
        return f"""
{h['name'].upper()} (Home) - Elo {h['elo']}
Form: {h['form']['last_5_results']} ({h['form']['games_analyzed']} games)
  → {h['interpretation']['form_description']}
  → {h['interpretation']['psychological_state']}
Goal diff L5: {h['form']['last_5_goal_diff']:+d}

{a['name'].upper()} (Away) - Elo {a['elo']}
Form: {a['form']['last_5_results']} ({a['form']['games_analyzed']} games)
  → {a['interpretation']['form_description']}
  → {a['interpretation']['psychological_state']}
Goal diff L5: {a['form']['last_5_goal_diff']:+d}

MATCHUP: {ctx['matchup']}{xg_note}
""".strip()

    def close(self):
        if self.conn:
            self.conn.close()


if __name__ == "__main__":
    import json
    
    builder = RobustBuilder()
    ctx = builder.build_context("2026-02-06_Leeds_United_Nott'ham_Forest")
    
    print("=== CONTEXT ===")
    print(json.dumps(ctx, indent=2, default=str))
    
    print("\n=== LLM FORMAT ===")
    print(builder.format_for_llm(ctx))
    
    builder.close()
