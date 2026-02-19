"""
Data Coverage Diagnostics - Phase 1 (P1-002, P1-004)

Validates data source reliability and identifies coverage gaps.
Generates reports showing where missing data will reduce narrative quality.

Usage:
    from src.analysis.data_coverage import CoverageReport, run_coverage_diagnostics

    report = run_coverage_diagnostics(season="2025-2026")
    print(report.summary())
"""

import pandas as pd
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
import json

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class DataSourceStatus:
    """Status of a single data source."""
    source_name: str
    table_name: str
    description: str
    total_records: int
    coverage_percentage: float
    last_updated: Optional[datetime]
    failure_modes: List[str] = field(default_factory=list)
    fallback_rules: List[str] = field(default_factory=list)
    is_healthy: bool = True


@dataclass
class FixtureCoverage:
    """Coverage details for a single fixture."""
    fixture_id: str
    home_team: str
    away_team: str
    date: datetime
    round_number: Optional[int]
    has_team_stats: bool
    has_xg_data: bool
    has_elo_data: bool
    has_ppda_data: bool
    has_form_data: bool
    has_h2h_data: bool
    has_odds_data: bool
    has_injury_data: bool
    has_lineup_data: bool
    coverage_score: float  # 0-100


@dataclass
class SeasonCoverage:
    """Aggregated coverage for a season."""
    season: str
    league: str
    total_fixtures: int
    fixtures_with_full_coverage: int
    avg_coverage_score: float
    min_coverage_score: float
    max_coverage_score: float
    coverage_by_round: Dict[int, float] = field(default_factory=dict)
    coverage_by_team: Dict[str, float] = field(default_factory=dict)


@dataclass
class CoverageReport:
    """Complete coverage diagnostics report."""
    generated_at: datetime
    season: str
    league: str
    data_sources: List[DataSourceStatus]
    season_coverage: SeasonCoverage
    fixtures_below_threshold: List[FixtureCoverage]
    missing_signals_summary: Dict[str, int]
    recommendations: List[str]

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            "=" * 60,
            f"DATA COVERAGE REPORT - {self.season}",
            "=" * 60,
            "",
            f"Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "📊 OVERALL COVERAGE",
            f"   Total Fixtures: {self.season_coverage.total_fixtures}",
            f"   Avg Coverage Score: {self.season_coverage.avg_coverage_score:.1f}%",
            f"   Full Coverage: {self.season_coverage.fixtures_with_full_coverage} fixtures",
            "",
            "📡 DATA SOURCES",
        ]

        for source in self.data_sources:
            status = "✅" if source.is_healthy else "⚠️"
            lines.append(f"   {status} {source.source_name}: {source.coverage_percentage:.1f}% ({source.total_records} records)")

        lines.extend([
            "",
            "⚠️ MISSING SIGNALS",
        ])

        for signal, count in sorted(self.missing_signals_summary.items(), key=lambda x: -x[1]):
            lines.append(f"   {signal}: {count} fixtures missing")

        if self.fixtures_below_threshold:
            lines.extend([
                "",
                f"🔴 FIXTURES BELOW THRESHOLD ({len(self.fixtures_below_threshold)})",
            ])
            for fix in self.fixtures_below_threshold[:10]:
                lines.append(f"   {fix.fixture_id}: {fix.coverage_score:.0f}%")

        if self.recommendations:
            lines.extend([
                "",
                "💡 RECOMMENDATIONS",
            ])
            for rec in self.recommendations:
                lines.append(f"   • {rec}")

        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        def default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        return json.dumps(self.to_dict(), default=default_serializer, indent=indent)


# ============================================================
# COVERAGE ANALYZER
# ============================================================

