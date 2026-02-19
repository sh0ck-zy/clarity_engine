"""
Prompt Comparator - Dashboard v4

Compares analyses from different prompts for the same fixture.

Usage:
    from src.analysis.prompt_comparator import PromptComparator

    comparator = PromptComparator()
    analyses = comparator.get_analyses_for_fixture(fixture_id)
    comparison = comparator.compare_prompts(fixture_id, "v3", "hybrid")
"""

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection


@dataclass
class AnalysisReport:
    """Single analysis report from DB."""
    id: int
    fixture_id: str
    prompt_version: str
    model_name: Optional[str]
    created_at: datetime
    headline: Optional[str]
    predicted_score: Optional[str]
    confidence: Optional[int]
    betting_recommendation: Optional[str]
    weights: Optional[Dict]
    full_json: Optional[Dict]
    actual_score: Optional[str]
    is_correct: Optional[bool]
    pnl: Optional[float]


@dataclass
class MatchReality:
    """Actual match result."""
    fixture_id: str
    score_home: int
    score_away: int
    xg_home: Optional[float]
    xg_away: Optional[float]
    possession_home: Optional[float]
    key_events: Optional[Dict]
    narrative_summary: Optional[str]


@dataclass
class AnalysisComparison:
    """Side-by-side comparison of two analyses."""
    fixture_id: str
    home_team: str
    away_team: str
    match_date: Optional[str]

    analysis_a: Optional[AnalysisReport]
    analysis_b: Optional[AnalysisReport]

    reality: Optional[MatchReality]

    # Comparison results
    a_predicted_winner: Optional[str]  # "home", "draw", "away"
    b_predicted_winner: Optional[str]
    actual_winner: Optional[str]

    a_correct: Optional[bool]
    b_correct: Optional[bool]


