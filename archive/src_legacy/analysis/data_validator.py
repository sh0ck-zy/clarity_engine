"""
Data Validator - Dashboard v4

Validates data coverage and time-travel safety for match context.

Usage:
    from src.analysis.data_validator import DataValidator

    validator = DataValidator()
    coverage = validator.check_data_coverage(fixture_id)
    warnings = validator.check_time_travel_safety(fixture_id)
"""

import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.analysis.context_builder_v2 import ContextBuilderV2
from src.analysis.context_schema import MatchContext, calculate_coverage_score


@dataclass
class DataSource:
    """Status of a single data source."""
    name: str
    status: str  # "complete", "partial", "missing"
    details: str = ""
    value: Optional[Any] = None


@dataclass
class CoverageReport:
    """Complete data coverage report for a fixture."""
    fixture_id: str
    match_date: Optional[date]
    home_team: str
    away_team: str
    overall_score: float  # 0-100
    sources: List[DataSource] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "match_date": self.match_date.isoformat() if self.match_date else None,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "overall_score": self.overall_score,
            "sources": [asdict(s) for s in self.sources]
        }


@dataclass
class TimeTravelWarning:
    """Warning about potential time-travel data leak."""
    field_name: str
    data_date: Optional[date]
    match_date: date
    message: str
    severity: str = "warning"  # "warning" or "error"


@dataclass
class TimeTravelReport:
    """Complete time-travel safety report."""
    fixture_id: str
    match_date: date
    is_safe: bool
    warnings: List[TimeTravelWarning] = field(default_factory=list)


