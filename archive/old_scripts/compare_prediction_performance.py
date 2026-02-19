#!/usr/bin/env python3
"""
Compare prediction performance: Old Context vs New Enriched Context

Tests on Round 23 and 24 fixtures:
- Old: ContextBuilderV2 (DB only) + best prompt
- New: EnrichedContextBuilder (DB + Agent) + best prompt

Metrics:
- Prediction accuracy (correct winner)
- Score accuracy (exact score)
- Both Teams to Score (BTTS)
- Over/Under 2.5 goals
"""

import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional
import json
from datetime import datetime

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import os
if not os.getenv("GEMINI_API_KEY"):
    from dotenv import load_dotenv
    load_dotenv()

from src.database.config import get_connection
from src.analysis.context_builder_v2 import ContextBuilderV2
from src.agents.enriched_context import EnrichedContextBuilder
import pandas as pd
from openai import OpenAI

# ============================================================
# CONFIGURATION
# ============================================================

BEST_PROMPT_VERSION = "v5_probabilistic"
ROUNDS_TO_TEST = [19, 20, 21]  # Latest 3 finished rounds
USE_AGENT_ENRICHMENT = False  # Disable for now due to API quotas
OPENAI_MODEL = "gpt-5.2"  # GPT-5.2

# Load prompt
PROMPTS_DIR = PROJECT_ROOT / "prompts"
PROBABILISTIC_PROMPT = (PROMPTS_DIR / f"{BEST_PROMPT_VERSION}.txt").read_text(encoding="utf-8")

# ============================================================
# PREDICTION ENGINE
# ============================================================

