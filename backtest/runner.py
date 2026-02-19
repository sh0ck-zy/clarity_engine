"""
Backtest Runner - Orchestrates the full backtest process.

Usage:
    python -m backtest.runner --rounds 25 26 --methods coded openclaw
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.agents.base import AnalysisReport
from src.agents.coded import CodedAgent
# from src.agents.openclaw import OpenClawAgent  # Uncomment when ready

from .fixtures import get_round_fixtures, get_fixtures_range, Fixture
from .reality import get_round_realities, get_match_reality
from .evaluator import evaluate_predictions, compare_methods, BacktestResults


class BacktestRunner:
    """
    Orchestrates backtest of multiple agents across multiple rounds.
    """
    
    def __init__(
        self,
        output_dir: str = "output/backtest",
        max_workers: int = 3,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers
        
        # Initialize agents
        self.coded_agent = CodedAgent()
        # self.openclaw_agent = OpenClawAgent()
    
    def run(
        self,
        rounds: List[int],
        methods: List[str] = ["coded"],
        parallel: bool = True,
    ) -> dict:
        """
        Run backtest for specified rounds and methods.
        
        Args:
            rounds: List of round numbers to backtest
            methods: List of methods ("coded", "openclaw")
            parallel: Whether to run analyses in parallel
        
        Returns:
            Dict with results for each method
        """
        print(f"\n{'='*60}")
        print(f"BACKTEST: Rounds {rounds}, Methods {methods}")
        print(f"{'='*60}\n")
        
        # Get all fixtures
        fixtures = []
        for r in rounds:
            round_fixtures = get_round_fixtures(r)
            print(f"Round {r}: {len(round_fixtures)} fixtures")
            fixtures.extend(round_fixtures)
        
        print(f"\nTotal: {len(fixtures)} fixtures to analyze\n")
        
        # Get realities
        realities = {}
        for r in rounds:
            realities.update(get_round_realities(r))
        print(f"Realities loaded: {len(realities)} completed matches\n")
        
        # Run each method
        all_results = {}
        
        for method in methods:
            print(f"\n--- Running {method.upper()} agent ---\n")
            
            if method == "coded":
                reports = self._run_coded(fixtures, parallel)
            elif method == "openclaw":
                reports = self._run_openclaw(fixtures, parallel)
            else:
                print(f"Unknown method: {method}")
                continue
            
            # Evaluate
            results = evaluate_predictions(reports, realities, method)
            all_results[method] = results
            
            # Print summary
            print(f"\n{method.upper()} Results:")
            print(f"  Accuracy: {results.accuracy:.1%} ({results.correct_results}/{results.total_matches})")
            print(f"  Avg Time: {results.avg_time:.1f}s")
            print(f"  Avg Tokens: {results.avg_tokens:.0f}")
            
            # Save reports
            self._save_reports(reports, method, rounds)
        
        # Compare if both methods run
        if "coded" in all_results and "openclaw" in all_results:
            comparison = compare_methods(all_results["coded"], all_results["openclaw"])
            print(comparison)
            
            # Save comparison
            comparison_path = self.output_dir / f"comparison_R{'_'.join(map(str, rounds))}.md"
            comparison_path.write_text(comparison)
            print(f"\nComparison saved to: {comparison_path}")
        
        return all_results
    
    def _run_coded(
        self,
        fixtures: List[Fixture],
        parallel: bool = True,
    ) -> List[AnalysisReport]:
        """Run coded agent on all fixtures."""
        
        reports = []
        
        if parallel and len(fixtures) > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(
                        self._analyze_coded,
                        f.home_team_id,
                        f.away_team_id,
                        f.round_number,
                        f.match_date,
                    ): f
                    for f in fixtures
                }
                
                for future in as_completed(futures):
                    fixture = futures[future]
                    try:
                        report = future.result()
                        reports.append(report)
                        mark = "✓" if report.predicted_result else "?"
                        print(f"  {mark} {fixture.home_team} vs {fixture.away_team}: {report.predicted_result or '?'} ({report.time_seconds:.1f}s)")
                    except Exception as e:
                        print(f"  ✗ {fixture.home_team} vs {fixture.away_team}: Error - {e}")
        else:
            for f in fixtures:
                try:
                    report = self._analyze_coded(
                        f.home_team_id,
                        f.away_team_id,
                        f.round_number,
                        f.match_date,
                    )
                    reports.append(report)
                    mark = "✓" if report.predicted_result else "?"
                    print(f"  {mark} {f.home_team} vs {f.away_team}: {report.predicted_result or '?'} ({report.time_seconds:.1f}s)")
                except Exception as e:
                    print(f"  ✗ {f.home_team} vs {f.away_team}: Error - {e}")
        
        return reports
    
    def _analyze_coded(
        self,
        home_team_id: int,
        away_team_id: int,
        round_number: int,
        match_date,
    ) -> AnalysisReport:
        """Run single coded analysis."""
        return self.coded_agent.analyze(
            home_team=home_team_id,
            away_team=away_team_id,
            round_number=round_number,
            match_date=match_date,
            backtest_mode=True,
        )
    
    def _run_openclaw(
        self,
        fixtures: List[Fixture],
        parallel: bool = True,
    ) -> List[AnalysisReport]:
        """Run OpenClaw agent on all fixtures."""
        # TODO: Implement when OpenClaw wrapper is ready
        print("OpenClaw agent not yet implemented")
        return []
    
    def _save_reports(
        self,
        reports: List[AnalysisReport],
        method: str,
        rounds: List[int],
    ) -> None:
        """Save reports to disk."""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rounds_str = "_".join(map(str, rounds))
        
        # Save individual reports
        reports_dir = self.output_dir / f"{method}_R{rounds_str}_{timestamp}"
        reports_dir.mkdir(exist_ok=True)
        
        for report in reports:
            # Save markdown report
            report_path = reports_dir / f"{report.fixture_id}.md"
            report_path.write_text(report.report_markdown or "No report")
            
            # Save metadata
            meta_path = reports_dir / f"{report.fixture_id}.json"
            meta = {
                "fixture_id": report.fixture_id,
                "home_team": report.home_team,
                "away_team": report.away_team,
                "round_number": report.round_number,
                "predicted_result": report.predicted_result,
                "predicted_scoreline": report.predicted_scoreline,
                "home_win_prob": report.home_win_prob,
                "draw_prob": report.draw_prob,
                "away_win_prob": report.away_win_prob,
                "recommended_bet": report.recommended_bet,
                "tools_used": report.tools_used,
                "tokens_used": report.tokens_used,
                "time_seconds": report.time_seconds,
                "model": report.model,
            }
            meta_path.write_text(json.dumps(meta, indent=2))
        
        print(f"\nReports saved to: {reports_dir}")


def main():
    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument(
        "--rounds", "-r",
        type=int,
        nargs="+",
        default=[25],
        help="Round numbers to backtest (e.g., --rounds 25 26)"
    )
    parser.add_argument(
        "--methods", "-m",
        type=str,
        nargs="+",
        default=["coded"],
        choices=["coded", "openclaw"],
        help="Methods to test"
    )
    parser.add_argument(
        "--parallel", "-p",
        action="store_true",
        default=True,
        help="Run analyses in parallel"
    )
    parser.add_argument(
        "--sequential", "-s",
        action="store_true",
        help="Run analyses sequentially (no parallel)"
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=3,
        help="Max parallel workers"
    )
    
    args = parser.parse_args()
    
    runner = BacktestRunner(max_workers=args.workers)
    runner.run(
        rounds=args.rounds,
        methods=args.methods,
        parallel=not args.sequential,
    )


if __name__ == "__main__":
    main()
