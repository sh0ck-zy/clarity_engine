import os
import json
import logging
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AnalysisEvaluator")


class AnalysisEvaluator:
    """Evaluates pre-match analyses against post-match reality using LLM."""
    
    def __init__(self, model="gpt-5.1"):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.error("❌ OPENAI_API_KEY not found!")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
        self.conn = get_connection()
        
        # Load evaluator prompt
        PROMPTS_DIR = PROJECT_ROOT / "prompts"
        prompt_file = PROMPTS_DIR / "v4_evaluator.txt"
        if prompt_file.exists():
            self.evaluator_prompt = prompt_file.read_text(encoding="utf-8")
        else:
            logger.error(f"❌ Evaluator prompt not found at {prompt_file}")
            self.evaluator_prompt = ""
    
    def _get_analysis_report(self, report_id):
        """Fetch analysis report from database."""
        if not self.conn:
            return None
        try:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT id, fixture_id, prompt_version, full_json, predicted_score, 
                       betting_recommendation, confidence
                FROM analysis_reports
                WHERE id = %s
            """, (report_id,))
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "fixture_id": row[1],
                    "prompt_version": row[2],
                    "full_json": row[3] if isinstance(row[3], dict) else json.loads(row[3]) if row[3] else {},
                    "predicted_score": row[4],
                    "betting_recommendation": row[5],
                    "confidence": row[6]
                }
        except Exception as e:
            logger.error(f"❌ Error fetching analysis report: {e}")
            if self.conn:
                self.conn.rollback()
        return None
    
    def _get_match_reality(self, fixture_id):
        """Fetch post-match reality from database."""
        if not self.conn:
            return None
        try:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT score_home, score_away, narrative_summary, key_events, 
                       luck_factor, xg_home, xg_away
                FROM match_reality
                WHERE fixture_id = %s
            """, (fixture_id,))
            row = cur.fetchone()
            if row:
                key_events = row[3]
                if isinstance(key_events, str):
                    try:
                        key_events = json.loads(key_events)
                    except:
                        key_events = []
                elif key_events is None:
                    key_events = []
                    
                return {
                    "score_home": row[0],
                    "score_away": row[1],
                    "narrative_summary": row[2],
                    "key_events": key_events,
                    "luck_factor": row[4],
                    "xg_home": float(row[5]) if row[5] is not None else None,
                    "xg_away": float(row[6]) if row[6] is not None else None,
                    "actual_score": f"{row[0]}-{row[1]}" if row[0] is not None and row[1] is not None else None
                }
        except Exception as e:
            logger.error(f"❌ Error fetching match reality: {e}")
            if self.conn:
                self.conn.rollback()
        return None
    
    def _build_evaluation_prompt(self, analysis, reality):
        """Build the prompt for LLM evaluation."""
        analysis_json = analysis.get("full_json", {})
        narrative = analysis_json.get("narrative", {})
        prediction = analysis_json.get("prediction", {})
        logic = analysis_json.get("glass_box_logic", {}) or analysis_json.get("weighting_decision", {})
        
        # Get predicted score from analysis or full_json
        predicted_score = analysis.get('predicted_score') or prediction.get('scoreline', 'N/A')
        betting_rec = analysis.get('betting_recommendation') or analysis_json.get("evidence_chain", {}).get("market_verdict", 'N/A')
        
        prompt = f"""
{self.evaluator_prompt}

=== PRE-MATCH ANALYSIS ===
Narrative/Game Flow: {narrative.get('game_flow', 'N/A')}
Tactical Dynamic: {narrative.get('tactical_dynamic', 'N/A')}
Predicted Score: {predicted_score}
Betting Recommendation: {betting_rec}
Confidence: {analysis.get('confidence', 'N/A')}%
Reasoning: {logic.get('reasoning', 'N/A')}
Factor Weights: {json.dumps(logic.get('factor_weights', {}), indent=2)}

=== POST-MATCH REALITY ===
Actual Score: {reality.get('actual_score', 'N/A')}
Narrative Summary: {reality.get('narrative_summary', 'N/A')}
Key Events: {', '.join(reality.get('key_events', [])) if reality.get('key_events') else 'None'}
Luck Factor: {reality.get('luck_factor', 'N/A')}
xG: {reality.get('xg_home', 'N/A')} (Home) vs {reality.get('xg_away', 'N/A')} (Away)

Evaluate this analysis across the 3 dimensions as specified.
"""
        return prompt
    
    def evaluate_analysis(self, report_id, force_refresh=False):
        """
        Evaluate a single analysis report against post-match reality.
        
        Args:
            report_id: ID of the analysis_report to evaluate
            force_refresh: If True, re-evaluate even if evaluation exists
        
        Returns:
            dict: Evaluation result or None if error
        """
        # Check if evaluation already exists
        if not force_refresh and self.conn:
            try:
                cur = self.conn.cursor()
                cur.execute("""
                    SELECT evaluation_json FROM analysis_evaluations
                    WHERE report_id = %s
                    ORDER BY created_at DESC LIMIT 1
                """, (report_id,))
                row = cur.fetchone()
                if row and row[0]:
                    logger.info(f"   ⚡ Evaluation cache hit for report {report_id}")
                    return row[0] if isinstance(row[0], dict) else json.loads(row[0])
            except Exception as e:
                logger.warning(f"   ⚠️ Cache check error: {e}")
                if self.conn:
                    self.conn.rollback()
        
        # Fetch analysis and reality
        analysis = self._get_analysis_report(report_id)
        if not analysis:
            logger.error(f"❌ Analysis report {report_id} not found")
            return None
        
        reality = self._get_match_reality(analysis["fixture_id"])
        if not reality:
            logger.error(f"❌ Match reality not found for fixture {analysis['fixture_id']}")
            return None
        
        if not reality.get("actual_score"):
            logger.warning(f"⚠️ No actual score available for fixture {analysis['fixture_id']}")
            return None
        
        # Build prompt and call LLM
        try:
            logger.info(f"🔍 Evaluating analysis {report_id} ({analysis['prompt_version']})...")
            prompt = self._build_evaluation_prompt(analysis, reality)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.evaluator_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Save evaluation
            self._save_evaluation(report_id, analysis, result)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ LLM evaluation error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _save_evaluation(self, report_id, analysis, evaluation_data):
        """Save evaluation to database."""
        if not self.conn:
            return
        
        try:
            narrative_quality = evaluation_data.get("narrative_quality", {})
            score_pred = evaluation_data.get("score_prediction", {})
            betting_tip = evaluation_data.get("betting_tip", {})
            
            cur = self.conn.cursor()
            # Check if evaluation exists
            cur.execute("SELECT id FROM analysis_evaluations WHERE report_id = %s", (report_id,))
            exists = cur.fetchone()
            
            if exists:
                # Update existing
                cur.execute("""
                    UPDATE analysis_evaluations SET
                        narrative_score = %s,
                        narrative_feedback = %s,
                        narrative_critical_flags = %s,
                        score_accuracy = %s,
                        score_explanation = %s,
                        tip_accuracy = %s,
                        tip_explanation = %s,
                        evaluation_json = %s,
                        created_at = NOW()
                    WHERE report_id = %s
                """, (
                    narrative_quality.get("score"),
                    narrative_quality.get("feedback"),
                    json.dumps(narrative_quality.get("critical_flags", [])),
                    score_pred.get("accuracy"),
                    score_pred.get("explanation"),
                    betting_tip.get("accuracy"),
                    betting_tip.get("explanation"),
                    json.dumps(evaluation_data),
                    report_id
                ))
            else:
                # Insert new
                cur.execute("""
                    INSERT INTO analysis_evaluations 
                    (report_id, fixture_id, prompt_version,
                     narrative_score, narrative_feedback, narrative_critical_flags,
                     score_accuracy, score_explanation,
                     tip_accuracy, tip_explanation,
                     evaluation_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    report_id,
                    analysis["fixture_id"],
                    analysis["prompt_version"],
                    narrative_quality.get("score"),
                    narrative_quality.get("feedback"),
                    json.dumps(narrative_quality.get("critical_flags", [])),
                    score_pred.get("accuracy"),
                    score_pred.get("explanation"),
                    betting_tip.get("accuracy"),
                    betting_tip.get("explanation"),
                    json.dumps(evaluation_data)
                ))
            
            self.conn.commit()
            logger.info("   💾 Evaluation saved to database")
            
        except Exception as e:
            logger.error(f"❌ Error saving evaluation: {e}")
            if self.conn:
                self.conn.rollback()
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


if __name__ == "__main__":
    # Test
    evaluator = AnalysisEvaluator()
    # Test with a report_id - update with actual ID
    # result = evaluator.evaluate_analysis(1)
    # print(json.dumps(result, indent=2))
    evaluator.close()

