import os
import json
import logging
import sys
from pathlib import Path
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch

# Adicionar raiz ao path para imports se necessário
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RealitySeeker")


class RealitySeeker:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("❌ GEMINI_API_KEY not found!")
        self.client = genai.Client(api_key=api_key)
        self.conn = get_connection()

    def _get_internal_stats(self, fixture_id):
        if not self.conn:
            return None
        try:
            cur = self.conn.cursor()
            query = """
                SELECT 
                    f.home_team, f.away_team, f.date, 
                    f.home_score, f.away_score,
                    MAX(CASE WHEN ts.is_home THEN ts.xg END) as xg_home,
                    MAX(CASE WHEN NOT ts.is_home THEN ts.xg END) as xg_away
                FROM fixtures f
                LEFT JOIN team_stats ts ON f.id = ts.fixture_id
                WHERE f.id = %s
                GROUP BY f.id, f.home_team, f.away_team, f.date, f.home_score, f.away_score
            """
            cur.execute(query, (fixture_id,))
            row = cur.fetchone()
            if row:
                return {
                    "home_team": row[0],
                    "away_team": row[1],
                    "date": str(row[2]),
                    "home_score": row[3],
                    "away_score": row[4],
                    "xg_home": float(row[5]) if row[5] else 0.0,
                    "xg_away": float(row[6]) if row[6] else 0.0
                }
        except Exception as e:
            logger.error(f"❌ DB Fetch Error: {e}")
            if self.conn:
                self.conn.rollback()
        return None

    def _save_truth(self, fixture_id, data):
        if not self.conn:
            return
        try:
            if not isinstance(data, dict):
                logger.error("❌ Save Truth Error: data is not a dict")
                return

            # Extract structured fields with fallbacks
            score_block = data.get("score", {}) or {}
            stats_block = data.get("stats", {}) or {}
            prob_block = data.get("probabilistic_view", {}) or {}
            tactical_block = data.get("tactical_summary", {}) or {}

            score_str = score_block.get("final") or score_block.get("score") or "0-0"
            try:
                sh, sa = map(int, score_str.split("-"))
            except Exception:
                sh, sa = 0, 0

            def _float_or_none(val):
                try:
                    return float(val)
                except Exception:
                    return None

            def _int_or_none(val):
                try:
                    return int(val)
                except Exception:
                    return None

            xg_h = _float_or_none(stats_block.get("xg_home"))
            xg_a = _float_or_none(stats_block.get("xg_away"))
            poss_h = _int_or_none(stats_block.get("possession_home"))

            key_events = data.get("key_events", [])
            # Map richer narrative into existing columns
            narrative_summary = tactical_block.get("game_flow") or ""
            luck_factor = prob_block.get("luck_factor") or "Normal"

            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO match_reality 
                (fixture_id, score_home, score_away, xg_home, xg_away, possession_home, 
                 key_events, narrative_summary, luck_factor, source_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'google_search_grounding')
                ON CONFLICT (fixture_id) DO UPDATE SET
                narrative_summary = EXCLUDED.narrative_summary,
                luck_factor = EXCLUDED.luck_factor,
                key_events = EXCLUDED.key_events
            """, (
                fixture_id,
                sh, sa,
                xg_h, xg_a,
                poss_h,
                json.dumps(key_events),
                narrative_summary,
                luck_factor
            ))
            self.conn.commit()
            logger.info("💾 Truth saved to Database.")
        except Exception as e:
            logger.error(f"❌ Save Truth Error: {e}")
            if self.conn:
                self.conn.rollback()

    def run_reality_check(self, fixture_id):
        db_stats = self._get_internal_stats(fixture_id)
        if not db_stats:
            logger.error(f"Fixture {fixture_id} not found in DB.")
            return None
        result = self.fetch_ground_truth(
            db_stats['home_team'],
            db_stats['away_team'],
            db_stats['date'],
            db_stats=db_stats
        )
        if result:
            self._save_truth(fixture_id, result)
            return result
        return None

    @staticmethod
    def _parse_response_text(text: str):
        """
        Parse JSON da resposta, removendo fences ```json ... ```.
        """
        cleaned = text.strip()

        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if not lines:
                raise json.JSONDecodeError("Empty fenced block", cleaned, 0)

            first = lines[0].strip()
            if first.startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]

            cleaned = "\n".join(lines).strip()

        return json.loads(cleaned)

    def fetch_ground_truth(self, home_team, away_team, match_date, db_stats=None):
        logger.info(f"Investigating truth for: {home_team} vs {away_team} on {match_date}")

        reference = ""
        if db_stats:
            reference = f"""
