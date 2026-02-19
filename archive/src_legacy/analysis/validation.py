"""
Validation Engine - Narrative Quality Focused (NO BETTING/ROI)

This module validates the quality of football match analyses by comparing
predictions against post-match reality. Focus is on narrative accuracy,
tactical understanding, and systematic error identification.

Phase 1 Goal: Achieve 80+ Narrative Score in 90% of analyses
"""

import pandas as pd
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection


class ValidationEngine:
    """
    Validates analysis quality with focus on narrative/tactical accuracy.
    NO betting, ROI, or financial metrics - pure analytical validation.
    """

    def __init__(self):
        self.conn = get_connection()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    # ========================================
    # 1. DATA FETCHING
    # ========================================

    def get_validation_data(
        self,
        season: str = "2025-2026",
        prompt_version: Optional[str] = None,
        min_confidence: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch complete validation dataset: analyses + evaluations + reality.

        Args:
            season: Season to analyze
            prompt_version: Filter by specific prompt (None = all)
            min_confidence: Minimum confidence threshold (None = all)

        Returns:
            DataFrame with all validation data
        """
        if not self.conn:
            return pd.DataFrame()

        query = """
            SELECT
                f.id as fixture_id,
                f.home_team,
                f.away_team,
                f.date,
                f.round,
                f.home_score as actual_home,
                f.away_score as actual_away,

                ar.id as report_id,
                ar.prompt_version,
                ar.confidence,
                ar.predicted_score,
                ar.betting_recommendation,
                ar.full_json,

                ae.narrative_score,
                ae.narrative_feedback,
                ae.narrative_critical_flags,
                ae.score_accuracy,
                ae.score_explanation,
                ae.tip_accuracy,
                ae.tip_explanation,
                ae.evaluation_json,

                mr.score_home as reality_home,
                mr.score_away as reality_away,
                mr.narrative_summary,
                mr.luck_factor,
                mr.xg_home,
                mr.xg_away

            FROM fixtures f
            JOIN analysis_reports ar ON f.id = ar.fixture_id
            JOIN analysis_evaluations ae ON ar.id = ae.report_id
            JOIN match_reality mr ON f.id = mr.fixture_id

            WHERE f.season = %s
              AND f.status = 'FINISHED'
        """

        params = [season]

        if prompt_version:
            query += " AND ar.prompt_version = %s"
            params.append(prompt_version)

        if min_confidence is not None:
            query += " AND ar.confidence >= %s"
            params.append(min_confidence)

        query += " ORDER BY f.date ASC"

        try:
            df = pd.read_sql(query, self.conn, params=tuple(params))

            # Parse JSON columns
            if 'narrative_critical_flags' in df.columns:
                df['critical_flags_list'] = df['narrative_critical_flags'].apply(
                    lambda x: json.loads(x) if isinstance(x, str) else (x if isinstance(x, list) else [])
                )

            # Calculate outcome (W/D/L)
            df['actual_outcome'] = df.apply(
                lambda row: 'W' if row['actual_home'] > row['actual_away']
                else ('L' if row['actual_home'] < row['actual_away'] else 'D'),
                axis=1
            )

            # Parse predicted score to get predicted outcome
            df['predicted_outcome'] = df['predicted_score'].apply(self._parse_predicted_outcome)

            return df

        except Exception as e:
            print(f"❌ Error fetching validation data: {e}")
            return pd.DataFrame()

    def _parse_predicted_outcome(self, score_str: str) -> str:
        """Parse predicted score string to W/D/L outcome."""
        if not score_str or not isinstance(score_str, str):
            return None
        try:
            parts = score_str.split('-')
            if len(parts) == 2:
                home = int(parts[0].strip())
                away = int(parts[1].strip())
                return 'W' if home > away else ('L' if home < away else 'D')
        except:
            pass
        return None

    # ========================================
    # 2. NARRATIVE QUALITY METRICS
    # ========================================

    def calculate_narrative_metrics(self, df: pd.DataFrame) -> Dict:
        """
        Calculate narrative quality metrics (0-100 scale).

        Returns:
            {
                'avg_score': float,
                'excellent_rate': float,  # % with score >80
                'good_rate': float,       # % with score >60
                'poor_rate': float,       # % with score <50
                'score_distribution': dict
            }
        """
        if df.empty:
            return {
                'avg_score': 0,
                'excellent_rate': 0,
                'good_rate': 0,
                'poor_rate': 0,
                'score_distribution': {}
            }

        scores = df['narrative_score'].dropna()

        if len(scores) == 0:
            return {
                'avg_score': 0,
                'excellent_rate': 0,
                'good_rate': 0,
                'poor_rate': 0,
                'score_distribution': {}
            }

        # Calculate percentages
        excellent = (scores >= 80).sum()
        good = (scores >= 60).sum()
        poor = (scores < 50).sum()
        total = len(scores)

        # Score distribution by ranges
        distribution = {
            '90-100': ((scores >= 90) & (scores <= 100)).sum(),
            '80-89': ((scores >= 80) & (scores < 90)).sum(),
            '70-79': ((scores >= 70) & (scores < 80)).sum(),
            '60-69': ((scores >= 60) & (scores < 70)).sum(),
            '50-59': ((scores >= 50) & (scores < 60)).sum(),
            '0-49': (scores < 50).sum()
        }

        return {
            'avg_score': float(scores.mean()),
            'median_score': float(scores.median()),
            'excellent_rate': (excellent / total) * 100,
            'good_rate': (good / total) * 100,
            'poor_rate': (poor / total) * 100,
            'score_distribution': distribution,
            'total_analyses': total
        }

    # ========================================
    # 3. ACCURACY METRICS
    # ========================================

    def calculate_accuracy_metrics(self, df: pd.DataFrame) -> Dict:
        """
        Calculate prediction accuracy (exact score, outcome, tip).

        Returns:
            {
                'exact_score_pct': float,
                'outcome_correct_pct': float,
                'tip_accuracy_pct': float
            }
        """
        if df.empty:
            return {
                'exact_score_pct': 0,
                'outcome_correct_pct': 0,
                'tip_accuracy_pct': 0
            }

        # Exact score accuracy
        score_acc = df['score_accuracy'].dropna()
        exact_score_pct = (score_acc.sum() / len(score_acc) * 100) if len(score_acc) > 0 else 0

        # Outcome accuracy (W/D/L)
        outcome_matches = df[df['predicted_outcome'].notna()]
        if len(outcome_matches) > 0:
            correct_outcomes = (outcome_matches['predicted_outcome'] == outcome_matches['actual_outcome']).sum()
            outcome_correct_pct = (correct_outcomes / len(outcome_matches)) * 100
        else:
            outcome_correct_pct = 0

        # Tip accuracy
        tip_acc = df['tip_accuracy'].dropna()
        tip_accuracy_pct = (tip_acc.sum() / len(tip_acc) * 100) if len(tip_acc) > 0 else 0

        return {
            'exact_score_pct': float(exact_score_pct),
            'outcome_correct_pct': float(outcome_correct_pct),
            'tip_accuracy_pct': float(tip_accuracy_pct),
            'total_with_scores': len(score_acc),
            'total_with_outcomes': len(outcome_matches),
            'total_with_tips': len(tip_acc)
        }

    # ========================================
    # 4. ERROR ANALYSIS
    # ========================================

    def get_error_patterns(self, df: pd.DataFrame) -> Dict:
        """
        Identify systematic error patterns and critical flags.

        Returns:
            {
                'top_flags': list[dict],
                'poor_analyses': DataFrame,
                'common_mistakes': dict
            }
        """
        if df.empty or 'critical_flags_list' not in df.columns:
            return {
                'top_flags': [],
                'poor_analyses': pd.DataFrame(),
                'common_mistakes': {}
            }

        # Aggregate all critical flags
        all_flags = []
        for flags in df['critical_flags_list']:
            if isinstance(flags, list):
                all_flags.extend(flags)

        # Count flag frequency
        from collections import Counter
        flag_counts = Counter(all_flags)
        top_flags = [
            {'flag': flag, 'count': count, 'percentage': (count / len(df)) * 100}
            for flag, count in flag_counts.most_common(10)
        ]

        # Get poor analyses (narrative_score < 50)
        poor_analyses = df[df['narrative_score'] < 50].copy()
        poor_analyses = poor_analyses[[
            'fixture_id', 'home_team', 'away_team', 'date',
            'prompt_version', 'narrative_score', 'confidence',
            'predicted_score', 'actual_home', 'actual_away',
            'narrative_feedback'
        ]].sort_values('narrative_score')

        # Common mistake patterns
        common_mistakes = {
            'overconfident_failures': len(df[(df['confidence'] >= 70) & (df['narrative_score'] < 50)]),
            'tactical_misreads': sum(1 for flags in df['critical_flags_list']
                                    if 'tactical_misread' in flags),
            'form_ignored': sum(1 for flags in df['critical_flags_list']
                               if 'form_ignored' in flags),
            'underestimated_factors': sum(1 for flags in df['critical_flags_list']
                                         if 'underestimated_factor' in flags)
        }

        return {
            'top_flags': top_flags,
            'poor_analyses': poor_analyses,
            'common_mistakes': common_mistakes,
            'poor_analyses_count': len(poor_analyses)
        }

    # ========================================
    # 5. PROMPT COMPARISON
    # ========================================

    def compare_prompts(
        self,
        prompt_versions: List[str],
        season: str = "2025-2026"
    ) -> pd.DataFrame:
        """
        Compare multiple prompts side-by-side.

        Args:
            prompt_versions: List of prompt versions to compare
            season: Season to analyze

        Returns:
            DataFrame with comparison metrics
        """
        comparison_data = []

        for prompt in prompt_versions:
            df = self.get_validation_data(season=season, prompt_version=prompt)

            if df.empty:
                comparison_data.append({
                    'prompt_version': prompt,
                    'total_analyses': 0,
                    'avg_narrative_score': 0,
                    'excellent_rate': 0,
                    'good_rate': 0,
                    'exact_score_pct': 0,
                    'outcome_correct_pct': 0,
                    'tip_accuracy_pct': 0,
                    'avg_confidence': 0
                })
                continue

            narrative_metrics = self.calculate_narrative_metrics(df)
            accuracy_metrics = self.calculate_accuracy_metrics(df)

            comparison_data.append({
                'prompt_version': prompt,
                'total_analyses': len(df),
                'avg_narrative_score': narrative_metrics['avg_score'],
                'median_narrative_score': narrative_metrics['median_score'],
                'excellent_rate': narrative_metrics['excellent_rate'],
                'good_rate': narrative_metrics['good_rate'],
                'poor_rate': narrative_metrics['poor_rate'],
                'exact_score_pct': accuracy_metrics['exact_score_pct'],
                'outcome_correct_pct': accuracy_metrics['outcome_correct_pct'],
                'tip_accuracy_pct': accuracy_metrics['tip_accuracy_pct'],
                'avg_confidence': df['confidence'].mean()
            })

        return pd.DataFrame(comparison_data)

    # ========================================
    # 6. BEST/WORST ANALYSES
    # ========================================

    def get_best_worst_analyses(
        self,
        df: pd.DataFrame,
        n: int = 5
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Get top N best and worst analyses by narrative score.

        Returns:
            (best_df, worst_df)
        """
        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        cols = [
            'fixture_id', 'home_team', 'away_team', 'date',
            'prompt_version', 'narrative_score', 'confidence',
            'predicted_score', 'actual_home', 'actual_away',
            'score_accuracy', 'tip_accuracy', 'narrative_feedback'
        ]

        best = df.nlargest(n, 'narrative_score')[cols].copy()
        worst = df.nsmallest(n, 'narrative_score')[cols].copy()

        return best, worst

    # ========================================
    # 7. COMPREHENSIVE VALIDATION REPORT
    # ========================================

    def generate_validation_report(
        self,
        season: str = "2025-2026",
        prompt_version: Optional[str] = None
    ) -> Dict:
        """
        Generate comprehensive validation report.

        Returns:
            Complete validation metrics dict
        """
        df = self.get_validation_data(season=season, prompt_version=prompt_version)

        if df.empty:
            return {
                'error': 'No validation data available',
                'season': season,
                'prompt_version': prompt_version
            }

        narrative_metrics = self.calculate_narrative_metrics(df)
        accuracy_metrics = self.calculate_accuracy_metrics(df)
        error_patterns = self.get_error_patterns(df)
        best, worst = self.get_best_worst_analyses(df, n=5)

        return {
            'season': season,
            'prompt_version': prompt_version or 'All',
            'narrative_quality': narrative_metrics,
            'accuracy': accuracy_metrics,
            'error_patterns': {
                'top_flags': error_patterns['top_flags'],
                'common_mistakes': error_patterns['common_mistakes'],
                'poor_analyses_count': error_patterns['poor_analyses_count']
            },
            'best_analyses': best.to_dict('records') if not best.empty else [],
            'worst_analyses': worst.to_dict('records') if not worst.empty else [],

            # Phase 1 Success Check
            'phase1_success': self._check_phase1_success(narrative_metrics)
        }

    def _check_phase1_success(self, narrative_metrics: Dict) -> Dict:
        """
        Check if Phase 1 goal is achieved:
        80+ Narrative Score in 90% of analyses
        """
        target_score = 80
        target_rate = 90

        # Calculate what % of analyses have score >= 80
        excellent_rate = narrative_metrics.get('excellent_rate', 0)

        achieved = excellent_rate >= target_rate

        return {
            'achieved': achieved,
            'target': f'{target_rate}% of analyses with score >={target_score}',
            'current': f'{excellent_rate:.1f}% of analyses with score >={target_score}',
            'gap': max(0, target_rate - excellent_rate),
            'status': '✅ PASSED' if achieved else '❌ NOT YET'
        }


# ========================================
# STANDALONE FUNCTIONS FOR DASHBOARD USE
# ========================================

def run_validation(season: str = "2025-2026", prompt_version: Optional[str] = None) -> Dict:
    """
    Convenience function to run full validation from dashboard.

    Args:
        season: Season to validate
        prompt_version: Specific prompt or None for all

    Returns:
        Complete validation report dict
    """
    engine = ValidationEngine()
    try:
        report = engine.generate_validation_report(season=season, prompt_version=prompt_version)
        return report
    finally:
        engine.close()


def compare_all_prompts(season: str = "2025-2026") -> pd.DataFrame:
    """
    Compare all available prompts for a season.

    Returns:
        DataFrame with prompt comparison
    """
    engine = ValidationEngine()
    try:
        # Get all available prompts
        conn = get_connection()
        if not conn:
            return pd.DataFrame()

        query = """
            SELECT DISTINCT ar.prompt_version
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE f.season = %s AND f.status = 'FINISHED'
            ORDER BY ar.prompt_version
        """
        df_prompts = pd.read_sql(query, conn, params=(season,))
        conn.close()

        if df_prompts.empty:
            return pd.DataFrame()

        prompts = df_prompts['prompt_version'].tolist()
        return engine.compare_prompts(prompts, season=season)

    finally:
        engine.close()


if __name__ == "__main__":
    # Test validation
    print("🔍 Testing ValidationEngine...")

    engine = ValidationEngine()

    # Test basic validation
    df = engine.get_validation_data(season="2025-2026")
    print(f"\n📊 Found {len(df)} analyses with evaluation data")

    if not df.empty:
        # Test narrative metrics
        narrative = engine.calculate_narrative_metrics(df)
        print(f"\n📖 Narrative Metrics:")
        print(f"   Avg Score: {narrative['avg_score']:.1f}")
        print(f"   Excellent Rate: {narrative['excellent_rate']:.1f}%")

        # Test accuracy
        accuracy = engine.calculate_accuracy_metrics(df)
        print(f"\n🎯 Accuracy Metrics:")
        print(f"   Outcome Correct: {accuracy['outcome_correct_pct']:.1f}%")

        # Generate full report
        report = engine.generate_validation_report(season="2025-2026")
        print(f"\n{report['phase1_success']['status']}")
        print(f"   {report['phase1_success']['current']}")

    engine.close()
    print("\n✅ Validation test complete!")