class ContextBasedPredictor:
    """Predictor that works with pre-built contexts."""

    def __init__(self, model: str = OPENAI_MODEL):
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def predict_from_context(self, context) -> Dict:
        """
        Generate prediction from a pre-built context.

        Args:
            context: MatchContext object (from V2 or V3 builder)

        Returns:
            Dict with prediction results
        """
        # Format context
        context_str = self._format_context(context)

        # Generate prompt
        full_prompt = f"{PROBABILISTIC_PROMPT}\n\nMATCH CONTEXT:\n{context_str}"

        try:
            # Get probabilities from OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a football prediction expert that provides probability analysis in JSON format."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )

            # Parse response
            text = response.choices[0].message.content.strip()

            # Extract JSON
            if "```json" in text:
                json_start = text.find("```json") + 7
                json_end = text.find("```", json_start)
                json_str = text[json_start:json_end].strip()
            elif "{" in text:
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                json_str = text[json_start:json_end]
            else:
                return {"error": "No JSON found in response"}

            probs = json.loads(json_str)

            # Decide result based on probabilities
            result = self._decide_result(probs)

            # Generate score
            score = self._generate_score(result, probs)

            # Calculate confidence
            confidence = self._calculate_confidence(probs, result)

            return {
                "most_likely_outcome": result,
                "outcome_probabilities": {
                    "home": probs.get("home_win_pct", 0) / 100,
                    "draw": probs.get("draw_pct", 0) / 100,
                    "away": probs.get("away_win_pct", 0) / 100
                },
                "predicted_score": score,
                "confidence": confidence,
                "both_teams_score_probability": probs.get("btts_pct", 50) / 100,
                "over_2_5_probability": probs.get("over_2_5_pct", 50) / 100,
                "expected_goals": probs.get("expected_total_goals", 2.5)
            }

        except Exception as e:
            return {"error": str(e)}

    def _format_context(self, context) -> str:
        """Format MatchContext to string for prompt."""
        lines = []

        # Teams
        lines.append(f"HOME: {context.home.identity.name}")
        lines.append(f"AWAY: {context.away.identity.name}")
        lines.append("")

        # Form
        lines.append(f"HOME FORM: {context.home.form.results} ({context.home.form.points} pts)")
        lines.append(f"AWAY FORM: {context.away.form.results} ({context.away.form.points} pts)")
        lines.append("")

        # Elo
        lines.append(f"HOME ELO: {context.home.identity.elo}")
        lines.append(f"AWAY ELO: {context.away.identity.elo}")
        lines.append("")

        # Injuries
        lines.append(f"HOME INJURIES: {context.home.absences.total_missing}")
        if context.home.absences.players:
            for p in context.home.absences.players[:5]:
                lines.append(f"  - {p.player_name} ({p.position}): {p.injury_type}")

        lines.append(f"AWAY INJURIES: {context.away.absences.total_missing}")
        if context.away.absences.players:
            for p in context.away.absences.players[:5]:
                lines.append(f"  - {p.player_name} ({p.position}): {p.injury_type}")

        lines.append("")

        # H2H
        lines.append(f"H2H: {context.head_to_head.matches_played} matches")
        lines.append(f"  Home wins: {context.head_to_head.home_wins}")
        lines.append(f"  Draws: {context.head_to_head.draws}")
        lines.append(f"  Away wins: {context.head_to_head.away_wins}")
        lines.append("")

        # League position
        lines.append(f"LEAGUE POSITION:")
        lines.append(f"  Home: {context.league_position.home_position}")
        lines.append(f"  Away: {context.league_position.away_position}")
        lines.append("")

        # Schedule
        lines.append(f"REST DAYS:")
        lines.append(f"  Home: {context.schedule.home_rest_days} days")
        lines.append(f"  Away: {context.schedule.away_rest_days} days")

        return "\n".join(lines)

    def _decide_result(self, probs: Dict) -> str:
        """Decide result based on probability thresholds."""
        home_pct = probs.get("home_win_pct", 0)
        draw_pct = probs.get("draw_pct", 0)
        away_pct = probs.get("away_win_pct", 0)

        if home_pct > away_pct and home_pct > draw_pct:
            return "HOME"
        elif away_pct > home_pct and away_pct > draw_pct:
            return "AWAY"
        else:
            return "DRAW"

    def _generate_score(self, result: str, probs: Dict) -> Dict:
        """Generate score consistent with result."""
        expected_goals = probs.get("expected_total_goals", 2.5)

        if result == "HOME":
            home = int(expected_goals * 0.6) + 1
            away = int(expected_goals * 0.4)
        elif result == "AWAY":
            home = int(expected_goals * 0.4)
            away = int(expected_goals * 0.6) + 1
        else:  # DRAW
            goals = int(expected_goals / 2)
            home = goals
            away = goals

        return {"home": home, "away": away}

    def _calculate_confidence(self, probs: Dict, result: str) -> float:
        """Calculate confidence in the prediction."""
        if result == "HOME":
            return probs.get("home_win_pct", 0) / 100
        elif result == "AWAY":
            return probs.get("away_win_pct", 0) / 100
        else:
            return probs.get("draw_pct", 0) / 100

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_fixtures_for_rounds(rounds: List[int]) -> pd.DataFrame:
    """Get all fixtures for specified rounds."""
    conn = get_connection()
    rounds_str = ','.join(map(str, rounds))

    query = f"""
        SELECT id, home_team, away_team, round, home_score, away_score, status
        FROM fixtures
        WHERE round IN ({rounds_str}) AND status = 'FINISHED'
        ORDER BY round, id
    """

    df = pd.read_sql(query, conn)
    conn.close()
    return df

def get_actual_outcome(home_score: int, away_score: int) -> Dict:
    """Extract actual outcome from match result."""
    total_goals = home_score + away_score

    if home_score > away_score:
        result = "HOME"
    elif away_score > home_score:
        result = "AWAY"
    else:
        result = "DRAW"

    return {
        "result": result,
        "home_score": home_score,
        "away_score": away_score,
        "total_goals": total_goals,
        "btts": home_score > 0 and away_score > 0,
        "over_2_5": total_goals > 2.5
    }

def evaluate_prediction(prediction: Dict, actual: Dict) -> Dict:
    """Evaluate prediction accuracy."""
    if "error" in prediction:
        return {"error": prediction["error"]}

    metrics = {}

    # Result accuracy
    pred_result = prediction.get("most_likely_outcome", "UNKNOWN")
    metrics["result_correct"] = (pred_result == actual["result"])

    # Exact score
    pred_home = prediction.get("predicted_score", {}).get("home", -1)
    pred_away = prediction.get("predicted_score", {}).get("away", -1)
    metrics["score_correct"] = (
        pred_home == actual["home_score"] and
        pred_away == actual["away_score"]
    )

    # BTTS
    pred_btts = prediction.get("both_teams_score_probability", 0) > 0.5
    metrics["btts_correct"] = (pred_btts == actual["btts"])

    # Over 2.5
    pred_over = prediction.get("over_2_5_probability", 0) > 0.5
    metrics["over_2_5_correct"] = (pred_over == actual["over_2_5"])

    # Confidence
    metrics["confidence"] = prediction.get("confidence", 0)

    return metrics

