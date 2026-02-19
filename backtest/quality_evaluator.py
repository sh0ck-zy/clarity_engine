"""
Quality Evaluator - Compare agent analyses against reality using LLM judge.

This evaluates HOW WELL each agent read the game, not just if they got the result right.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

try:
    from .reality_builder import MatchReality, build_reality
except ImportError:
    from reality_builder import MatchReality, build_reality


@dataclass
class QualityScore:
    """Quality evaluation of an analysis."""
    
    fixture_id: str
    method: str  # "coded" or "openclaw"
    
    # Scores (1-10)
    game_reading: int  # Did they understand how the game would unfold?
    key_factors: int   # Did they identify the decisive factors?
    reasoning: int     # Was their logic sound?
    boldness: int      # Did they take a real stance?
    
    # Overall
    overall: float
    
    # Explanation
    explanation: str
    
    # What they got right/wrong
    correct_insights: List[str]
    missed_insights: List[str]


JUDGE_PROMPT = """You are evaluating football match predictions AFTER the match has been played.

Your job is to assess HOW WELL the analyst read the game - not just if they got the result right.
A good analysis that predicts the wrong result is better than a lucky guess with bad reasoning.

## MATCH REALITY
{reality}

## ANALYST'S PREDICTION (written BEFORE the match)
{analysis}

## EVALUATION CRITERIA

1. **Game Reading (1-10)**: Did they understand how the match would unfold?
   - Did they predict the flow correctly? (who would dominate, how goals would come)
   - Did they anticipate the tactical dynamic?
   - Even if result was wrong, did they see the patterns?

2. **Key Factors (1-10)**: Did they identify what would decide the game?
   - Did they spot the decisive elements?
   - Did they miss obvious factors?
   - Did they focus on relevant things or irrelevant noise?

3. **Reasoning Quality (1-10)**: Was their logic sound?
   - Did conclusions follow from evidence?
   - Were they specific or vague?
   - Did they avoid clichés and actually analyze?

4. **Boldness (1-10)**: Did they take a real stance?
   - Did they commit to a view or hedge everything?
   - Was their confidence calibrated?
   - Did they say something memorable?

## OUTPUT FORMAT
Return a JSON object with these fields:
- game_reading: 1-10
- key_factors: 1-10
- reasoning: 1-10
- boldness: 1-10
- overall: weighted average as float
- explanation: one paragraph
- correct_insights: list of strings
- missed_insights: list of strings