class CoverageAnalyzer:
    """Analyzes data coverage across sources and fixtures."""

    COVERAGE_THRESHOLD = 70.0  # Minimum acceptable coverage %

    def __init__(self):
        self.conn = get_connection()

    def close(self):
        if self.conn:
            self.conn.close()

    def generate_report(
        self,
        season: str = "2025-2026",
        league: str = "Premier League"
    ) -> CoverageReport:
        """Generate comprehensive coverage report."""

        data_sources = self._check_data_sources(season)
        fixtures = self._get_fixture_coverage(season, league)
        season_coverage = self._aggregate_season_coverage(fixtures, season, league)
        missing_summary = self._summarize_missing_signals(fixtures)
        below_threshold = [f for f in fixtures if f.coverage_score < self.COVERAGE_THRESHOLD]
        recommendations = self._generate_recommendations(data_sources, missing_summary)

        return CoverageReport(
            generated_at=datetime.utcnow(),
            season=season,
            league=league,
            data_sources=data_sources,
            season_coverage=season_coverage,
            fixtures_below_threshold=below_threshold,
            missing_signals_summary=missing_summary,
            recommendations=recommendations
        )

    def _check_data_sources(self, season: str) -> List[DataSourceStatus]:
        """Check status of all data sources."""
        sources = []

        # 1. FBRef (via team_stats)
        sql = """
            SELECT COUNT(*) as cnt,
                   SUM(CASE WHEN xg IS NOT NULL THEN 1 ELSE 0 END) as with_xg
            FROM team_stats ts
            JOIN fixtures f ON ts.fixture_id = f.id
            WHERE f.season = %s
        """
        df = pd.read_sql(sql, self.conn, params=(season,))
        total = int(df.iloc[0]['cnt']) if not df.empty else 0
        with_xg = int(df.iloc[0]['with_xg']) if not df.empty else 0

        sources.append(DataSourceStatus(
            source_name="FBRef (xG/Stats)",
            table_name="team_stats",
            description="Match xG, PPDA, field tilt from FBRef",
            total_records=total,
            coverage_percentage=(with_xg / total * 100) if total > 0 else 0,
            last_updated=None,
            failure_modes=["Cloudflare blocking", "DOM structure changes"],
            fallback_rules=["Use season averages if match stats missing"],
            is_healthy=with_xg > 0
        ))

        # 2. ClubElo
        sql_elo = """
            SELECT COUNT(*) as cnt,
                   SUM(CASE WHEN elo IS NOT NULL THEN 1 ELSE 0 END) as with_elo
            FROM team_stats ts
            JOIN fixtures f ON ts.fixture_id = f.id
            WHERE f.season = %s
        """
        df_elo = pd.read_sql(sql_elo, self.conn, params=(season,))
        elo_total = int(df_elo.iloc[0]['cnt']) if not df_elo.empty else 0
        elo_count = int(df_elo.iloc[0]['with_elo']) if not df_elo.empty else 0

        sources.append(DataSourceStatus(
            source_name="ClubElo (Ratings)",
            table_name="team_stats.elo",
            description="Team Elo ratings",
            total_records=elo_count,
            coverage_percentage=(elo_count / elo_total * 100) if elo_total > 0 else 0,
            last_updated=None,
            failure_modes=["API rate limiting", "Team name mapping failures"],
            fallback_rules=["Default to Elo 1500 if missing"],
            is_healthy=elo_count > 0
        ))

        # 3. Odds
        sql_odds = """
            SELECT COUNT(DISTINCT fixture_id) as cnt
            FROM market_odds
        """
        df_odds = pd.read_sql(sql_odds, self.conn)
        odds_count = int(df_odds.iloc[0]['cnt']) if not df_odds.empty else 0

        sql_fixtures = "SELECT COUNT(*) as cnt FROM fixtures WHERE season = %s"
        df_fix = pd.read_sql(sql_fixtures, self.conn, params=(season,))
        fix_count = int(df_fix.iloc[0]['cnt']) if not df_fix.empty else 1

        sources.append(DataSourceStatus(
            source_name="Market Odds",
            table_name="market_odds",
            description="Pre-match 1X2 odds",
            total_records=odds_count,
            coverage_percentage=(odds_count / fix_count * 100) if fix_count > 0 else 0,
            last_updated=None,
            failure_modes=["Manual CSV import required", "Provider changes"],
            fallback_rules=["Context can work without odds"],
            is_healthy=odds_count > 0
        ))

        # 4. Understat (PPDA/Field Tilt)
        sql_ppda = """
            SELECT COUNT(*) as cnt,
                   SUM(CASE WHEN ppda IS NOT NULL THEN 1 ELSE 0 END) as with_ppda
            FROM team_stats ts
            JOIN fixtures f ON ts.fixture_id = f.id
            WHERE f.season = %s
        """
        df_ppda = pd.read_sql(sql_ppda, self.conn, params=(season,))
        ppda_total = int(df_ppda.iloc[0]['cnt']) if not df_ppda.empty else 0
        ppda_count = int(df_ppda.iloc[0]['with_ppda']) if not df_ppda.empty else 0

        sources.append(DataSourceStatus(
            source_name="Understat (Tactical)",
            table_name="team_stats.ppda/field_tilt",
            description="PPDA and field tilt metrics",
            total_records=ppda_count,
            coverage_percentage=(ppda_count / ppda_total * 100) if ppda_total > 0 else 0,
            last_updated=None,
            failure_modes=["API changes", "Team name mapping"],
            fallback_rules=["Use league averages if missing"],
            is_healthy=ppda_count > 0
        ))

        # 5. Injuries (Historical)
        sql_inj = "SELECT COUNT(*) as cnt FROM player_injuries_historical"
        df_inj = pd.read_sql(sql_inj, self.conn)
        inj_count = int(df_inj.iloc[0]['cnt']) if not df_inj.empty else 0

        sources.append(DataSourceStatus(
            source_name="Injuries (Transfermarkt)",
            table_name="player_injuries_historical",
            description="Player injury history",
            total_records=inj_count,
            coverage_percentage=100.0 if inj_count > 0 else 0.0,
            last_updated=None,
            failure_modes=["Stale data", "Player ID mapping issues"],
            fallback_rules=["Context works without specific injury data"],
            is_healthy=inj_count > 0
        ))

        return sources

    def _get_fixture_coverage(
        self,
        season: str,
        league: str
    ) -> List[FixtureCoverage]:
        """Calculate coverage for each fixture."""

        # Get all fixtures
        sql = """
            SELECT
                f.id as fixture_id,
                f.home_team,
                f.away_team,
                f.date,
                f.round,
                -- Team stats presence
                COALESCE(ts_home.xg IS NOT NULL, FALSE) as has_home_xg,
                COALESCE(ts_away.xg IS NOT NULL, FALSE) as has_away_xg,
                COALESCE(ts_home.elo IS NOT NULL, FALSE) as has_home_elo,
                COALESCE(ts_away.elo IS NOT NULL, FALSE) as has_away_elo,
                COALESCE(ts_home.ppda IS NOT NULL, FALSE) as has_home_ppda,
                COALESCE(ts_away.ppda IS NOT NULL, FALSE) as has_away_ppda,
                -- Odds presence
                COALESCE(mo.home_win IS NOT NULL, FALSE) as has_odds
            FROM fixtures f
            LEFT JOIN team_stats ts_home ON f.id = ts_home.fixture_id AND ts_home.team_name = f.home_team
            LEFT JOIN team_stats ts_away ON f.id = ts_away.fixture_id AND ts_away.team_name = f.away_team
            LEFT JOIN market_odds mo ON f.id = mo.fixture_id
            WHERE f.season = %s AND f.league = %s
            ORDER BY f.date
        """
        df = pd.read_sql(sql, self.conn, params=(season, league))

        coverages = []
        for _, row in df.iterrows():
            # Calculate individual coverage flags
            has_xg = bool(row['has_home_xg'] and row['has_away_xg'])
            has_elo = bool(row['has_home_elo'] and row['has_away_elo'])
            has_ppda = bool(row['has_home_ppda'] and row['has_away_ppda'])
            has_odds = bool(row['has_odds'])

            # Form data - check if we have prior matches
            has_form = self._check_form_data(row['home_team'], row['away_team'], row['date'])

            # H2H data
            has_h2h = self._check_h2h_data(row['home_team'], row['away_team'], row['date'])

            # Injury/lineup data (placeholder - needs team_id mapping)
            has_injury = False  # Would need proper implementation
            has_lineup = False

            # Calculate coverage score (weighted)
            weights = {
                'xg': 20,
                'elo': 15,
                'ppda': 10,
                'form': 25,
                'h2h': 10,
                'odds': 10,
                'injury': 5,
                'lineup': 5
            }

            score = 0
            if has_xg: score += weights['xg']
            if has_elo: score += weights['elo']
            if has_ppda: score += weights['ppda']
            if has_form: score += weights['form']
            if has_h2h: score += weights['h2h']
            if has_odds: score += weights['odds']
            if has_injury: score += weights['injury']
            if has_lineup: score += weights['lineup']

            coverages.append(FixtureCoverage(
                fixture_id=row['fixture_id'],
                home_team=row['home_team'],
                away_team=row['away_team'],
                date=row['date'],
                round_number=row['round'],
                has_team_stats=has_xg,
                has_xg_data=has_xg,
                has_elo_data=has_elo,
                has_ppda_data=has_ppda,
                has_form_data=has_form,
                has_h2h_data=has_h2h,
                has_odds_data=has_odds,
                has_injury_data=has_injury,
                has_lineup_data=has_lineup,
                coverage_score=score
            ))

        return coverages

    def _check_form_data(self, home_team: str, away_team: str, match_date: datetime) -> bool:
        """Check if we have form data (prior matches) for both teams."""
        sql = """
            SELECT COUNT(*) as cnt FROM fixtures
            WHERE (home_team = %s OR away_team = %s)
              AND date < %s
              AND status = 'FINISHED'
        """
        df_home = pd.read_sql(sql, self.conn, params=(home_team, home_team, match_date))
        df_away = pd.read_sql(sql, self.conn, params=(away_team, away_team, match_date))

        home_count = int(df_home.iloc[0]['cnt']) if not df_home.empty else 0
        away_count = int(df_away.iloc[0]['cnt']) if not df_away.empty else 0

        return home_count >= 3 and away_count >= 3

    def _check_h2h_data(self, home_team: str, away_team: str, match_date: datetime) -> bool:
        """Check if we have H2H history."""
        sql = """
            SELECT COUNT(*) as cnt FROM fixtures
            WHERE ((home_team = %s AND away_team = %s) OR (home_team = %s AND away_team = %s))
              AND date < %s
              AND status = 'FINISHED'
        """
        df = pd.read_sql(sql, self.conn, params=(home_team, away_team, away_team, home_team, match_date))
        return int(df.iloc[0]['cnt']) >= 1 if not df.empty else False

    def _aggregate_season_coverage(
        self,
        fixtures: List[FixtureCoverage],
        season: str,
        league: str
    ) -> SeasonCoverage:
        """Aggregate coverage metrics for the season."""

        if not fixtures:
            return SeasonCoverage(
                season=season,
                league=league,
                total_fixtures=0,
                fixtures_with_full_coverage=0,
                avg_coverage_score=0.0,
                min_coverage_score=0.0,
                max_coverage_score=0.0
            )

        scores = [f.coverage_score for f in fixtures]

        # By round
        by_round: Dict[int, List[float]] = {}
        for f in fixtures:
            if f.round_number is not None:
                by_round.setdefault(f.round_number, []).append(f.coverage_score)

        coverage_by_round = {r: sum(s)/len(s) for r, s in by_round.items()}

        # By team
        by_team: Dict[str, List[float]] = {}
        for f in fixtures:
            by_team.setdefault(f.home_team, []).append(f.coverage_score)
            by_team.setdefault(f.away_team, []).append(f.coverage_score)

        coverage_by_team = {t: sum(s)/len(s) for t, s in by_team.items()}

        return SeasonCoverage(
            season=season,
            league=league,
            total_fixtures=len(fixtures),
            fixtures_with_full_coverage=sum(1 for s in scores if s >= 90),
            avg_coverage_score=sum(scores) / len(scores),
            min_coverage_score=min(scores),
            max_coverage_score=max(scores),
            coverage_by_round=coverage_by_round,
            coverage_by_team=coverage_by_team
        )

    def _summarize_missing_signals(self, fixtures: List[FixtureCoverage]) -> Dict[str, int]:
        """Count missing signals across all fixtures."""
        missing = {
            'xg_data': 0,
            'elo_data': 0,
            'ppda_data': 0,
            'form_data': 0,
            'h2h_data': 0,
            'odds_data': 0,
            'injury_data': 0,
            'lineup_data': 0
        }

        for f in fixtures:
            if not f.has_xg_data: missing['xg_data'] += 1
            if not f.has_elo_data: missing['elo_data'] += 1
            if not f.has_ppda_data: missing['ppda_data'] += 1
            if not f.has_form_data: missing['form_data'] += 1
            if not f.has_h2h_data: missing['h2h_data'] += 1
            if not f.has_odds_data: missing['odds_data'] += 1
            if not f.has_injury_data: missing['injury_data'] += 1
            if not f.has_lineup_data: missing['lineup_data'] += 1

        return missing

    def _generate_recommendations(
        self,
        sources: List[DataSourceStatus],
        missing: Dict[str, int]
    ) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        for source in sources:
            if source.coverage_percentage < 50:
                recommendations.append(
                    f"Critical: {source.source_name} has only {source.coverage_percentage:.0f}% coverage. "
                    f"Check {source.failure_modes[0] if source.failure_modes else 'data pipeline'}."
                )

        if missing.get('xg_data', 0) > 10:
            recommendations.append(
                "Run FBRef scraper to backfill missing xG data: python -m src.ingestion.scraper"
            )

        if missing.get('elo_data', 0) > 10:
            recommendations.append(
                "Run Elo backfill to update ratings: python -m src.ingestion.elo_backfill"
            )

        if missing.get('odds_data', 0) > 10:
            recommendations.append(
                "Import odds CSV to fill market data: python scripts/import_odds_csv.py"
            )

        if missing.get('injury_data', 0) == len(missing):
            recommendations.append(
                "Injury data integration pending. Consider running Transfermarkt import."
            )

        return recommendations


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def run_coverage_diagnostics(
    season: str = "2025-2026",
    league: str = "Premier League"
) -> CoverageReport:
    """
    Run full coverage diagnostics.

    Args:
        season: Season to analyze
        league: League to analyze

    Returns:
        CoverageReport with all diagnostics
    """
    analyzer = CoverageAnalyzer()
    try:
        return analyzer.generate_report(season=season, league=league)
    finally:
        analyzer.close()


def save_coverage_report(
    report: CoverageReport,
    output_path: Optional[Path] = None
) -> Path:
    """
    Save coverage report to JSON file.

    Args:
        report: CoverageReport to save
        output_path: Optional path (defaults to data/coverage_reports/)

    Returns:
        Path to saved file
    """
    if output_path is None:
        output_dir = PROJECT_ROOT / "data" / "coverage_reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"coverage_{report.season}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    output_path.write_text(report.to_json())
    return output_path


if __name__ == "__main__":
    print("Running Data Coverage Diagnostics...")

    report = run_coverage_diagnostics(season="2025-2026")
    print(report.summary())

    # Save to file
    path = save_coverage_report(report)
    print(f"\n📁 Report saved to: {path}")
