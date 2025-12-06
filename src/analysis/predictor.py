import os
import sys
import json
from openai import OpenAI
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.analysis.builder import MatchContextBuilder
from src.analysis.prompts import PROMPTS
from src.database.config import get_connection

load_dotenv()

class ClarityEngine:
    def __init__(self, model="gpt-4o"):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.builder = MatchContextBuilder()
        self.conn = get_connection()

    def _check_cache(self, fixture_id, prompt_key):
        """Checks DB for existing analysis."""
        if not self.conn: return None
        try:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT full_json FROM analysis_reports 
                WHERE fixture_id = %s AND prompt_version = %s AND model_name = %s
                ORDER BY created_at DESC LIMIT 1
            """, (fixture_id, prompt_key, self.model))
            row = cur.fetchone()
            if row:
                print("   ⚡ Cache Hit! Loaded from DB.")
                return row[0]
        except Exception as e:
            print(f"   ⚠️ Cache Check Error: {e}")
            self.conn.rollback()
        return None

    def _save_to_cache(self, fixture_id, prompt_key, data):
        """Saves new analysis to DB."""
        if not self.conn: return
        try:
            cur = self.conn.cursor()
            
            # Extract high-level fields for SQL columns
            headline = data.get("headline", "")
            pred = data.get("prediction", {})
            score = pred.get("scoreline", "")
            conf = pred.get("confidence", 0)
            rec = data.get("evidence_chain", {}).get("market_verdict", "")
            
            # Extract weights safely
            logic = data.get("glass_box_logic", {}) or data.get("weighting_decision", {})
            weights = json.dumps(logic.get("factor_weights", {}))

            cur.execute("""
                INSERT INTO analysis_reports 
                (fixture_id, prompt_version, model_name, headline, predicted_score, confidence, betting_recommendation, weights, full_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (fixture_id, prompt_key, self.model, headline, score, conf, rec, weights, json.dumps(data)))
            
            self.conn.commit()
            print("   💾 Saved to Database.")
        except Exception as e:
            print(f"   ❌ Save Error: {e}")
            self.conn.rollback()

    def run_analysis(self, fixture_id, prompt_key="hybrid", force_refresh=False):
        print(f"🧠 Analyzing {fixture_id} ({prompt_key})...")
        
        # 1. Check Cache
        if not force_refresh:
            cached = self._check_cache(fixture_id, prompt_key)
            if cached: return cached

        # 2. Build Context
        context = self.builder.build_context(fixture_id)
        if "error" in context:
            return {"error": context['error']}

        # 3. Get Prompt
        if prompt_key not in PROMPTS:
            return {"error": f"Prompt '{prompt_key}' not found"}
        system_prompt = PROMPTS[prompt_key]["text"]

        # 4. Call LLM
        try:
            print(f"   🔥 Sending to {self.model}...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(context)}
                ],
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
            
            # 5. Save
            self._save_to_cache(fixture_id, prompt_key, result)
            return result

        except Exception as e:
            print(f"❌ LLM Error: {e}")
            return {"error": str(e)}

    def close(self):
        self.builder.close()
        if self.conn: self.conn.close()

if __name__ == "__main__":
    # Test CLI
    engine = ClarityEngine()
    engine.run_analysis("2025-11-29_Sunderland_Bournemouth", "hybrid", force_refresh=True)
    engine.close()
