"""
Evaluator - Compare predictions against reality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json

from src.agents.base import AnalysisReport, MatchReality


@dataclass
class MatchEvaluation:
    """Evaluation of a single prediction vs reality."""
    
    fixture_id: str
    home_team: str
    away_team: str
    
    # Prediction
    predicted_result: Optional[str]
    predicted_scoreline: Optional[str]
    confidence: Optional[float]
    
    # Reality
    actual_result: str
    actual_scoreline: str
    
    # Evaluation
    result_correct: bool
    scoreline_correct: bool
    
    # Report quality (filled by LLM judge later)
    report_quality_score: Optional[float] = None
    report_quality_notes: Optional[str] = None


@dataclass 
class BacktestResults:
    """Aggregate results for a backtest run."""
    
    method: str  # "coded" or "openclaw"
    total_matches: int = 0
    
    # Accuracy
    correct_results: int = 0
    correct_scorelines: int = 0
    
    # By result type
    home_wins_predicted: int = 0
    home_wins_correct: int = 0
    draws_predicted: int = 0
    draws_correct: int = 0
    away_wins_predicted: int = 0
    away_wins_correct: int = 0
    
    # Timing/Cost
    total_time_seconds: float = 0.0
    total_tokens: int = 0
    
    # Individual evaluations
    evaluations: List[MatchEvaluation] = field(default_factory=list)
    
    @property
    def accuracy(self) -> float:
        if self.total_matches == 0:
            return 0.0
        return self.correct_results / self.total_matches
    
    @property
    def avg_time(self) -> float:
        if self.total_matches == 0:
            return 0.0
        return self.total_time_seconds / self.total_matches
    
    @property
    def avg_tokens(self) -> float:
        if self.total_matches == 0:
            return 0.0
        return self.total_tokens / self.total_matches


def evaluate_single(
    report: AnalysisReport,
    reality: MatchReality,
) -> MatchEvaluation:
    """Evaluate a single prediction against reality."""
    
    predicted = report.predicted_result
    actual = reality.result
    
    result_correct = predicted == actual if predicted else False
    
    # Check scoreline
    predicted_score = report.predicted_scoreline
    actual_score = f"{reality.home_score}-{reality.away_score}"
    scoreline_correct = predicted_score == actual_score if predicted_score else False
    
    # Get confidence
    confidence = None
    if predicted == "H" and report.home_win_prob:
        confidence = report.home_win_prob
    elif predicted == "D" and report.draw_prob:
        confidence = report.draw_prob
    elif predicted == "A" and report.away_win_prob:
        confidence = report.away_win_prob
    
    return MatchEvaluation(
        fixture_id=report.fixture_id,
        home_team=report.home_team,
        away_team=report.away_team,
        predicted_result=predicted,
        predicted_scoreline=predicted_score,
        confidence=confidence,
        actual_result=actual,
        actual_scoreline=actual_score,
        result_correct=result_correct,
        scoreline_correct=scoreline_correct,
    )


def evaluate_predictions(
    reports: List[AnalysisReport],
    realities: Dict[str, MatchReality],
    method: str = "coded",
) -> BacktestResults:
    """
    Evaluate all predictions against realities.
    
    Args:
        reports: List of analysis reports
        realities: Dict mapping fixture_id to MatchReality
        method: Agent method name
    
    Returns:
        BacktestResults with aggregate metrics
    """
    results = BacktestResults(method=method)
    
    for report in reports:
        # Find matching reality
        # Try direct fixture_id match first
        reality = realities.get(report.fixture_id)
        
        # If not found, try to match by teams
        if not reality:
            for fid, r in realities.items():
                if (r.home_team == report.home_team and 
                    r.away_team == report.away_team):
                    reality = r
                    break
        
        if not reality:
            continue
        
        # Evaluate
        eval_result = evaluate_single(report, reality)
        results.evaluations.append(eval_result)
        results.total_matches += 1
        
        # Update counters
        if eval_result.result_correct:
            results.correct_results += 1
        if eval_result.scoreline_correct:
            results.correct_scorelines += 1
        
        # Track by result type
        if report.predicted_result == "H":
            results.home_wins_predicted += 1
            if eval_result.result_correct:
                results.home_wins_correct += 1
        elif report.predicted_result == "D":
            results.draws_predicted += 1
            if eval_result.result_correct:
                results.draws_correct += 1
        elif report.predicted_result == "A":
            results.away_wins_predicted += 1
            if eval_result.result_correct:
                results.away_wins_correct += 1
        
        # Timing
        results.total_time_seconds += report.time_seconds
        results.total_tokens += report.tokens_used
    
    return results


def compare_methods(
    coded_results: BacktestResults,
    openclaw_results: BacktestResults,
) -> str:
    """Generate comparison report between two methods."""
    
    report = f"""
# Backtest Comparison Report

## Summary

| Metric | Coded Agent | OpenClaw Agent |
|--------|-------------|----------------|
| Matches | {coded_results.total_matches} | {openclaw_results.total_matches} |
| Accuracy | {coded_results.accuracy:.1%} | {openclaw_results.accuracy:.1%} |
| Correct Results | {coded_results.correct_results} | {openclaw_results.correct_results} |
| Exact Scorelines | {coded_results.correct_scorelines} | {openclaw_results.correct_scorelines} |
| Avg Time | {coded_results.avg_time:.1f}s | {openclaw_results.avg_time:.1f}s |
| Avg Tokens | {coded_results.avg_tokens:.0f} | {openclaw_results.avg_tokens:.0f} |

## By Result Type

### Home Wins
- Coded: {coded_results.home_wins_correct}/{coded_results.home_wins_predicted} predicted
- OpenClaw: {openclaw_results.home_wins_correct}/{openclaw_results.home_wins_predicted} predicted

### Draws
- Coded: {coded_results.draws_correct}/{coded_results.draws_predicted} predicted
- OpenClaw: {openclaw_results.draws_correct}/{openclaw_results.draws_predicted} predicted

### Away Wins
- Coded: {coded_results.away_wins_correct}/{coded_results.away_wins_predicted} predicted
- OpenClaw: {openclaw_results.away_wins_correct}/{openclaw_results.away_wins_predicted} predicted

## Individual Results

| Match | Coded | OpenClaw | Actual |
|-------|-------|----------|--------|
"""
    
    # Match up evaluations by fixture
    coded_by_teams = {(e.home_team, e.away_team): e for e in coded_results.evaluations}
    openclaw_by_teams = {(e.home_team, e.away_team): e for e in openclaw_results.evaluations}
    
    all_teams = set(coded_by_teams.keys()) | set(openclaw_by_teams.keys())
    
    for teams in sorted(all_teams):
        coded_eval = coded_by_teams.get(teams)
        openclaw_eval = openclaw_by_teams.get(teams)
        
        match_name = f"{teams[0]} vs {teams[1]}"
        
        coded_pred = "?"
        if coded_eval:
            mark = "✅" if coded_eval.result_correct else "❌"
            coded_pred = f"{coded_eval.predicted_result} {mark}"
        
        openclaw_pred = "?"
        if openclaw_eval:
            mark = "✅" if openclaw_eval.result_correct else "❌"
            openclaw_pred = f"{openclaw_eval.predicted_result} {mark}"
        
        actual = coded_eval.actual_scoreline if coded_eval else (
            openclaw_eval.actual_scoreline if openclaw_eval else "?"
        )
        
        report += f"| {match_name} | {coded_pred} | {openclaw_pred} | {actual} |\n"
    
    return report