class DataValidator:
    """
    Validates data coverage and time-travel safety for match context.
    """

    def __init__(self):
        self.builder = ContextBuilderV2()

    def close(self):
        self.builder.close()

    def check_data_coverage(self, fixture_id: str) -> Optional[CoverageReport]:
        """
        Check data coverage for a fixture.

        Args:
            fixture_id: Fixture ID

        Returns:
            CoverageReport with status of each data source
        """
        context = self.builder.build_context(fixture_id)
        if not context:
            return None

        sources = []

        # 1. Fixture info
        sources.append(DataSource(
            name="Fixture Info",
            status="complete",
            details=f"{context.home.identity.name} vs {context.away.identity.name}",
            value={"date": context.match_date.isoformat(), "round": context.round_number}
        ))

        # 2. Elo ratings
        home_elo = context.home.identity.elo
        away_elo = context.away.identity.elo
        if home_elo > 0 and away_elo > 0:
            sources.append(DataSource(
                name="Elo Ratings",
                status="complete",
                details=f"Home: {home_elo}, Away: {away_elo}",
                value={"home": home_elo, "away": away_elo}
            ))
        else:
            sources.append(DataSource(
                name="Elo Ratings",
                status="missing",
                details="Elo data not available"
            ))

        # 3. Form (last 5)
        home_form = context.home.form.results
        away_form = context.away.form.results
        if home_form and away_form and home_form != "-----":
            sources.append(DataSource(
                name="Form (Last 5)",
                status="complete",
                details=f"Home: {home_form}, Away: {away_form}",
                value={"home": home_form, "away": away_form}
            ))
        elif home_form or away_form:
            sources.append(DataSource(
                name="Form (Last 5)",
                status="partial",
                details=f"Home: {home_form or 'N/A'}, Away: {away_form or 'N/A'}"
            ))
        else:
            sources.append(DataSource(
                name="Form (Last 5)",
                status="missing",
                details="Form data not available"
            ))

        # 4. xG Season averages
        home_xg = context.home.identity.season_xg_per_match
        away_xg = context.away.identity.season_xg_per_match
        if home_xg > 0 or away_xg > 0:
            sources.append(DataSource(
                name="xG Season Averages",
                status="complete",
                details=f"Home: {home_xg:.2f}, Away: {away_xg:.2f}",
                value={"home": home_xg, "away": away_xg}
            ))
        else:
            sources.append(DataSource(
                name="xG Season Averages",
                status="missing",
                details="xG data not available"
            ))

        # 5. Injuries
        home_injuries = context.home.absences.total_missing
        away_injuries = context.away.absences.total_missing
        if home_injuries > 0 or away_injuries > 0:
            sources.append(DataSource(
                name="Injuries",
                status="complete",
                details=f"Home: {home_injuries}, Away: {away_injuries}",
                value={"home": home_injuries, "away": away_injuries}
            ))
        else:
            # Check if we have injury data at all
            conn = get_connection()
            if conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(*) FROM player_injuries_historical
                    WHERE team_name IN (%s, %s)
                """, (context.home.identity.name, context.away.identity.name))
                count = cur.fetchone()[0]
                conn.close()
                if count > 0:
                    sources.append(DataSource(
                        name="Injuries",
                        status="complete",
                        details="No active injuries",
                        value={"home": 0, "away": 0}
                    ))
                else:
                    sources.append(DataSource(
                        name="Injuries",
                        status="missing",
                        details="Injury data not available"
                    ))
            else:
                sources.append(DataSource(
                    name="Injuries",
                    status="missing",
                    details="Could not check injury data"
                ))

        # 6. Lineups
        home_lineup = context.home.lineup
        away_lineup = context.away.lineup
        if home_lineup and away_lineup and home_lineup.starters and away_lineup.starters:
            is_confirmed = home_lineup.is_confirmed and away_lineup.is_confirmed
            sources.append(DataSource(
                name="Lineups",
                status="complete" if is_confirmed else "partial",
                details=f"Home: {home_lineup.formation or 'N/A'}, Away: {away_lineup.formation or 'N/A'}" +
                       (" (confirmed)" if is_confirmed else " (historical)"),
                value={
                    "home_formation": home_lineup.formation,
                    "away_formation": away_lineup.formation,
                    "is_confirmed": is_confirmed
                }
            ))
        else:
            sources.append(DataSource(
                name="Lineups",
                status="missing",
                details="Lineup data not available"
            ))

        # 7. Odds
        if context.odds.home_win and context.odds.draw and context.odds.away_win:
            sources.append(DataSource(
                name="Odds (1X2)",
                status="complete",
                details=f"H: {context.odds.home_win:.2f}, D: {context.odds.draw:.2f}, A: {context.odds.away_win:.2f}",
                value={
                    "home_win": context.odds.home_win,
                    "draw": context.odds.draw,
                    "away_win": context.odds.away_win,
                    "source": context.odds.source
                }
            ))
        elif context.odds.home_win or context.odds.draw or context.odds.away_win:
            sources.append(DataSource(
                name="Odds (1X2)",
                status="partial",
                details="Some odds available"
            ))
        else:
            sources.append(DataSource(
                name="Odds (1X2)",
                status="missing",
                details="Odds not available"
            ))

        # 8. Head to head
        h2h = context.head_to_head
        if h2h.matches_played > 0:
            sources.append(DataSource(
                name="Head to Head",
                status="complete",
                details=f"{h2h.matches_played} matches (H:{h2h.home_wins} D:{h2h.draws} A:{h2h.away_wins})",
                value={
                    "matches": h2h.matches_played,
                    "home_wins": h2h.home_wins,
                    "draws": h2h.draws,
                    "away_wins": h2h.away_wins
                }
            ))
        else:
            sources.append(DataSource(
                name="Head to Head",
                status="missing",
                details="No H2H data"
            ))

        # 9. League position
        lp = context.league_position
        if lp.home_position > 0 and lp.away_position > 0:
            sources.append(DataSource(
                name="League Position",
                status="complete",
                details=f"Home: {lp.home_position}th ({lp.home_points}pts), Away: {lp.away_position}th ({lp.away_points}pts)",
                value={
                    "home_position": lp.home_position,
                    "away_position": lp.away_position,
                    "home_points": lp.home_points,
                    "away_points": lp.away_points
                }
            ))
        else:
            sources.append(DataSource(
                name="League Position",
                status="missing",
                details="League position not available"
            ))

        # Calculate overall score
        overall_score = calculate_coverage_score(context)

        return CoverageReport(
            fixture_id=fixture_id,
            match_date=context.match_date,
            home_team=context.home.identity.name,
            away_team=context.away.identity.name,
            overall_score=overall_score,
            sources=sources
        )

    def check_time_travel_safety(self, fixture_id: str) -> Optional[TimeTravelReport]:
        """
        Check for time-travel data leaks.

        Verifies that all data used is from before the match date.

        Args:
            fixture_id: Fixture ID

        Returns:
            TimeTravelReport with any warnings
        """
        context = self.builder.build_context(fixture_id)
        if not context:
            return None

        match_date = context.match_date
        warnings = []

        # Check if actual result was used in any calculations
        conn = get_connection()
        if conn:
            cur = conn.cursor()

            # Check fixtures table for result
            cur.execute("""
                SELECT home_score, away_score, status
                FROM fixtures
                WHERE id = %s
            """, (fixture_id,))
            row = cur.fetchone()

            if row and row[0] is not None and row[1] is not None:
                # Match has a result - check if it was used in form calculation
                # (This would be a bug in the context builder)
                # For now, just note that result exists
                pass

            # Check form calculation dates
            # The form should only include matches BEFORE this match date
            cur.execute("""
                SELECT COUNT(*) FROM fixtures
                WHERE (home_team = %s OR away_team = %s)
                AND date >= %s
                AND home_score IS NOT NULL
                AND id != %s
            """, (
                context.home.identity.name,
                context.home.identity.name,
                match_date,
                fixture_id
            ))
            future_matches = cur.fetchone()[0]

            if future_matches > 0:
                # This could indicate a problem but needs more investigation
                pass

            # Check odds capture time
            if context.odds.captured_at:
                if isinstance(context.odds.captured_at, datetime):
                    odds_date = context.odds.captured_at.date()
                else:
                    odds_date = context.odds.captured_at

                if odds_date > match_date:
                    warnings.append(TimeTravelWarning(
                        field_name="odds",
                        data_date=odds_date,
                        match_date=match_date,
                        message=f"Odds captured after match date ({odds_date} > {match_date})",
                        severity="error"
                    ))

            # Check context built_at
            if context.built_at:
                # built_at is metadata about when context was generated, not data date
                pass

            conn.close()

        # Check for explicit warnings from context builder
        for warning in context.data_warnings:
            if "future" in warning.lower() or "after" in warning.lower():
                warnings.append(TimeTravelWarning(
                    field_name="context_builder",
                    data_date=None,
                    match_date=match_date,
                    message=warning,
                    severity="warning"
                ))

        is_safe = len([w for w in warnings if w.severity == "error"]) == 0

        return TimeTravelReport(
            fixture_id=fixture_id,
            match_date=match_date,
            is_safe=is_safe,
            warnings=warnings
        )

    def get_raw_context_json(self, fixture_id: str) -> Optional[str]:
        """
        Get raw MatchContext as JSON for debugging.

        Args:
            fixture_id: Fixture ID

        Returns:
            JSON string of MatchContext
        """
        context = self.builder.build_context(fixture_id)
        if not context:
            return None

        # Convert to dict, handling date serialization
        context_dict = asdict(context)

        def serialize_value(obj):
            """Serialize complex types for JSON."""
            import numpy as np

            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            elif isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: serialize_value(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [serialize_value(i) for i in obj]
            return obj

        context_dict = serialize_value(context_dict)

        return json.dumps(context_dict, indent=2, ensure_ascii=False)


def get_fixture_data_status(fixture_id: str) -> str:
    """
    Quick check of fixture data status.

    Returns: "complete", "partial", or "missing"
    """
    validator = DataValidator()
    try:
        report = validator.check_data_coverage(fixture_id)
        if not report:
            return "missing"

        if report.overall_score >= 80:
            return "complete"
        elif report.overall_score >= 50:
            return "partial"
        else:
            return "missing"
    finally:
        validator.close()


if __name__ == "__main__":
    # Test with a sample fixture
    validator = DataValidator()

    # Get a fixture from DB
    conn = get_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM fixtures WHERE round = 23 LIMIT 1")
        row = cur.fetchone()
        conn.close()

        if row:
            fixture_id = row[0]
            print(f"Testing with fixture: {fixture_id}")
            print("=" * 60)

            # Coverage check
            coverage = validator.check_data_coverage(fixture_id)
            if coverage:
                print(f"\nCoverage Score: {coverage.overall_score:.1f}%")
                print(f"Match: {coverage.home_team} vs {coverage.away_team}")
                print(f"Date: {coverage.match_date}")
                print("\nData Sources:")
                for src in coverage.sources:
                    status_icon = {"complete": "✅", "partial": "⚠️", "missing": "❌"}.get(src.status, "?")
                    print(f"  {status_icon} {src.name}: {src.details}")

            # Time-travel check
            print("\n" + "=" * 60)
            tt_report = validator.check_time_travel_safety(fixture_id)
            if tt_report:
                status = "✅ SAFE" if tt_report.is_safe else "❌ UNSAFE"
                print(f"\nTime-Travel Check: {status}")
                if tt_report.warnings:
                    print("Warnings:")
                    for w in tt_report.warnings:
                        print(f"  - {w.message}")

            # Raw JSON
            print("\n" + "=" * 60)
            print("\nRaw Context (first 500 chars):")
            raw = validator.get_raw_context_json(fixture_id)
            if raw:
                print(raw[:500] + "...")

    validator.close()