Be fair but critical. A result prediction being wrong doesn't mean the analysis was bad.
A correct prediction with "home team will win because they're at home" scores low.
"""


class QualityEvaluator:
    """Evaluates analysis quality using LLM judge."""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def evaluate(
        self,
        analysis_text: str,
        reality: MatchReality,
        method: str = "coded",
    ) -> QualityScore:
        """Evaluate a single analysis against reality."""
        
        # Build reality description
        reality_desc = self._format_reality(reality)
        
        # Call LLM judge
        prompt = JUDGE_PROMPT.format(
            reality=reality_desc,
            analysis=analysis_text,
        )
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        
        result_text = response.choices[0].message.content
        
        # Parse JSON
        try:
            if "```json" in result_text:
                json_start = result_text.find("```json") + 7
                json_end = result_text.find("```", json_start)
                json_str = result_text[json_start:json_end].strip()
            else:
                json_start = result_text.find("{")
                json_end = result_text.rfind("}") + 1
                json_str = result_text[json_start:json_end]
            
            data = json.loads(json_str)
            
            return QualityScore(
                fixture_id=reality.fixture_id,
                method=method,
                game_reading=data.get("game_reading", 5),
                key_factors=data.get("key_factors", 5),
                reasoning=data.get("reasoning", 5),
                boldness=data.get("boldness", 5),
                overall=data.get("overall", 5.0),
                explanation=data.get("explanation", ""),
                correct_insights=data.get("correct_insights", []),
                missed_insights=data.get("missed_insights", []),
            )
            
        except (json.JSONDecodeError, KeyError):
            return QualityScore(
                fixture_id=reality.fixture_id,
                method=method,
                game_reading=5,
                key_factors=5,
                reasoning=5,
                boldness=5,
                overall=5.0,
                explanation="Failed to parse evaluation",
                correct_insights=[],
                missed_insights=[],
            )
    
    def _format_reality(self, r: MatchReality) -> str:
        """Format reality for the judge."""
        
        lines = [
            f"**Final Score**: {r.home_team} {r.home_score}-{r.away_score} {r.away_team}",
            f"**Result**: {'Home Win' if r.result == 'H' else 'Away Win' if r.result == 'A' else 'Draw'}",
        ]
        
        if r.home_xg and r.away_xg:
            lines.append(f"**xG**: {r.home_xg:.2f} - {r.away_xg:.2f}")
        
        if r.home_possession:
            lines.append(f"**Possession**: {r.home_team} {r.home_possession}%")
        
        if r.home_shots and r.away_shots:
            lines.append(f"**Shots**: {r.home_shots} - {r.away_shots}")
        
        if r.goals:
            lines.append("\n**Goals**:")
            for g in r.goals:
                team = r.away_team if not g.get('is_home') else r.home_team
                lines.append(f"  - {g.get('time')}' {g.get('player_name')} ({team})")
        
        if r.match_narrative:
            lines.append(f"\n**What happened**: {r.match_narrative}")
        
        if r.insights:
            lines.append("\n**Pre-match context that proved relevant**:")
            for insight in r.insights[:3]:
                lines.append(f"  - {insight}")
        
        return "\n".join(lines)


def compare_analyses(
    fixture_id: str,
    coded_report_path: Path,
    openclaw_report_path: Path,
) -> dict:
    """Compare two analyses for the same match."""
    
    evaluator = QualityEvaluator()
    reality = build_reality(fixture_id)
    
    if not reality:
        return {"error": f"No reality data for {fixture_id}"}
    
    # Load reports
    coded_text = coded_report_path.read_text() if coded_report_path.exists() else ""
    openclaw_text = openclaw_report_path.read_text() if openclaw_report_path.exists() else ""
    
    # Evaluate
    coded_score = evaluator.evaluate(coded_text, reality, "coded")
    openclaw_score = evaluator.evaluate(openclaw_text, reality, "openclaw")
    
    return {
        "fixture_id": fixture_id,
        "match": f"{reality.home_team} {reality.home_score}-{reality.away_score} {reality.away_team}",
        "coded": {
            "overall": coded_score.overall,
            "game_reading": coded_score.game_reading,
            "key_factors": coded_score.key_factors,
            "reasoning": coded_score.reasoning,
            "boldness": coded_score.boldness,
            "explanation": coded_score.explanation,
            "correct": coded_score.correct_insights,
            "missed": coded_score.missed_insights,
        },
        "openclaw": {
            "overall": openclaw_score.overall,
            "game_reading": openclaw_score.game_reading,
            "key_factors": openclaw_score.key_factors,
            "reasoning": openclaw_score.reasoning,
            "boldness": openclaw_score.boldness,
            "explanation": openclaw_score.explanation,
            "correct": openclaw_score.correct_insights,
            "missed": openclaw_score.missed_insights,
        },
        "winner": "coded" if coded_score.overall > openclaw_score.overall else "openclaw" if openclaw_score.overall > coded_score.overall else "tie",
    }


if __name__ == "__main__":
    # Test with Burnley vs West Ham
    from pathlib import Path
    
    base = Path("output/backtest")
    coded_dir = base / "coded_R25_20260219_111117"
    openclaw_dir = base / "openclaw_R25_20260219_111228"
    
    # Find Burnley match
    fixture_id = "4813618"  # Burnley vs West Ham
    
    coded_path = coded_dir / "2026-02-07_Burnley_West_Ham_United.md"
    openclaw_path = openclaw_dir / "2026-02-07_Burnley_West_Ham_United.md"
    
    if coded_path.exists() and openclaw_path.exists():
        result = compare_analyses(fixture_id, coded_path, openclaw_path)
        print(json.dumps(result, indent=2))
    else:
        print(f"Files not found")
        print(f"Coded: {coded_path.exists()}")
        print(f"OpenClaw: {openclaw_path.exists()}")
