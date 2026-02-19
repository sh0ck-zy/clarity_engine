"""
Regression Alert System - Phase 1 (P1-012)

Monitors validation metrics and alerts when quality drops.
Prevents shipping regressions to production.

Usage:
    from src.analysis.regression_alerts import RegressionMonitor, check_for_regressions

    monitor = RegressionMonitor()
    alerts = monitor.check_current_state()
"""

import pandas as pd
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import json

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection


# ============================================================
# ALERT TYPES
# ============================================================

@dataclass
class RegressionAlert:
    """A detected regression alert."""
    alert_id: str
    alert_type: str  # "narrative_quality", "outcome_accuracy", "coverage", "error_spike"
    severity: str  # "critical", "warning", "info"
    metric_name: str
    current_value: float
    threshold_value: float
    baseline_value: Optional[float]
    delta: float  # Current - Baseline (negative = regression)
    description: str
    affected_prompt: Optional[str]
    affected_round: Optional[int]
    detected_at: datetime = field(default_factory=datetime.utcnow)
    is_acknowledged: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AlertThresholds:
    """Configurable alert thresholds."""
    # Narrative Quality
    narrative_score_min: float = 60.0  # Minimum acceptable avg score
    narrative_score_drop: float = 10.0  # Alert if drops by this much
    excellent_rate_min: float = 50.0  # Minimum % of 80+ scores

    # Outcome Accuracy
    outcome_accuracy_min: float = 35.0  # Minimum W/D/L accuracy
    outcome_accuracy_drop: float = 15.0  # Alert if drops by this much

    # Coverage
    coverage_score_min: float = 70.0  # Minimum data coverage
    coverage_drop: float = 10.0  # Alert if coverage drops

    # Error Patterns
    critical_flag_spike: int = 5  # Alert if a flag appears this many times
    poor_analysis_max: int = 3  # Max poor analyses per round before alert


# ============================================================
# REGRESSION MONITOR
# ============================================================

