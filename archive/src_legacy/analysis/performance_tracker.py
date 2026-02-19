"""
Performance Tracker - Dashboard v4

Tracks and compares prompt performance over time.

Usage:
    from src.analysis.performance_tracker import PerformanceTracker

    tracker = PerformanceTracker()
    leaderboard = tracker.get_prompt_leaderboard()
    by_round = tracker.get_accuracy_by_round("v3")
"""

import sys
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection


@dataclass
class PromptStats:
    """Statistics for a single prompt version."""
    prompt_version: str
    total_predictions: int
    correct_predictions: int
    accuracy: float  # 0-100
    avg_confidence: Optional[float]
    total_pnl: Optional[float]
    trend: str  # "up", "down", "stable"
    trend_delta: float  # Change in accuracy from previous period


@dataclass
class RoundAccuracy:
    """Accuracy for a specific round."""
    round_number: int
    total_matches: int
    correct_predictions: int
    accuracy: float  # 0-100
    matches: List[Dict]  # Details of each match


@dataclass
class BiggestError:
    """A significant prediction error."""
    fixture_id: str
    home_team: str
    away_team: str
    match_date: Optional[date]
    round_number: Optional[int]
    predicted_score: str
    actual_score: str
    confidence: int
    prompt_version: str
    error_magnitude: float  # How wrong we were