# ============================================================
# MAIN COMPARISON
# ============================================================

def main():
    print("=" * 80)
    print("PREDICTION PERFORMANCE COMPARISON")
    print("=" * 80)
    print(f"\nRounds: {ROUNDS_TO_TEST}")
    print(f"Agent Enrichment: {'ENABLED' if USE_AGENT_ENRICHMENT else 'DISABLED'}")
    print(f"Prompt: {BEST_PROMPT_VERSION}")
    print()

    # Get fixtures
    print("Fetching fixtures...")
    fixtures_df = get_fixtures_for_rounds(ROUNDS_TO_TEST)
    total_fixtures = len(fixtures_df)
    print(f"Found {total_fixtures} finished fixtures\n")

    if total_fixtures == 0:
        print("❌ No fixtures found")
        return

    # Initialize
    builder_old = ContextBuilderV2()
    builder_new = EnrichedContextBuilder(
        use_agent=USE_AGENT_ENRICHMENT,
        provider="openai"
    )
    predictor = ContextBasedPredictor()

    results_old = []
    results_new = []

    # Process each fixture
    for idx, row in fixtures_df.iterrows():
        fixture_id = row['id']
        home_team = row['home_team']
        away_team = row['away_team']
        round_num = row['round']

        print(f"\n[{idx+1}/{total_fixtures}] Round {round_num}: {home_team} vs {away_team}")
        print("-" * 80)

        actual = get_actual_outcome(row['home_score'], row['away_score'])
        print(f"  Actual: {actual['result']} ({actual['home_score']}-{actual['away_score']})")

        # OLD CONTEXT
        try:
            print("\n  [OLD] Building context (DB only)...")
            context_old = builder_old.build_context(fixture_id)

            print("  [OLD] Generating prediction...")
            prediction_old = predictor.predict_from_context(context_old)

            if "error" not in prediction_old:
                metrics_old = evaluate_prediction(prediction_old, actual)
                pred_result = prediction_old.get("most_likely_outcome", "?")
                pred_score = prediction_old.get("predicted_score", {})
                print(f"  [OLD] Predicted: {pred_result} ({pred_score.get('home', '?')}-{pred_score.get('away', '?')})")
                print(f"        Result: {'✓' if metrics_old['result_correct'] else '✗'} | "
                      f"Score: {'✓' if metrics_old['score_correct'] else '✗'} | "
                      f"Confidence: {metrics_old['confidence']:.0%}")

                results_old.append({
                    "fixture_id": fixture_id,
                    "round": round_num,
                    "home_team": home_team,
                    "away_team": away_team,
                    "prediction": prediction_old,
                    "actual": actual,
                    "metrics": metrics_old
                })
            else:
                print(f"  [OLD] ❌ Error: {prediction_old['error']}")
                results_old.append({"fixture_id": fixture_id, "error": prediction_old['error']})

        except Exception as e:
            print(f"  [OLD] ❌ Error: {e}")
            results_old.append({"fixture_id": fixture_id, "error": str(e)})

        # NEW CONTEXT
        try:
            print("\n  [NEW] Building enriched context...")
            result_new = builder_new.build_enriched_context(
                fixture_id,
                enrich_injuries=True,
                enrich_h2h=True,
                enrich_news=False
            )
            context_new = result_new.context

            if result_new.enrichment_applied:
                print(f"        Enrichment: {result_new.enrichment_quality:.0%} quality")

            print("  [NEW] Generating prediction...")
            prediction_new = predictor.predict_from_context(context_new)

            if "error" not in prediction_new:
                metrics_new = evaluate_prediction(prediction_new, actual)
                pred_result = prediction_new.get("most_likely_outcome", "?")
                pred_score = prediction_new.get("predicted_score", {})
                print(f"  [NEW] Predicted: {pred_result} ({pred_score.get('home', '?')}-{pred_score.get('away', '?')})")
                print(f"        Result: {'✓' if metrics_new['result_correct'] else '✗'} | "
                      f"Score: {'✓' if metrics_new['score_correct'] else '✗'} | "
                      f"Confidence: {metrics_new['confidence']:.0%}")

                results_new.append({
                    "fixture_id": fixture_id,
                    "round": round_num,
                    "home_team": home_team,
                    "away_team": away_team,
                    "prediction": prediction_new,
                    "actual": actual,
                    "metrics": metrics_new,
                    "enrichment_quality": result_new.enrichment_quality
                })
            else:
                print(f"  [NEW] ❌ Error: {prediction_new['error']}")
                results_new.append({"fixture_id": fixture_id, "error": prediction_new['error']})

        except Exception as e:
            print(f"  [NEW] ❌ Error: {e}")
            results_new.append({"fixture_id": fixture_id, "error": str(e)})

    # Close
    builder_old.close()
    builder_new.close()

    # Aggregate results
    print("\n" + "=" * 80)
    print("AGGREGATE RESULTS")
    print("=" * 80)

    valid_old = [r for r in results_old if "metrics" in r]
    valid_new = [r for r in results_new if "metrics" in r]

    print(f"\nValid predictions: OLD={len(valid_old)}/{total_fixtures}, NEW={len(valid_new)}/{total_fixtures}")

    if not valid_old or not valid_new:
        print("❌ Not enough valid predictions")
        return

    def calc_aggregate(results: List[Dict]) -> Dict:
        total = len(results)
        return {
            "total": total,
            "result_accuracy": sum(r["metrics"]["result_correct"] for r in results) / total,
            "score_accuracy": sum(r["metrics"]["score_correct"] for r in results) / total,
            "btts_accuracy": sum(r["metrics"]["btts_correct"] for r in results) / total,
            "over_2_5_accuracy": sum(r["metrics"]["over_2_5_correct"] for r in results) / total,
            "avg_confidence": sum(r["metrics"]["confidence"] for r in results) / total
        }

    agg_old = calc_aggregate(valid_old)
    agg_new = calc_aggregate(valid_new)

    # Print comparison
    print("\n" + "-" * 80)
    print("OLD CONTEXT (DB only)")
    print("-" * 80)
    print(f"Result Accuracy:    {agg_old['result_accuracy']:.1%} ({agg_old['result_accuracy']*agg_old['total']:.0f}/{agg_old['total']})")
    print(f"Exact Score:        {agg_old['score_accuracy']:.1%}")
    print(f"BTTS Accuracy:      {agg_old['btts_accuracy']:.1%}")
    print(f"Over/Under 2.5:     {agg_old['over_2_5_accuracy']:.1%}")
    print(f"Avg Confidence:     {agg_old['avg_confidence']:.1%}")

    print("\n" + "-" * 80)
    print("NEW CONTEXT (DB + Agent)")
    print("-" * 80)
    print(f"Result Accuracy:    {agg_new['result_accuracy']:.1%} ({agg_new['result_accuracy']*agg_new['total']:.0f}/{agg_new['total']})")
    print(f"Exact Score:        {agg_new['score_accuracy']:.1%}")
    print(f"BTTS Accuracy:      {agg_new['btts_accuracy']:.1%}")
    print(f"Over/Under 2.5:     {agg_new['over_2_5_accuracy']:.1%}")
    print(f"Avg Confidence:     {agg_new['avg_confidence']:.1%}")

    # Improvements
    print("\n" + "-" * 80)
    print("IMPROVEMENT (New vs Old)")
    print("-" * 80)

    result_diff = agg_new['result_accuracy'] - agg_old['result_accuracy']
    score_diff = agg_new['score_accuracy'] - agg_old['score_accuracy']

    def fmt_diff(diff: float) -> str:
        return f"{'+' if diff >= 0 else ''}{diff:.1%}"

    print(f"Result Accuracy:    {fmt_diff(result_diff)}")
    print(f"Exact Score:        {fmt_diff(score_diff)}")

    # Winner
    print("\n" + "=" * 80)
    if result_diff > 0:
        print(f"🏆 WINNER: NEW CONTEXT (+{result_diff:.1%} accuracy)")
    elif result_diff < 0:
        print(f"🏆 WINNER: OLD CONTEXT (+{abs(result_diff):.1%} accuracy)")
    else:
        print("🤝 TIE")
    print("=" * 80)

    # Save results
    output_file = PROJECT_ROOT / "docs" / "prediction_performance_comparison.json"
    with open(output_file, 'w') as f:
        json.dump({
            "metadata": {
                "rounds": ROUNDS_TO_TEST,
                "total_fixtures": total_fixtures,
                "timestamp": datetime.now().isoformat()
            },
            "aggregate": {"old": agg_old, "new": agg_new},
            "detailed": {"old": valid_old, "new": valid_new}
        }, f, indent=2, default=str)

    print(f"\n✓ Results saved to: {output_file}")

if __name__ == "__main__":
    main()
