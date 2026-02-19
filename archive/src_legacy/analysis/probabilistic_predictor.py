"""
Probabilistic Predictor - v5

Em vez de pedir ao LLM um score, pedimos probabilidades.
A decisão final (H/D/A) é feita por código com thresholds calibrados.
"""

import json
import os
from pathlib import Path
from google import genai
from google.genai.types import GenerateContentConfig
from src.analysis.builder import MatchContextBuilder
from src.database.config import get_connection

# Load prompt
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
PROBABILISTIC_PROMPT = (PROMPTS_DIR / "v5_probabilistic.txt").read_text(encoding="utf-8")


class ProbabilisticPredictor:
    """
    Em vez de pedir score, pede distribuição de probabilidades.
    A decisão final é feita por código, não pelo LLM.
    """

    def __init__(self, model: str = "gemini-2.0-flash"):
        api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.builder = MatchContextBuilder()
        self.conn = get_connection()

    def close(self):
        if self.conn:
            self.conn.close()
        if hasattr(self.builder, 'close'):
            self.builder.close()

    def predict(self, fixture_id: str) -> dict:
        """
        Gera previsão probabilística para um fixture.

        Returns:
            dict com probabilities, result, predicted_score, confidence
        """
        # 1. Build context
        context = self.builder.build_context(fixture_id)
        if not context:
            return {"error": f"Could not build context for {fixture_id}"}

        # 2. Get probabilities from LLM
        probs = self._get_probabilities(context)
        if "error" in probs:
            return probs

        # 3. Decide result based on thresholds
        result = self._decide_result(probs)

        # 4. Generate score consistent with result
        score = self._generate_score(result, probs)

        # 5. Calculate confidence
        confidence = self._calculate_confidence(probs, result)

        # 6. Save to database
        self._save_to_db(fixture_id, probs, result, score, confidence)

        return {
            "fixture_id": fixture_id,
            "probabilities": {
                "home_win": probs.get("home_win_pct", 0),
                "draw": probs.get("draw_pct", 0),
                "away_win": probs.get("away_win_pct", 0)
            },
            "result": result,
            "predicted_score": score,
            "confidence": confidence,
            "over_2_5_pct": probs.get("over_2_5_pct", 50),
            "expected_goals": probs.get("expected_total_goals", 2.5),
            "reasoning": probs.get("reasoning", {}),
            "key_uncertainty": probs.get("key_uncertainty", "")
        }

    def _get_probabilities(self, context: dict) -> dict:
        """LLM só faz distribuição de probabilidades."""

        # Format context for prompt
        context_str = self._format_context(context)

        full_prompt = f"{PROBABILISTIC_PROMPT}\n\nMATCH CONTEXT:\n{context_str}"

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=2000
                )
            )

            content = response.text.strip()

            # Clean markdown if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            probs = json.loads(content)

            # Validate probabilities sum to 100
            total = probs.get("home_win_pct", 0) + probs.get("draw_pct", 0) + probs.get("away_win_pct", 0)
            if abs(total - 100) > 2:  # Allow small rounding errors
                # Normalize
                factor = 100 / total
                probs["home_win_pct"] = round(probs["home_win_pct"] * factor)
                probs["draw_pct"] = round(probs["draw_pct"] * factor)
                probs["away_win_pct"] = 100 - probs["home_win_pct"] - probs["draw_pct"]

            return probs

        except json.JSONDecodeError as e:
            return {"error": f"JSON decode error: {e}", "raw": content}
        except Exception as e:
            return {"error": str(e)}

    def _format_context(self, context: dict) -> str:
        """Format context dict as readable string for LLM."""
        lines = []

        # Home team
        home = context.get("home", {})
        home_ident = home.get("identity", {})
        home_form = home.get("form", {})
        home_name = home.get("name", "Home Team")

        lines.append(f"HOME: {home_name}")
        lines.append(f"  Elo: {home_ident.get('elo', 1500)}")
        lines.append(f"  Season xG: {home_ident.get('season_overall_xg', 'N/A')} | xGA: {home_ident.get('season_overall_xga', 'N/A')}")
        lines.append(f"  Last 5: {home_form.get('last_5_results', 'N/A')}")
        lines.append(f"  Recent xG diff: {home_form.get('last_5_xg_diff', 'N/A')}")
        lines.append(f"  PPDA: {home_ident.get('season_ppda', 'N/A')} | Field Tilt: {home_ident.get('season_field_tilt', 'N/A')}%")

        # Away team
        away = context.get("away", {})
        away_ident = away.get("identity", {})
        away_form = away.get("form", {})
        away_name = away.get("name", "Away Team")

        lines.append(f"\nAWAY: {away_name}")
        lines.append(f"  Elo: {away_ident.get('elo', 1500)}")
        lines.append(f"  Season xG: {away_ident.get('season_overall_xg', 'N/A')} | xGA: {away_ident.get('season_overall_xga', 'N/A')}")
        lines.append(f"  Last 5: {away_form.get('last_5_results', 'N/A')}")
        lines.append(f"  Recent xG diff: {away_form.get('last_5_xg_diff', 'N/A')}")
        lines.append(f"  PPDA: {away_ident.get('season_ppda', 'N/A')} | Field Tilt: {away_ident.get('season_field_tilt', 'N/A')}%")

        # Head to head
        h2h = context.get("h2h", {})
        if h2h:
            lines.append(f"\nH2H (last {h2h.get('matches', 0)} games):")
            lines.append(f"  {home_name} wins: {h2h.get('home_wins', 0)} | Draws: {h2h.get('draws', 0)} | {away_name} wins: {h2h.get('away_wins', 0)}")

        # Absences/Injuries
        home_injuries = home.get("context", {}).get("key_injuries", [])
        away_injuries = away.get("context", {}).get("key_injuries", [])
        if home_injuries:
            lines.append(f"\n{home_name} Injuries: {', '.join(home_injuries[:5])}")
        if away_injuries:
            lines.append(f"{away_name} Injuries: {', '.join(away_injuries[:5])}")

        return "\n".join(lines)

    def _decide_result(self, probs: dict) -> str:
        """
        Código decide resultado baseado em thresholds calibrados.
        """
        home = probs.get("home_win_pct", 33)
        draw = probs.get("draw_pct", 34)
        away = probs.get("away_win_pct", 33)

        # Threshold: só prevê vencedor se >40% E significativamente acima do draw
        # Isto força mais empates quando há incerteza

        if home >= 45 and home > draw + 12:
            return "H"
        elif away >= 45 and away > draw + 12:
            return "A"
        elif draw >= 30:
            # Se draw >= 30% e nenhum lado tem vantagem clara, é empate
            return "D"
        elif home > away:
            return "H"
        elif away > home:
            return "A"
        else:
            return "D"

    def _generate_score(self, result: str, probs: dict) -> str:
        """Gera score consistente com o resultado e expected goals."""

        expected_goals = probs.get("expected_total_goals", 2.5)

        if result == "D":
            if expected_goals < 1.5:
                return "0-0"
            elif expected_goals < 2.5:
                return "1-1"
            else:
                return "2-2"
        elif result == "H":
            if expected_goals < 2.0:
                return "1-0"
            elif expected_goals < 3.0:
                return "2-1"
            else:
                return "3-1"
        else:  # Away win
            if expected_goals < 2.0:
                return "0-1"
            elif expected_goals < 3.0:
                return "1-2"
            else:
                return "1-3"

    def _calculate_confidence(self, probs: dict, result: str) -> int:
        """Calcula confiança baseada na distribuição de probabilidades."""

        if result == "H":
            return probs.get("home_win_pct", 50)
        elif result == "A":
            return probs.get("away_win_pct", 50)
        else:
            return probs.get("draw_pct", 30)

    def _save_to_db(self, fixture_id: str, probs: dict, result: str, score: str, confidence: int):
        """Salva previsão na tabela analysis_reports."""

        if not self.conn:
            return

        try:
            cursor = self.conn.cursor()

            # Build full JSON
            full_json = {
                "probabilities": {
                    "home_win_pct": probs.get("home_win_pct"),
                    "draw_pct": probs.get("draw_pct"),
                    "away_win_pct": probs.get("away_win_pct")
                },
                "over_2_5_pct": probs.get("over_2_5_pct"),
                "btts_yes_pct": probs.get("btts_yes_pct"),
                "expected_total_goals": probs.get("expected_total_goals"),
                "reasoning": probs.get("reasoning"),
                "key_uncertainty": probs.get("key_uncertainty"),
                "result_decision": result
            }

            # Create headline from reasoning
            home_factor = (probs.get("reasoning", {}).get("home_factors", [""])[0])[:30] if probs.get("reasoning") else ""
            draw_factor = (probs.get("reasoning", {}).get("draw_factors", [""])[0])[:30] if probs.get("reasoning") else ""

            if result == "D":
                headline = f"Draw likely: {draw_factor}" if draw_factor else "Draw: balanced contest"
            elif result == "H":
                headline = f"Home edge: {home_factor}" if home_factor else "Home win expected"
            else:
                headline = f"Away edge: {(probs.get('reasoning', {}).get('away_factors', [''])[0])[:30]}"

            cursor.execute("""
                INSERT INTO analysis_reports
                (fixture_id, prompt_version, model_name, headline, predicted_score, confidence, full_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                fixture_id,
                "v5_prob",
                self.model,
                headline[:100],
                score,
                confidence,
                json.dumps(full_json)
            ))

            self.conn.commit()
            cursor.close()

        except Exception as e:
            print(f"Error saving to DB: {e}")
            self.conn.rollback()


# Convenience function
def predict_probabilistic(fixture_id: str) -> dict:
    """Quick function to get probabilistic prediction."""
    predictor = ProbabilisticPredictor()
    try:
        return predictor.predict(fixture_id)
    finally:
        predictor.close()


if __name__ == "__main__":
    # Test
    import sys
    if len(sys.argv) > 1:
        fixture_id = sys.argv[1]
    else:
        fixture_id = "2025-12-30_Arsenal_Aston_Villa"

    result = predict_probabilistic(fixture_id)
    print(json.dumps(result, indent=2))