--- INTERNAL REFERENCE DATA ---
My DB says: Score {db_stats.get('home_score')}-{db_stats.get('away_score')}.
xG: {db_stats.get('xg_home')} vs {db_stats.get('xg_away')}.
WARNING: Trust the web search if it contradicts this.
-------------------------------
"""

        prompt = f"""
ROLE:
You are a post-match auditor for a football analytics engine.
You MUST base everything on real published match reports and stats pages.

MATCH:
- Home: {home_team}
- Away: {away_team}
- Date: {match_date}

OBJECTIVE:
Produce a structured, non-hallucinated post-match report that can be compared against a pre-match prediction.
Separate raw facts, events, tactical interpretation, and fairness vs stats.

SEARCH REQUIREMENTS:
- Use web search tools to open multiple sources:
  - at least ONE traditional match report (BBC, Sky, Guardian, club sites)
  - at least ONE stats site if available (FotMob, Sofascore, WhoScored, Understat, Opta-powered)
- If stats like xG are not available, set them to null and state that in the analysis.
- Prefer agreement between sources. If sources disagree, mention it.

OUTPUT FORMAT (STRICT):
Return ONLY raw JSON. No markdown. No ```json fences. No text before/after JSON.
If you add ``` or any text outside JSON, the answer is INVALID.

The JSON MUST have exactly these fields:
{{
  "meta": {{
    "home_team": "{home_team}",
    "away_team": "{away_team}",
    "date": "{match_date}",
    "competition": "string or null",
    "sources": [
      "main_text_source_1",
      "main_text_source_2",
      "main_stats_source_1"
    ]
  }},
  "score": {{
    "final": "H-A",
    "ht_score": "H-A or null"
  }},
  "stats": {{
    "xg_home": "float or null",
    "xg_away": "float or null",
    "possession_home": "float or null",
    "shots_home": "int or null",
    "shots_away": "int or null",
    "shots_on_target_home": "int or null",
    "shots_on_target_away": "int or null",
    "big_chances_home": "int or null",
    "big_chances_away": "int or null"
  }},
  "key_events": [
    {{
      "minute": "int or null",
      "team": "home/away/neutral",
      "type": "goal/penalty/missed_penalty/red_card/yellow_card/injury/big_chance/save/other",
      "description": "short factual description based on sources"
    }}
  ],
  "tactical_summary": {{
    "game_flow": "objective description of how the game actually played out over 90 minutes",
    "home_approach": "what home tried to do with and without the ball",
    "away_approach": "what away tried to do with and without the ball",
    "turning_points": [
      "key moments that shifted control or win probability"
    ]
  }},
  "probabilistic_view": {{
    "did_result_match_stats": "yes/no/mixed",
    "explanation": "did the scoreline look fair given xG, chances and territory",
    "luck_factor": "Normal/Unlucky_for_home/Unlucky_for_away/High_Variance",
    "notes": "short explanation connecting stats to perceived luck or variance"
  }},
  "comparison_hooks": {{
    "dominant_zones": "who controlled territory and in what phases",
    "threat_profile_home": "how home created danger (crosses, cutbacks, counters, set pieces)",
    "threat_profile_away": "same for away",
    "structural_weaknesses_exposed": [
      "bulleted patterns that matter for model updates"
    ]
  }}
}}

CONSTRAINTS:
- Every field must be present. If you cannot find a value, set it to null.
- Do NOT invent players, events or stats. If not confirmed, leave null.
- Do NOT include ``` or any markdown formatting.
"""

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=GenerateContentConfig(
                tools=[Tool(google_search=GoogleSearch())],
                temperature=0.2
            )
        )

        try:
            return self._parse_response_text(response.text)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON decode error: {e} — response was: {response.text}")
            return None


    def close(self):
        if self.conn:
            self.conn.close()