class PerformanceTracker:
    """
    Tracks prompt performance over time.
    """

    def __init__(self):
        self.conn = get_connection()

    def close(self):
        if self.conn:
            self.conn.close()

    def get_prompt_leaderboard(self, season: str = "2025-2026") -> List[PromptStats]:
        """
        Get leaderboard of prompt versions by accuracy.

        Args:
            season: Season to filter by

        Returns:
            List of PromptStats sorted by accuracy
        """
        if not self.conn:
            return []

        cur = self.conn.cursor()

        # Get all predictions with results
        cur.execute("""
            SELECT
                ar.prompt_version,
                ar.predicted_score,
                f.home_score,
                f.away_score,
                ar.confidence,
                ar.pnl,
                ar.is_correct
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE f.season = %s
            AND f.home_score IS NOT NULL
            AND ar.predicted_score IS NOT NULL
        """, (season,))

        # Calculate stats per prompt
        prompt_data: Dict[str, dict] = {}

        for row in cur.fetchall():
            prompt = row[0]
            predicted = row[1]
            actual_home = row[2]
            actual_away = row[3]
            confidence = row[4]
            pnl = row[5]
            is_correct_db = row[6]

            if prompt not in prompt_data:
                prompt_data[prompt] = {
                    "total": 0,
                    "correct": 0,
                    "confidences": [],
                    "pnl": 0.0
                }

            prompt_data[prompt]["total"] += 1
            if confidence:
                prompt_data[prompt]["confidences"].append(confidence)
            if pnl:
                prompt_data[prompt]["pnl"] += float(pnl)

            # Determine if prediction was correct
            if is_correct_db is not None:
                if is_correct_db:
                    prompt_data[prompt]["correct"] += 1
            else:
                # Calculate from predicted_score
                is_correct = self._check_prediction_correct(predicted, actual_home, actual_away)
                if is_correct:
                    prompt_data[prompt]["correct"] += 1

        # Build stats list
        stats = []
        for prompt_version, data in prompt_data.items():
            total = data["total"]
            correct = data["correct"]
            avg_conf = sum(data["confidences"]) / len(data["confidences"]) if data["confidences"] else None
            total_pnl = data["pnl"] if data["pnl"] else None

            accuracy = (correct / total * 100) if total > 0 else 0

            # Calculate trend (compare last 10 vs previous 10)
            trend, trend_delta = self._calculate_trend(prompt_version, season)

            stats.append(PromptStats(
                prompt_version=prompt_version,
                total_predictions=total,
                correct_predictions=correct,
                accuracy=accuracy,
                avg_confidence=avg_conf,
                total_pnl=total_pnl,
                trend=trend,
                trend_delta=trend_delta
            ))

        # Sort by accuracy descending
        stats.sort(key=lambda x: x.accuracy, reverse=True)
        return stats

    def _check_prediction_correct(self, predicted: str, actual_home: int, actual_away: int) -> bool:
        """Check if prediction outcome matches actual result."""
        if not predicted or actual_home is None or actual_away is None:
            return False

        try:
            # Parse predicted score (format: "2-1")
            parts = predicted.split("-")
            if len(parts) != 2:
                return False
            pred_home = int(parts[0].strip())
            pred_away = int(parts[1].strip())

            # Compare outcomes (home win, draw, away win)
            pred_outcome = "home" if pred_home > pred_away else ("away" if pred_away > pred_home else "draw")
            actual_outcome = "home" if actual_home > actual_away else ("away" if actual_away > actual_home else "draw")

            return pred_outcome == actual_outcome
        except (ValueError, IndexError):
            return False

    def _calculate_trend(self, prompt_version: str, season: str) -> tuple[str, float]:
        """Calculate accuracy trend for a prompt."""
        if not self.conn:
            return "stable", 0.0

        cur = self.conn.cursor()

        # Get recent predictions ordered by date with actual results
        cur.execute("""
            SELECT ar.predicted_score, f.home_score, f.away_score, ar.is_correct, f.date
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE ar.prompt_version = %s
            AND f.season = %s
            AND f.home_score IS NOT NULL
            AND ar.predicted_score IS NOT NULL
            ORDER BY f.date DESC
        """, (prompt_version, season))

        results = cur.fetchall()

        if len(results) < 10:
            return "stable", 0.0

        # Calculate correctness for each result
        def is_correct(row):
            if row[3] is not None:  # is_correct from DB
                return row[3]
            return self._check_prediction_correct(row[0], row[1], row[2])

        # Recent 10
        recent = results[:10]
        recent_correct = sum(1 for r in recent if is_correct(r))
        recent_accuracy = recent_correct / 10 * 100

        # Previous 10
        if len(results) >= 20:
            previous = results[10:20]
            prev_correct = sum(1 for r in previous if is_correct(r))
            prev_accuracy = prev_correct / 10 * 100
        else:
            prev_accuracy = recent_accuracy

        delta = recent_accuracy - prev_accuracy

        if delta > 5:
            trend = "up"
        elif delta < -5:
            trend = "down"
        else:
            trend = "stable"

        return trend, delta

    def get_accuracy_by_round(
        self,
        prompt_version: str = None,
        season: str = "2025-2026",
        limit: int = 10
    ) -> List[RoundAccuracy]:
        """
        Get accuracy breakdown by round.

        Args:
            prompt_version: Filter by prompt (None = all prompts combined)
            season: Season to filter by
            limit: Number of recent rounds to return

        Returns:
            List of RoundAccuracy for recent rounds
        """
        if not self.conn:
            return []

        cur = self.conn.cursor()

        # Get fixtures with predictions and results
        if prompt_version:
            cur.execute("""
                SELECT
                    f.round,
                    f.id,
                    f.home_team,
                    f.away_team,
                    ar.predicted_score,
                    f.home_score,
                    f.away_score,
                    ar.is_correct
                FROM fixtures f
                LEFT JOIN analysis_reports ar ON f.id = ar.fixture_id
                    AND ar.prompt_version = %s
                WHERE f.season = %s
                AND f.round IS NOT NULL
                AND f.home_score IS NOT NULL
                ORDER BY f.round DESC, f.home_team
            """, (prompt_version, season))
        else:
            # Get first prediction per fixture
            cur.execute("""
                SELECT
                    f.round,
                    f.id,
                    f.home_team,
                    f.away_team,
                    ar.predicted_score,
                    f.home_score,
                    f.away_score,
                    ar.is_correct
                FROM fixtures f
                LEFT JOIN LATERAL (
                    SELECT predicted_score, is_correct
                    FROM analysis_reports
                    WHERE fixture_id = f.id
                    LIMIT 1
                ) ar ON true
                WHERE f.season = %s
                AND f.round IS NOT NULL
                AND f.home_score IS NOT NULL
                ORDER BY f.round DESC, f.home_team
            """, (season,))

        # Group by round
        round_data: Dict[int, dict] = {}

        for row in cur.fetchall():
            round_num = row[0]
            fixture_id = row[1]
            home_team = row[2]
            away_team = row[3]
            predicted = row[4]
            actual_home = row[5]
            actual_away = row[6]
            is_correct_db = row[7]

            if round_num not in round_data:
                round_data[round_num] = {
                    "total": 0,
                    "correct": 0,
                    "matches": []
                }

            round_data[round_num]["total"] += 1

            # Calculate correctness
            if predicted:
                if is_correct_db is not None:
                    is_correct = is_correct_db
                else:
                    is_correct = self._check_prediction_correct(predicted, actual_home, actual_away)

                if is_correct:
                    round_data[round_num]["correct"] += 1
            else:
                is_correct = None

            round_data[round_num]["matches"].append({
                "fixture_id": fixture_id,
                "home_team": home_team,
                "away_team": away_team,
                "predicted": predicted,
                "actual": f"{actual_home}-{actual_away}",
                "is_correct": is_correct
            })

        # Build results
        results = []
        for round_num in sorted(round_data.keys(), reverse=True)[:limit]:
            data = round_data[round_num]
            total = data["total"]
            correct = data["correct"]
            accuracy = (correct / total * 100) if total > 0 else 0

            results.append(RoundAccuracy(
                round_number=round_num,
                total_matches=total,
                correct_predictions=correct,
                accuracy=accuracy,
                matches=data["matches"]
            ))

        return results

    def get_biggest_errors(
        self,
        season: str = "2025-2026",
        limit: int = 10,
        min_confidence: int = 60
    ) -> List[BiggestError]:
        """
        Get the biggest prediction errors.

        Args:
            season: Season to filter by
            limit: Number of errors to return
            min_confidence: Minimum confidence to consider (high confidence errors are worse)

        Returns:
            List of BiggestError sorted by error magnitude
        """
        if not self.conn:
            return []

        cur = self.conn.cursor()

        # Get all predictions with results - filter errors in Python
        cur.execute("""
            SELECT
                ar.fixture_id,
                f.home_team,
                f.away_team,
                f.date,
                f.round,
                ar.predicted_score,
                f.home_score,
                f.away_score,
                ar.confidence,
                ar.prompt_version,
                ar.is_correct
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE f.season = %s
            AND f.home_score IS NOT NULL
            AND ar.predicted_score IS NOT NULL
            AND ar.confidence >= %s
            ORDER BY ar.confidence DESC
        """, (season, min_confidence))

        errors = []
        for row in cur.fetchall():
            fixture_id = row[0]
            home_team = row[1]
            away_team = row[2]
            match_date = row[3]
            round_num = row[4]
            predicted = row[5]
            actual_home = row[6]
            actual_away = row[7]
            confidence = row[8]
            prompt = row[9]
            is_correct_db = row[10]

            # Check if this was an error
            if is_correct_db is not None:
                is_correct = is_correct_db
            else:
                is_correct = self._check_prediction_correct(predicted, actual_home, actual_away)

            # Skip correct predictions
            if is_correct:
                continue

            actual = f"{actual_home}-{actual_away}"

            # Calculate error magnitude based on confidence and how wrong we were
            error_magnitude = self._calculate_error_magnitude(
                predicted, actual_home, actual_away, confidence
            )

            errors.append(BiggestError(
                fixture_id=fixture_id,
                home_team=home_team,
                away_team=away_team,
                match_date=match_date,
                round_number=round_num,
                predicted_score=predicted,
                actual_score=actual,
                confidence=confidence,
                prompt_version=prompt,
                error_magnitude=error_magnitude
            ))

        # Sort by error magnitude and limit
        errors.sort(key=lambda e: e.error_magnitude, reverse=True)
        return errors[:limit]

    def _calculate_error_magnitude(
        self,
        predicted: str,
        actual_home: int,
        actual_away: int,
        confidence: int
    ) -> float:
        """
        Calculate how bad an error was.

        Factors:
        - Confidence (higher = worse error)
        - Predicted wrong outcome (home/draw/away)
        - Score difference
        """
        if not predicted or actual_home is None or actual_away is None:
            return 0.0

        # Parse predicted score
        try:
            parts = predicted.replace("-", " ").split()
            pred_home = int(parts[0])
            pred_away = int(parts[-1])
        except (ValueError, IndexError):
            return confidence  # Just use confidence if can't parse

        # Determine outcomes
        pred_outcome = "home" if pred_home > pred_away else ("away" if pred_away > pred_home else "draw")
        actual_outcome = "home" if actual_home > actual_away else ("away" if actual_away > actual_home else "draw")

        # Base error from confidence
        error = confidence

        # Bonus for wrong outcome direction
        if pred_outcome != actual_outcome:
            error += 20

        # Bonus for score difference
        score_diff = abs((actual_home - actual_away) - (pred_home - pred_away))
        error += score_diff * 5

        return error

    def get_overall_stats(self, season: str = "2025-2026") -> Dict[str, Any]:
        """
        Get overall performance statistics.

        Args:
            season: Season to filter by

        Returns:
            Dict with overall stats
        """
        if not self.conn:
            return {}

        cur = self.conn.cursor()

        # Get all predictions with results
        cur.execute("""
            SELECT
                ar.predicted_score,
                f.home_score,
                f.away_score,
                ar.confidence,
                ar.pnl,
                ar.is_correct
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE f.season = %s
            AND f.home_score IS NOT NULL
            AND ar.predicted_score IS NOT NULL
        """, (season,))

        total = 0
        correct = 0
        confidences = []
        total_pnl = 0.0

        for row in cur.fetchall():
            predicted = row[0]
            actual_home = row[1]
            actual_away = row[2]
            confidence = row[3]
            pnl = row[4]
            is_correct_db = row[5]

            total += 1
            if confidence:
                confidences.append(confidence)
            if pnl:
                total_pnl += float(pnl)

            if is_correct_db is not None:
                if is_correct_db:
                    correct += 1
            else:
                if self._check_prediction_correct(predicted, actual_home, actual_away):
                    correct += 1

        accuracy = (correct / total * 100) if total > 0 else 0
        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        # Unique fixtures analyzed
        cur.execute("""
            SELECT COUNT(DISTINCT fixture_id)
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE f.season = %s
        """, (season,))
        unique_fixtures = cur.fetchone()[0] or 0

        # Rounds covered
        cur.execute("""
            SELECT MIN(f.round), MAX(f.round)
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE f.season = %s AND f.round IS NOT NULL
        """, (season,))
        round_row = cur.fetchone()
        min_round = round_row[0] if round_row else None
        max_round = round_row[1] if round_row else None

        return {
            "total_predictions": total,
            "correct_predictions": correct,
            "overall_accuracy": accuracy,
            "avg_confidence": avg_confidence,
            "total_pnl": total_pnl if total_pnl else None,
            "unique_fixtures": unique_fixtures,
            "rounds_covered": f"{min_round}-{max_round}" if min_round and max_round else None,
            "prompt_count": len(self.get_prompt_leaderboard(season))
        }


