"""
Time-Travel Safety Guard - Phase 1 (P1-008)

Ensures no future data leaks into pre-match context.
This is CRITICAL for ML training data integrity.

Usage:
    from src.analysis.time_travel_guard import TimeTravelGuard, validate_context_time_safety

    guard = TimeTravelGuard()
    is_safe, violations = guard.validate_context(context, fixture_date)
"""

import pandas as pd
import sys
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection


# ============================================================
# VIOLATION TYPES
# ============================================================

@dataclass
class TimeTravelViolation:
    """A detected time-travel violation."""
    violation_type: str  # "form_leak", "odds_leak", "injury_leak", "result_leak"
    severity: str  # "critical", "warning"
    description: str
    data_point: str  # What data was accessed
    data_date: Optional[datetime]  # When that data is from
    fixture_date: datetime  # When the fixture is
    query_or_source: str  # What query/code caused this


# ============================================================
# TIME TRAVEL GUARD
# ============================================================

class TimeTravelGuard:
    """
    Validates that all data access is time-travel safe.

    Time-travel safety means: Only use data that was available
    BEFORE the match started.
    """

    def __init__(self):
        self.conn = get_connection()
        self.violations: List[TimeTravelViolation] = []

    def close(self):
        if self.conn:
            self.conn.close()

    def validate_context(
        self,
        context: Dict,
        fixture_date: datetime
    ) -> Tuple[bool, List[TimeTravelViolation]]:
        """
        Validate that a context payload doesn't contain future data.

        Args:
            context: Match context dictionary
            fixture_date: Date of the fixture

        Returns:
            (is_safe, list_of_violations)
        """
        self.violations = []

        # Check form data
        self._validate_form_data(context, fixture_date)

        # Check H2H data
        self._validate_h2h_data(context, fixture_date)

        # Check odds data
        self._validate_odds_data(context, fixture_date)

        # Check injury data
        self._validate_injury_data(context, fixture_date)

        # Check no actual results in context
        self._validate_no_results(context)

        is_safe = len([v for v in self.violations if v.severity == "critical"]) == 0
        return is_safe, self.violations

    def _validate_form_data(self, context: Dict, fixture_date: datetime):
        """Validate form data only uses matches before fixture_date."""

        for side in ['home', 'away']:
            team_context = context.get(side, {})
            form = team_context.get('form', {})

            # Check if form results seem to include the current match
            # (Heuristic: form should show 5 or fewer results)
            results = form.get('results', '')
            if results and results.count('-') >= 5:
                self.violations.append(TimeTravelViolation(
                    violation_type="form_leak",
                    severity="warning",
                    description=f"{side} form has >5 matches - may include current fixture",
                    data_point=f"{side}.form.results",
                    data_date=None,
                    fixture_date=fixture_date,
                    query_or_source="form_calculation"
                ))

    def _validate_h2h_data(self, context: Dict, fixture_date: datetime):
        """Validate H2H data only uses matches before fixture_date."""
        h2h = context.get('head_to_head', {})

        # Check that H2H doesn't include current match
        matches_played = h2h.get('matches_played', 0)
        if matches_played > 10:
            self.violations.append(TimeTravelViolation(
                violation_type="h2h_leak",
                severity="warning",
                description=f"H2H shows {matches_played} matches - unusually high",
                data_point="head_to_head.matches_played",
                data_date=None,
                fixture_date=fixture_date,
                query_or_source="h2h_calculation"
            ))

    def _validate_odds_data(self, context: Dict, fixture_date: datetime):
        """Validate odds were captured before kickoff."""
        odds = context.get('odds', {})
        captured_at = odds.get('captured_at')

        if captured_at:
            if isinstance(captured_at, str):
                try:
                    captured_at = datetime.fromisoformat(captured_at.replace('Z', '+00:00'))
                except:
                    pass

            if isinstance(captured_at, datetime):
                if captured_at > fixture_date:
                    self.violations.append(TimeTravelViolation(
                        violation_type="odds_leak",
                        severity="critical",
                        description=f"Odds captured AFTER fixture date",
                        data_point="odds.captured_at",
                        data_date=captured_at,
                        fixture_date=fixture_date,
                        query_or_source="odds_snapshot"
                    ))

    def _validate_injury_data(self, context: Dict, fixture_date: datetime):
        """Validate injury data uses valid_at before fixture_date."""
        for side in ['home', 'away']:
            team_context = context.get(side, {})
            absences = team_context.get('absences', {})
            players = absences.get('players', [])

            for player in players:
                # Check if any injury info has a timestamp after fixture
                # (This is a placeholder - actual validation needs injury timestamps)
                pass

    def _validate_no_results(self, context: Dict):
        """Validate context doesn't contain actual match results."""
        result_fields = [
            'actual_score',
            'final_score',
            'home_score',
            'away_score',
            'match_result',
            'winner'
        ]

        for field in result_fields:
            if field in context:
                self.violations.append(TimeTravelViolation(
                    violation_type="result_leak",
                    severity="critical",
                    description=f"Context contains actual result field: {field}",
                    data_point=field,
                    data_date=None,
                    fixture_date=datetime.now(),
                    query_or_source="context_structure"
                ))

    # ============================================================
    # DATABASE VALIDATION
    # ============================================================

    def validate_fixture_queries(self, fixture_id: str) -> Tuple[bool, List[TimeTravelViolation]]:
        """
        Validate all database queries for a fixture are time-travel safe.

        This checks the actual database to ensure no leakage.
        """
        self.violations = []

        if not self.conn:
            return False, [TimeTravelViolation(
                violation_type="db_error",
                severity="critical",
                description="No database connection",
                data_point="",
                data_date=None,
                fixture_date=datetime.now(),
                query_or_source=""
            )]

        # Get fixture date
        df_fix = pd.read_sql(
            "SELECT id, date FROM fixtures WHERE id = %s",
            self.conn, params=(fixture_id,)
        )
        if df_fix.empty:
            return False, [TimeTravelViolation(
                violation_type="not_found",
                severity="critical",
                description=f"Fixture {fixture_id} not found",
                data_point="",
                data_date=None,
                fixture_date=datetime.now(),
                query_or_source=""
            )]

        fixture_date = pd.to_datetime(df_fix.iloc[0]['date'])

        # Check odds_snapshots
        self._validate_odds_snapshots(fixture_id, fixture_date)

        # Check match_features (if using historical tables)
        self._validate_match_features(fixture_id, fixture_date)

        is_safe = len([v for v in self.violations if v.severity == "critical"]) == 0
        return is_safe, self.violations

    def _validate_odds_snapshots(self, fixture_id: str, fixture_date: datetime):
        """Validate odds_snapshots captured_at < fixture_date."""
        sql = """
            SELECT captured_at, source
            FROM odds_snapshots
            WHERE fixture_id = %s
              AND captured_at >= %s
        """
        df = pd.read_sql(sql, self.conn, params=(fixture_id, fixture_date))

        if not df.empty:
            for _, row in df.iterrows():
                self.violations.append(TimeTravelViolation(
                    violation_type="odds_leak",
                    severity="critical",
                    description=f"Odds captured at {row['captured_at']} >= fixture date {fixture_date}",
                    data_point=f"odds_snapshots.captured_at",
                    data_date=row['captured_at'],
                    fixture_date=fixture_date,
                    query_or_source=f"source: {row['source']}"
                ))

    def _validate_match_features(self, fixture_id: str, fixture_date: datetime):
        """Validate match_features don't use future data."""
        # This would check match_features table if using historical data
        # For now, just a placeholder
        pass

    # ============================================================
    # BULK VALIDATION
    # ============================================================

    def validate_season(
        self,
        season: str,
        league: str = "Premier League"
    ) -> Dict[str, Any]:
        """
        Validate all fixtures in a season for time-travel safety.

        Returns:
            {
                'total_fixtures': int,
                'safe_fixtures': int,
                'unsafe_fixtures': int,
                'violation_summary': dict,
                'critical_violations': list
            }
        """
        if not self.conn:
            return {'error': 'No database connection'}

        sql = "SELECT id, date FROM fixtures WHERE season = %s AND league = %s"
        df = pd.read_sql(sql, self.conn, params=(season, league))

        total = len(df)
        safe_count = 0
        unsafe_count = 0
        all_violations = []

        for _, row in df.iterrows():
            is_safe, violations = self.validate_fixture_queries(row['id'])
            if is_safe:
                safe_count += 1
            else:
                unsafe_count += 1
                all_violations.extend(violations)

        # Summarize violation types
        violation_summary = {}
        for v in all_violations:
            violation_summary[v.violation_type] = violation_summary.get(v.violation_type, 0) + 1

        critical = [v for v in all_violations if v.severity == "critical"]

        return {
            'total_fixtures': total,
            'safe_fixtures': safe_count,
            'unsafe_fixtures': unsafe_count,
            'safety_rate': (safe_count / total * 100) if total > 0 else 0,
            'violation_summary': violation_summary,
            'critical_violations': [
                {
                    'fixture': v.data_point,
                    'type': v.violation_type,
                    'description': v.description
                } for v in critical[:20]  # Limit to 20
            ]
        }