class PromptComparator:
    """
    Compares analyses from different prompts.
    """

    def __init__(self):
        self.conn = get_connection()

    def close(self):
        if self.conn:
            self.conn.close()

    def get_available_prompts(self) -> List[str]:
        """Get list of all prompt versions used."""
        if not self.conn:
            return []

        cur = self.conn.cursor()
        cur.execute("""
            SELECT DISTINCT prompt_version
            FROM analysis_reports
            ORDER BY prompt_version
        """)
        return [row[0] for row in cur.fetchall()]

    def get_analyses_for_fixture(self, fixture_id: str) -> List[AnalysisReport]:
        """
        Get all analyses for a fixture.

        Args:
            fixture_id: Fixture ID

        Returns:
            List of AnalysisReport from different prompts
        """
        if not self.conn:
            return []

        cur = self.conn.cursor()
        cur.execute("""
            SELECT
                id, fixture_id, prompt_version, model_name, created_at,
                headline, predicted_score, confidence, betting_recommendation,
                weights, full_json, actual_score, is_correct, pnl
            FROM analysis_reports
            WHERE fixture_id = %s
            ORDER BY created_at DESC
        """, (fixture_id,))

        reports = []
        for row in cur.fetchall():
            reports.append(AnalysisReport(
                id=row[0],
                fixture_id=row[1],
                prompt_version=row[2],
                model_name=row[3],
                created_at=row[4],
                headline=row[5],
                predicted_score=row[6],
                confidence=row[7],
                betting_recommendation=row[8],
                weights=row[9],
                full_json=row[10],
                actual_score=row[11],
                is_correct=row[12],
                pnl=float(row[13]) if row[13] else None
            ))

        return reports

    def get_match_reality(self, fixture_id: str) -> Optional[MatchReality]:
        """
        Get actual match result.

        Args:
            fixture_id: Fixture ID

        Returns:
            MatchReality or None
        """
        if not self.conn:
            return None

        cur = self.conn.cursor()

        # Try match_reality table first
        cur.execute("""
            SELECT
                fixture_id, score_home, score_away, xg_home, xg_away,
                possession_home, key_events, narrative_summary
            FROM match_reality
            WHERE fixture_id = %s
        """, (fixture_id,))
        row = cur.fetchone()

        if row:
            return MatchReality(
                fixture_id=row[0],
                score_home=row[1],
                score_away=row[2],
                xg_home=float(row[3]) if row[3] else None,
                xg_away=float(row[4]) if row[4] else None,
                possession_home=float(row[5]) if row[5] else None,
                key_events=row[6],
                narrative_summary=row[7]
            )

        # Fallback to fixtures table
        cur.execute("""
            SELECT home_score, away_score
            FROM fixtures
            WHERE id = %s AND home_score IS NOT NULL
        """, (fixture_id,))
        row = cur.fetchone()

        if row:
            return MatchReality(
                fixture_id=fixture_id,
                score_home=row[0],
                score_away=row[1],
                xg_home=None,
                xg_away=None,
                possession_home=None,
                key_events=None,
                narrative_summary=None
            )

        return None

    def _parse_predicted_winner(self, predicted_score: Optional[str]) -> Optional[str]:
        """Parse predicted score to determine winner."""
        if not predicted_score:
            return None

        try:
            parts = predicted_score.replace("-", " ").split()
            if len(parts) >= 2:
                home = int(parts[0])
                away = int(parts[-1])  # Handle "2 - 1" or "2-1"
                if home > away:
                    return "home"
                elif away > home:
                    return "away"
                else:
                    return "draw"
        except (ValueError, IndexError):
            pass

        return None

    def _get_actual_winner(self, reality: Optional[MatchReality]) -> Optional[str]:
        """Determine actual winner from reality."""
        if not reality:
            return None

        if reality.score_home > reality.score_away:
            return "home"
        elif reality.score_away > reality.score_home:
            return "away"
        else:
            return "draw"

    def compare_prompts(
        self,
        fixture_id: str,
        prompt_a: str,
        prompt_b: str
    ) -> Optional[AnalysisComparison]:
        """
        Compare two prompts for the same fixture.

        Args:
            fixture_id: Fixture ID
            prompt_a: First prompt version
            prompt_b: Second prompt version

        Returns:
            AnalysisComparison or None
        """
        if not self.conn:
            return None

        # Get fixture info
        cur = self.conn.cursor()
        cur.execute("""
            SELECT home_team, away_team, date
            FROM fixtures
            WHERE id = %s
        """, (fixture_id,))
        fixture_row = cur.fetchone()

        if not fixture_row:
            return None

        home_team, away_team, match_date = fixture_row

        # Get analyses
        all_analyses = self.get_analyses_for_fixture(fixture_id)
        analysis_a = next((a for a in all_analyses if a.prompt_version == prompt_a), None)
        analysis_b = next((a for a in all_analyses if a.prompt_version == prompt_b), None)

        # Get reality
        reality = self.get_match_reality(fixture_id)
        actual_winner = self._get_actual_winner(reality)

        # Determine predictions
        a_predicted = self._parse_predicted_winner(analysis_a.predicted_score if analysis_a else None)
        b_predicted = self._parse_predicted_winner(analysis_b.predicted_score if analysis_b else None)

        # Determine correctness
        a_correct = (a_predicted == actual_winner) if a_predicted and actual_winner else None
        b_correct = (b_predicted == actual_winner) if b_predicted and actual_winner else None

        return AnalysisComparison(
            fixture_id=fixture_id,
            home_team=home_team,
            away_team=away_team,
            match_date=match_date.isoformat() if match_date else None,
            analysis_a=analysis_a,
            analysis_b=analysis_b,
            reality=reality,
            a_predicted_winner=a_predicted,
            b_predicted_winner=b_predicted,
            actual_winner=actual_winner,
            a_correct=a_correct,
            b_correct=b_correct
        )

    def get_fixtures_with_analyses(self, season: str = "2025-2026") -> List[Dict]:
        """
        Get all fixtures that have analyses.

        Args:
            season: Season string

        Returns:
            List of fixture info with analysis counts
        """
        if not self.conn:
            return []

        cur = self.conn.cursor()
        cur.execute("""
            SELECT
                f.id,
                f.home_team,
                f.away_team,
                f.date,
                f.round,
                f.home_score,
                f.away_score,
                COUNT(DISTINCT ar.prompt_version) as prompt_count,
                ARRAY_AGG(DISTINCT ar.prompt_version) as prompts
            FROM fixtures f
            LEFT JOIN analysis_reports ar ON f.id = ar.fixture_id
            WHERE f.season = %s
            GROUP BY f.id, f.home_team, f.away_team, f.date, f.round, f.home_score, f.away_score
            ORDER BY f.date DESC, f.home_team
        """, (season,))

        results = []
        for row in cur.fetchall():
            results.append({
                "fixture_id": row[0],
                "home_team": row[1],
                "away_team": row[2],
                "date": row[3].isoformat() if row[3] else None,
                "round": row[4],
                "home_score": row[5],
                "away_score": row[6],
                "prompt_count": row[7],
                "prompts": row[8] if row[8] and row[8][0] else []
            })

        return results


if __name__ == "__main__":
    comparator = PromptComparator()

    print("Available prompts:", comparator.get_available_prompts())
    print("=" * 60)

    # Get fixtures with analyses
    fixtures = comparator.get_fixtures_with_analyses()
    print(f"\nFixtures with analyses: {len([f for f in fixtures if f['prompt_count'] > 0])}")

    # Find a fixture with multiple analyses
    multi_analysis = [f for f in fixtures if f['prompt_count'] > 1]
    if multi_analysis:
        fixture = multi_analysis[0]
        print(f"\nComparing analyses for: {fixture['home_team']} vs {fixture['away_team']}")

        analyses = comparator.get_analyses_for_fixture(fixture['fixture_id'])
        for a in analyses:
            print(f"  - {a.prompt_version}: {a.predicted_score} (conf: {a.confidence})")

        # Compare first two prompts
        if len(analyses) >= 2:
            comparison = comparator.compare_prompts(
                fixture['fixture_id'],
                analyses[0].prompt_version,
                analyses[1].prompt_version
            )
            if comparison:
                print(f"\nComparison:")
                print(f"  A ({comparison.analysis_a.prompt_version}): predicted {comparison.a_predicted_winner}")
                print(f"  B ({comparison.analysis_b.prompt_version}): predicted {comparison.b_predicted_winner}")
                if comparison.reality:
                    print(f"  Reality: {comparison.reality.score_home}-{comparison.reality.score_away} ({comparison.actual_winner})")
                    print(f"  A correct: {comparison.a_correct}, B correct: {comparison.b_correct}")

    comparator.close()