class RegressionMonitor:
    """
    Monitors quality metrics and generates alerts on regressions.
    """

    def __init__(self, thresholds: Optional[AlertThresholds] = None):
        self.conn = get_connection()
        self.thresholds = thresholds or AlertThresholds()
        self.alerts: List[RegressionAlert] = []
        self._alert_counter = 0

    def close(self):
        if self.conn:
            self.conn.close()

    def _next_alert_id(self) -> str:
        self._alert_counter += 1
        return f"ALERT-{datetime.now().strftime('%Y%m%d')}-{self._alert_counter:04d}"

    # ============================================================
    # CHECK FUNCTIONS
    # ============================================================

    def check_current_state(
        self,
        season: str = "2025-2026",
        prompt_version: Optional[str] = None
    ) -> List[RegressionAlert]:
        """
        Check current state for regressions.

        Returns list of alerts (empty = all good).
        """
        self.alerts = []

        if not self.conn:
            return [RegressionAlert(
                alert_id=self._next_alert_id(),
                alert_type="system",
                severity="critical",
                metric_name="database_connection",
                current_value=0,
                threshold_value=1,
                baseline_value=None,
                delta=-1,
                description="Database connection failed",
                affected_prompt=None,
                affected_round=None
            )]

        # Check narrative quality
        self._check_narrative_quality(season, prompt_version)

        # Check outcome accuracy
        self._check_outcome_accuracy(season, prompt_version)

        # Check error patterns
        self._check_error_patterns(season, prompt_version)

        # Check round-over-round changes
        self._check_round_regression(season, prompt_version)

        return self.alerts

    def _check_narrative_quality(self, season: str, prompt_version: Optional[str]):
        """Check narrative quality metrics."""

        sql = """
            SELECT
                AVG(ae.narrative_score) as avg_score,
                COUNT(*) as total,
                SUM(CASE WHEN ae.narrative_score >= 80 THEN 1 ELSE 0 END) as excellent
            FROM analysis_evaluations ae
            JOIN analysis_reports ar ON ae.report_id = ar.id
            JOIN fixtures f ON ae.fixture_id = f.id
            WHERE f.season = %s AND f.status = 'FINISHED'
        """
        params = [season]
        if prompt_version:
            sql += " AND ar.prompt_version = %s"
            params.append(prompt_version)

        df = pd.read_sql(sql, self.conn, params=tuple(params))

        if df.empty or df.iloc[0]['total'] == 0:
            return

        row = df.iloc[0]
        avg_score = float(row['avg_score']) if pd.notna(row['avg_score']) else 0
        total = int(row['total'])
        excellent = int(row['excellent'])
        excellent_rate = (excellent / total * 100) if total > 0 else 0

        # Check average score
        if avg_score < self.thresholds.narrative_score_min:
            self.alerts.append(RegressionAlert(
                alert_id=self._next_alert_id(),
                alert_type="narrative_quality",
                severity="critical",
                metric_name="avg_narrative_score",
                current_value=avg_score,
                threshold_value=self.thresholds.narrative_score_min,
                baseline_value=None,
                delta=avg_score - self.thresholds.narrative_score_min,
                description=f"Average narrative score ({avg_score:.1f}) below threshold ({self.thresholds.narrative_score_min})",
                affected_prompt=prompt_version,
                affected_round=None
            ))

        # Check excellent rate
        if excellent_rate < self.thresholds.excellent_rate_min:
            self.alerts.append(RegressionAlert(
                alert_id=self._next_alert_id(),
                alert_type="narrative_quality",
                severity="warning",
                metric_name="excellent_rate",
                current_value=excellent_rate,
                threshold_value=self.thresholds.excellent_rate_min,
                baseline_value=None,
                delta=excellent_rate - self.thresholds.excellent_rate_min,
                description=f"Excellent rate ({excellent_rate:.1f}%) below threshold ({self.thresholds.excellent_rate_min}%)",
                affected_prompt=prompt_version,
                affected_round=None
            ))

    def _check_outcome_accuracy(self, season: str, prompt_version: Optional[str]):
        """Check outcome prediction accuracy."""

        sql = """
            SELECT
                ar.predicted_score,
                f.home_score,
                f.away_score
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE f.season = %s AND f.status = 'FINISHED'
              AND ar.predicted_score IS NOT NULL
        """
        params = [season]
        if prompt_version:
            sql += " AND ar.prompt_version = %s"
            params.append(prompt_version)

        df = pd.read_sql(sql, self.conn, params=tuple(params))

        if df.empty:
            return

        correct = 0
        total = 0

        for _, row in df.iterrows():
            pred_score = str(row['predicted_score'])
            try:
                parts = pred_score.split('-')
                if len(parts) == 2:
                    pred_home = int(parts[0].strip())
                    pred_away = int(parts[1].strip())
                    actual_home = int(row['home_score'])
                    actual_away = int(row['away_score'])

                    # Compare outcomes
                    pred_outcome = 'W' if pred_home > pred_away else ('L' if pred_home < pred_away else 'D')
                    actual_outcome = 'W' if actual_home > actual_away else ('L' if actual_home < actual_away else 'D')

                    if pred_outcome == actual_outcome:
                        correct += 1
                    total += 1
            except:
                continue

        if total == 0:
            return

        accuracy = correct / total * 100

        if accuracy < self.thresholds.outcome_accuracy_min:
            self.alerts.append(RegressionAlert(
                alert_id=self._next_alert_id(),
                alert_type="outcome_accuracy",
                severity="warning",
                metric_name="outcome_correct_pct",
                current_value=accuracy,
                threshold_value=self.thresholds.outcome_accuracy_min,
                baseline_value=None,
                delta=accuracy - self.thresholds.outcome_accuracy_min,
                description=f"Outcome accuracy ({accuracy:.1f}%) below threshold ({self.thresholds.outcome_accuracy_min}%)",
                affected_prompt=prompt_version,
                affected_round=None
            ))

    def _check_error_patterns(self, season: str, prompt_version: Optional[str]):
        """Check for spikes in critical error flags."""

        sql = """
            SELECT
                ae.narrative_critical_flags
            FROM analysis_evaluations ae
            JOIN analysis_reports ar ON ae.report_id = ar.id
            JOIN fixtures f ON ae.fixture_id = f.id
            WHERE f.season = %s AND f.status = 'FINISHED'
        """
        params = [season]
        if prompt_version:
            sql += " AND ar.prompt_version = %s"
            params.append(prompt_version)

        df = pd.read_sql(sql, self.conn, params=tuple(params))

        if df.empty:
            return

        # Count flags
        flag_counts = {}
        for _, row in df.iterrows():
            flags = row['narrative_critical_flags']
            if isinstance(flags, str):
                try:
                    flags = json.loads(flags)
                except:
                    flags = []
            elif not isinstance(flags, list):
                flags = []

            for flag in flags:
                flag_counts[flag] = flag_counts.get(flag, 0) + 1

        # Check for spikes
        for flag, count in flag_counts.items():
            if count >= self.thresholds.critical_flag_spike:
                self.alerts.append(RegressionAlert(
                    alert_id=self._next_alert_id(),
                    alert_type="error_spike",
                    severity="warning",
                    metric_name=f"flag_{flag}",
                    current_value=count,
                    threshold_value=self.thresholds.critical_flag_spike,
                    baseline_value=None,
                    delta=count - self.thresholds.critical_flag_spike,
                    description=f"Critical flag '{flag}' appears {count} times (threshold: {self.thresholds.critical_flag_spike})",
                    affected_prompt=prompt_version,
                    affected_round=None
                ))

    def _check_round_regression(self, season: str, prompt_version: Optional[str]):
        """Check for quality drops between recent rounds."""

        sql = """
            SELECT
                f.round,
                AVG(ae.narrative_score) as avg_score,
                COUNT(*) as total
            FROM analysis_evaluations ae
            JOIN analysis_reports ar ON ae.report_id = ar.id
            JOIN fixtures f ON ae.fixture_id = f.id
            WHERE f.season = %s AND f.status = 'FINISHED' AND f.round IS NOT NULL
        """
        params = [season]
        if prompt_version:
            sql += " AND ar.prompt_version = %s"
            params.append(prompt_version)

        sql += " GROUP BY f.round ORDER BY f.round DESC LIMIT 5"

        df = pd.read_sql(sql, self.conn, params=tuple(params))

        if len(df) < 2:
            return

        # Compare latest round to previous
        latest = df.iloc[0]
        previous = df.iloc[1]

        latest_score = float(latest['avg_score']) if pd.notna(latest['avg_score']) else 0
        previous_score = float(previous['avg_score']) if pd.notna(previous['avg_score']) else 0

        drop = previous_score - latest_score

        if drop >= self.thresholds.narrative_score_drop:
            self.alerts.append(RegressionAlert(
                alert_id=self._next_alert_id(),
                alert_type="round_regression",
                severity="critical",
                metric_name="round_score_change",
                current_value=latest_score,
                threshold_value=previous_score - self.thresholds.narrative_score_drop,
                baseline_value=previous_score,
                delta=-drop,
                description=f"Round {int(latest['round'])} score ({latest_score:.1f}) dropped {drop:.1f} points from Round {int(previous['round'])} ({previous_score:.1f})",
                affected_prompt=prompt_version,
                affected_round=int(latest['round'])
            ))

    # ============================================================
    # COMPARISON FUNCTIONS
    # ============================================================

    def compare_prompts(self, season: str = "2025-2026") -> List[RegressionAlert]:
        """
        Compare prompt versions and alert on significant differences.
        """
        sql = """
            SELECT DISTINCT ar.prompt_version
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            WHERE f.season = %s
        """
        df_prompts = pd.read_sql(sql, self.conn, params=(season,))

        if len(df_prompts) < 2:
            return []

        alerts = []
        prompts = df_prompts['prompt_version'].tolist()

        # Get metrics per prompt
        prompt_metrics = {}
        for prompt in prompts:
            sql = """
                SELECT AVG(ae.narrative_score) as avg_score
                FROM analysis_evaluations ae
                JOIN analysis_reports ar ON ae.report_id = ar.id
                JOIN fixtures f ON ae.fixture_id = f.id
                WHERE f.season = %s AND ar.prompt_version = %s
            """
            df = pd.read_sql(sql, self.conn, params=(season, prompt))
            if not df.empty and pd.notna(df.iloc[0]['avg_score']):
                prompt_metrics[prompt] = float(df.iloc[0]['avg_score'])

        # Find significant differences
        if len(prompt_metrics) >= 2:
            best_prompt = max(prompt_metrics, key=prompt_metrics.get)
            best_score = prompt_metrics[best_prompt]

            for prompt, score in prompt_metrics.items():
                if prompt != best_prompt:
                    gap = best_score - score
                    if gap >= 10:  # Significant gap
                        alerts.append(RegressionAlert(
                            alert_id=self._next_alert_id(),
                            alert_type="prompt_comparison",
                            severity="info",
                            metric_name="prompt_gap",
                            current_value=score,
                            threshold_value=best_score,
                            baseline_value=best_score,
                            delta=-gap,
                            description=f"Prompt '{prompt}' ({score:.1f}) is {gap:.1f} points behind '{best_prompt}' ({best_score:.1f})",
                            affected_prompt=prompt,
                            affected_round=None
                        ))

        return alerts

    # ============================================================
    # REPORTING
    # ============================================================

    def generate_report(
        self,
        alerts: List[RegressionAlert],
        include_acknowledged: bool = False
    ) -> str:
        """Generate human-readable alert report."""

        if not include_acknowledged:
            alerts = [a for a in alerts if not a.is_acknowledged]

        if not alerts:
            return "✅ No regression alerts detected."

        critical = [a for a in alerts if a.severity == "critical"]
        warnings = [a for a in alerts if a.severity == "warning"]
        info = [a for a in alerts if a.severity == "info"]

        lines = [
            "=" * 60,
            "REGRESSION ALERT REPORT",
            "=" * 60,
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Alerts: {len(alerts)}",
            f"  🔴 Critical: {len(critical)}",
            f"  🟡 Warning: {len(warnings)}",
            f"  🔵 Info: {len(info)}",
            ""
        ]

        if critical:
            lines.extend([
                "🔴 CRITICAL ALERTS",
                "-" * 40
            ])
            for alert in critical:
                lines.extend([
                    f"[{alert.alert_id}] {alert.alert_type}",
                    f"   {alert.description}",
                    f"   Metric: {alert.metric_name}",
                    f"   Current: {alert.current_value:.2f} | Threshold: {alert.threshold_value:.2f}",
                    ""
                ])

        if warnings:
            lines.extend([
                "🟡 WARNINGS",
                "-" * 40
            ])
            for alert in warnings:
                lines.extend([
                    f"[{alert.alert_id}] {alert.alert_type}",
                    f"   {alert.description}",
                    ""
                ])

        if info:
            lines.extend([
                "🔵 INFO",
                "-" * 40
            ])
            for alert in info:
                lines.extend([
                    f"[{alert.alert_id}] {alert.description}",
                    ""
                ])

        return "\n".join(lines)


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def check_for_regressions(
    season: str = "2025-2026",
    prompt_version: Optional[str] = None
) -> tuple[bool, List[RegressionAlert]]:
    """
    Quick check for regressions.

    Returns:
        (has_critical_alerts, list_of_alerts)
    """
    monitor = RegressionMonitor()
    try:
        alerts = monitor.check_current_state(season=season, prompt_version=prompt_version)
        has_critical = any(a.severity == "critical" for a in alerts)
        return has_critical, alerts
    finally:
        monitor.close()


def get_alert_summary(season: str = "2025-2026") -> str:
    """Get formatted alert summary."""
    monitor = RegressionMonitor()
    try:
        alerts = monitor.check_current_state(season=season)
        return monitor.generate_report(alerts)
    finally:
        monitor.close()


if __name__ == "__main__":
    print("Testing Regression Alert System...")

    monitor = RegressionMonitor()

    # Check current state
    alerts = monitor.check_current_state(season="2025-2026")

    print(f"\n📊 Found {len(alerts)} alerts")

    # Generate report
    report = monitor.generate_report(alerts)
    print("\n" + report)

    # Check prompt comparison
    print("\n🔍 Checking prompt comparison...")
    prompt_alerts = monitor.compare_prompts(season="2025-2026")
    if prompt_alerts:
        for alert in prompt_alerts:
            print(f"   [{alert.severity}] {alert.description}")

    monitor.close()
    print("\n✅ Regression alert test complete!")