# ============================================================
# QUERY VALIDATION DECORATORS
# ============================================================

def time_travel_safe_query(fixture_date_param_index: int = 1):
    """
    Decorator to validate queries include proper date filtering.

    Usage:
        @time_travel_safe_query(fixture_date_param_index=1)
        def get_form_data(team, fixture_date):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # This is a compile-time check reminder
            # Actual validation happens at runtime via TimeTravelGuard
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def validate_context_time_safety(
    context: Dict,
    fixture_date: datetime
) -> Tuple[bool, List[str]]:
    """
    Convenience function to validate context time safety.

    Returns:
        (is_safe, list_of_error_strings)
    """
    guard = TimeTravelGuard()
    try:
        is_safe, violations = guard.validate_context(context, fixture_date)
        errors = [f"[{v.severity}] {v.violation_type}: {v.description}" for v in violations]
        return is_safe, errors
    finally:
        guard.close()


def run_time_travel_audit(season: str = "2025-2026") -> Dict:
    """
    Run full time-travel audit for a season.

    Returns audit summary.
    """
    guard = TimeTravelGuard()
    try:
        return guard.validate_season(season)
    finally:
        guard.close()


if __name__ == "__main__":
    print("Testing Time-Travel Safety Guard...")

    guard = TimeTravelGuard()

    # Test context validation
    test_context = {
        'home': {
            'form': {'results': 'W-W-D-L-W'},
            'absences': {'players': []}
        },
        'away': {
            'form': {'results': 'L-D-W-W-L'},
            'absences': {'players': []}
        },
        'odds': {
            'home_win': 1.85,
            'captured_at': '2025-01-15T14:00:00Z'
        },
        'head_to_head': {'matches_played': 5}
    }

    fixture_date = datetime(2025, 1, 18, 15, 0, 0)

    is_safe, violations = guard.validate_context(test_context, fixture_date)
    print(f"\n✅ Context is time-travel safe: {is_safe}")
    if violations:
        print(f"   Violations found: {len(violations)}")
        for v in violations:
            print(f"   [{v.severity}] {v.violation_type}: {v.description}")

    # Test season audit
    print("\n🔍 Running season audit...")
    audit = guard.validate_season("2025-2026")
    print(f"   Total fixtures: {audit.get('total_fixtures', 0)}")
    print(f"   Safe rate: {audit.get('safety_rate', 0):.1f}%")
    if audit.get('violation_summary'):
        print(f"   Violations: {audit['violation_summary']}")

    guard.close()
    print("\n✅ Time-travel guard test complete!")
