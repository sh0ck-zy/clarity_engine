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
            # Extended query to fetch PPDA and Field Tilt
            query = """
                SELECT 
                    f.home_team, f.away_team, f.date, 
                    f.home_score, f.away_score,
                    MAX(CASE WHEN ts.is_home THEN ts.xg END) as xg_home,
                    MAX(CASE WHEN NOT ts.is_home THEN ts.xg END) as xg_away,
                    MAX(CASE WHEN ts.is_home THEN ts.ppda END) as ppda_home,
                    MAX(CASE WHEN NOT ts.is_home THEN ts.ppda END) as ppda_away,
                    MAX(CASE WHEN ts.is_home THEN ts.field_tilt END) as tilt_home,
                    MAX(CASE WHEN NOT ts.is_home THEN ts.field_tilt END) as tilt_away
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
                    "xg_home": float(row[5]) if row[5] is not None else 0.0,
                    "xg_away": float(row[6]) if row[6] is not None else 0.0,
                    "ppda_home": float(row[7]) if row[7] is not None else None,
                    "ppda_away": float(row[8]) if row[8] is not None else None,
                    "tilt_home": float(row[9]) if row[9] is not None else None,
                    "tilt_away": float(row[10]) if row[10] is not None else None,
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

            # 1. New Structure Parsing
            truth_vector = data.get("truth_vector", {})
            stat_audit = data.get("stat_audit", {})
            calibration = data.get("model_calibration_notes", {})

            # 2. Extract Score (Sanity Check or Fallback)
            score_block = data.get("score", {}) or {}
            score_str = score_block.get("final") or "0-0"
            try:
                sh, sa = map(int, score_str.split("-"))
            except:
                sh, sa = 0, 0 

            # 3. Map to Existing DB Columns
            luck_factor = str(truth_vector.get("luck_factor", "Normal"))

            narrative_summary = (
                f"AUDIT VERDICT: {stat_audit.get('explanation', 'No explanation provided.')}\n\n"
                f"LOSER ANALYSIS: {calibration.get('what_went_wrong_for_loser', 'N/A')}"
            )

            key_events = calibration.get("key_events", [])

            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO match_reality 
                (fixture_id, score_home, score_away, xg_home, xg_away, possession_home, 
                 key_events, narrative_summary, luck_factor, source_type)
                VALUES (%s, %s, %s, NULL, NULL, NULL, %s, %s, %s, 'forensic_auditor')
                ON CONFLICT (fixture_id) DO UPDATE SET
                narrative_summary = EXCLUDED.narrative_summary,
                luck_factor = EXCLUDED.luck_factor,
                key_events = EXCLUDED.key_events,
                source_type = 'forensic_auditor'
            """, (
                fixture_id,
                sh, sa,
                json.dumps(key_events),
                narrative_summary,
                luck_factor
            ))
            self.conn.commit()
            logger.info("💾 Forensic Truth saved to Database.")
        except Exception as e:
            logger.error(f"❌ Save Truth Error: {e}")
            if self.conn:
                self.conn.rollback()

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
        logger.info(f"🕵️  Forensic Audit for: {home_team} vs {away_team} on {match_date}")

        # Inject Internal Data if available
        internal_evidence = ""
        if db_stats:
            internal_evidence = f"""
            === INTERNAL LAB DATA (PRE-MATCH MODEL INPUTS) ===
            Final Score: {db_stats.get('home_score')} - {db_stats.get('away_score')}
            xG: {db_stats.get('xg_home')} (Home) vs {db_stats.get('xg_away')} (Away)
            PPDA: {db_stats.get('ppda_home', 'N/A')} (Home) vs {db_stats.get('ppda_away', 'N/A')} (Away)
            Field Tilt: {db_stats.get('tilt_home', 'N/A')}% (Home)
            Note: Compare these numbers against the match reports. Do they tell the full story?
            """

        prompt = f"""
ROLE:
You are a Forensic Football Auditor optimizing a predictive AI model.
Your goal is NOT to write a news report. Your goal is to **validate the match statistics** against qualitative match reports to create a "Ground Truth" dataset.

TARGET MATCH:
- {home_team} vs {away_team} ({match_date})
{internal_evidence}

INSTRUCTIONS:
1. **Search**: Find post-match reports (BBC, Sky, Whoscored, Analyst articles) to understand the *nature* of the game.
2. **Audit the Stats**: 
   - Does the xG reflect the dominance? (e.g. Did a team accumulate "junk xG" when 3-0 down?)
   - Was the result influenced by "High Variance" events (Red cards, penalties, massive errors)?
3. **Define the Truth**: Create a structured summary that we can programmatically compare against our pre-match prediction.

OUTPUT FORMAT (JSON ONLY):
Return raw JSON inside a fenced code block.
{{
  "meta": {{ "match": "{home_team} vs {away_team}" }},
  "score": {{ "final": "H-A" }},
  "truth_vector": {{
    "actual_winner": "Home/Away/Draw",
    "tactical_scenario": "One of: [Open End-to-End, Park the Bus, Midfield Attrition, Domination without Chances, Chaos/Transition]",
    "game_state_impact": "Did an early goal change the game flow? (Yes/No)",
    "luck_factor": "Score 0-10 (0=Pure Skill, 10=Pure Luck/Ref Error/Own Goal)"
  }},
  "stat_audit": {{
    "xg_fidelity": "High/Medium/Low (Do the xG stats accurately represent who played better?)",
    "stat_lie_detected": "Boolean (True if stats are misleading)",
    "explanation": "Short sentence explaining why stats might be misleading (if applicable)."
  }},
  "model_calibration_notes": {{
    "what_went_wrong_for_loser": "Tactical mismatch? Individual error? Fatigue?",
    "key_events": ["Red Card 15'", "Penalty Miss 88'", "Injury to Star Player"]
  }}
}}
"""

        # FIX: Usando nome de modelo mais estável e temperatura baixa em vez de response_mime_type
        response = self.client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt,
            config=GenerateContentConfig(
                tools=[Tool(google_search=GoogleSearch())],
                temperature=0.1 
            )
        )

        try:
            return self._parse_response_text(response.text)
        except Exception as e:
            logger.error(f"❌ JSON decode error: {e} — response was: {response.text}")
            return None

    def run_reality_check(self, fixture_id):
        # 1. Obter stats da BD
        db_stats = self._get_internal_stats(fixture_id)
        if not db_stats:
            logger.error(f"Fixture {fixture_id} not found in DB.")
            return None
        
        # 2. Chamar o Auditor (AI + Search)
        result = self.fetch_ground_truth(
            db_stats['home_team'],
            db_stats['away_team'],
            db_stats['date'],
            db_stats=db_stats
        )
        
        # 3. Salvar o resultado se existir
        if result:
            self._save_truth(fixture_id, result)
            return result
        return None

    def close(self):
        if self.conn:
            self.conn.close()