if __name__ == "__main__":
    tracker = PerformanceTracker()

    print("=" * 60)
    print("PERFORMANCE TRACKER TEST")
    print("=" * 60)

    # Overall stats
    overall = tracker.get_overall_stats()
    print(f"\nOverall Stats:")
    print(f"  Total predictions: {overall['total_predictions']}")
    print(f"  Correct: {overall['correct_predictions']}")
    print(f"  Accuracy: {overall['overall_accuracy']:.1f}%")
    print(f"  Unique fixtures: {overall['unique_fixtures']}")
    print(f"  Rounds: {overall['rounds_covered']}")

    # Leaderboard
    print("\n" + "=" * 60)
    print("PROMPT LEADERBOARD")
    print("=" * 60)
    leaderboard = tracker.get_prompt_leaderboard()
    for i, p in enumerate(leaderboard):
        trend_icon = {"up": "↑", "down": "↓", "stable": "→"}.get(p.trend, "?")
        crown = " 🏆" if i == 0 else ""
        print(f"  {p.prompt_version}{crown}: {p.accuracy:.1f}% ({p.correct_predictions}/{p.total_predictions}) {trend_icon} {p.trend_delta:+.1f}%")

    # Accuracy by round
    print("\n" + "=" * 60)
    print("ACCURACY BY ROUND")
    print("=" * 60)
    by_round = tracker.get_accuracy_by_round(limit=5)
    for r in by_round:
        bar_len = int(r.accuracy / 10)
        bar = "█" * bar_len + "░" * (10 - bar_len)
        print(f"  R{r.round_number}: {bar} {r.correct_predictions}/{r.total_matches} ({r.accuracy:.0f}%)")

    # Biggest errors
    print("\n" + "=" * 60)
    print("BIGGEST ERRORS")
    print("=" * 60)
    errors = tracker.get_biggest_errors(limit=5)
    for e in errors:
        print(f"  • {e.home_team} {e.actual_score} (pred: {e.predicted_score}, conf: {e.confidence}%)")

    tracker.close()
