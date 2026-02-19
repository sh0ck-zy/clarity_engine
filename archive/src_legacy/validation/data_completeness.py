from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Iterable, Optional


EXPECTED_FIXTURES_BY_LEAGUE = {
    1: 380,
}


@dataclass(frozen=True)
class CoverageMetric:
    expected: int
    actual: int
    coverage: float
    missing: int
    missing_sample: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlayerMarketCoverage:
    player_stats_count: int
    market_values_count: int
    coverage: float
    missing: int
    missing_sample: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class FixtureCoverage:
    expected: int
    actual: int
    coverage: float
    missing: int
    first_date: Optional[str]
    last_date: Optional[str]


@dataclass(frozen=True)
class DataCompletenessReport:
    season: int
    league_id: int
    generated_at: str
    fixtures: FixtureCoverage
    team_match_stats: CoverageMetric
    lineups: CoverageMetric
    player_market_values: PlayerMarketCoverage
    odds: CoverageMetric

    def to_dict(self) -> dict:
        return asdict(self)


def _coverage_metric(
    expected: int,
    actual: int,
    missing_ids: Iterable[str],
    sample_limit: int,
) -> CoverageMetric:
    expected = max(expected, 0)
    actual = max(actual, 0)
    missing = max(expected - actual, 0)
    coverage = actual / expected if expected else 0.0
    sample = [item for item in missing_ids][:sample_limit]
    return CoverageMetric(
        expected=expected,
        actual=actual,
        coverage=round(coverage, 4),
        missing=missing,
        missing_sample=sample,
    )


def build_report(
    conn,
    season: int,
    league_id: int,
    detailed: bool = False,
    sample_limit: int = 25,
) -> DataCompletenessReport:
    fixture_query = """
        SELECT fixture_id, date
        FROM fixtures_historical
        WHERE season = %s AND league_id = %s
        ORDER BY date
    """
    with conn.cursor() as cur:
        cur.execute(fixture_query, (season, league_id))
        fixture_rows = cur.fetchall()

    fixture_ids = [row[0] for row in fixture_rows]
    fixture_dates = [row[1] for row in fixture_rows if row[1] is not None]

    expected_fixtures = EXPECTED_FIXTURES_BY_LEAGUE.get(league_id, len(fixture_ids))
    fixture_missing = max(expected_fixtures - len(fixture_ids), 0)
    fixture_coverage = len(fixture_ids) / expected_fixtures if expected_fixtures else 0.0
    fixtures = FixtureCoverage(
        expected=expected_fixtures,
        actual=len(fixture_ids),
        coverage=round(fixture_coverage, 4),
        missing=fixture_missing,
        first_date=fixture_dates[0].isoformat() if fixture_dates else None,
        last_date=fixture_dates[-1].isoformat() if fixture_dates else None,
    )

    team_stats_query = """
        SELECT fixture_id, COUNT(*)
        FROM team_match_stats
        WHERE season = %s AND league_id = %s
        GROUP BY fixture_id
    """
    with conn.cursor() as cur:
        cur.execute(team_stats_query, (season, league_id))
        team_stats_rows = cur.fetchall()

    team_stats_by_fixture = {row[0]: int(row[1]) for row in team_stats_rows}
    team_stats_missing = [
        fixture_id
        for fixture_id in fixture_ids
        if team_stats_by_fixture.get(fixture_id, 0) < 2
    ]
    team_stats_expected = len(fixture_ids) * 2
    team_stats_actual = sum(
        min(team_stats_by_fixture.get(fixture_id, 0), 2) for fixture_id in fixture_ids
    )
    team_match_stats = _coverage_metric(
        team_stats_expected,
        team_stats_actual,
        team_stats_missing if detailed else [],
        sample_limit,
    )

    lineups_query = """
        SELECT l.fixture_id, l.team_id
        FROM lineups_historical l
        JOIN fixtures_historical f ON f.fixture_id = l.fixture_id
        WHERE f.season = %s AND f.league_id = %s
        GROUP BY l.fixture_id, l.team_id
    """
    with conn.cursor() as cur:
        cur.execute(lineups_query, (season, league_id))
        lineup_rows = cur.fetchall()

    lineup_pairs = {}
    for fixture_id, team_id in lineup_rows:
        lineup_pairs.setdefault(fixture_id, set()).add(team_id)
    lineup_missing = [
        fixture_id
        for fixture_id in fixture_ids
        if len(lineup_pairs.get(fixture_id, set())) < 2
    ]
    lineup_expected = len(fixture_ids) * 2
    lineup_actual = sum(
        min(len(lineup_pairs.get(fixture_id, set())), 2) for fixture_id in fixture_ids
    )
    lineups = _coverage_metric(
        lineup_expected,
        lineup_actual,
        lineup_missing if detailed else [],
        sample_limit,
    )

    player_stats_query = """
        SELECT DISTINCT player_id
        FROM player_season_stats
        WHERE season = %s AND league_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(player_stats_query, (season, league_id))
        player_stats_rows = cur.fetchall()
    player_ids = {int(row[0]) for row in player_stats_rows}

    market_values_query = """
        SELECT DISTINCT pm.player_id
        FROM player_market_values pm
        JOIN player_season_stats ps ON ps.player_id = pm.player_id
        WHERE ps.season = %s
          AND ps.league_id = %s
          AND pm.valuation_date BETWEEN %s AND %s
    """
    if fixture_dates:
        start_date = fixture_dates[0].date()
        end_date = fixture_dates[-1].date()
    else:
        start_date = datetime(season, 1, 1).date()
        end_date = datetime(season, 12, 31).date()
    with conn.cursor() as cur:
        cur.execute(market_values_query, (season, league_id, start_date, end_date))
        market_rows = cur.fetchall()
    market_ids = {int(row[0]) for row in market_rows}

    missing_market_ids = sorted(player_ids - market_ids)
    market_coverage = len(market_ids) / len(player_ids) if player_ids else 0.0
    player_market_values = PlayerMarketCoverage(
        player_stats_count=len(player_ids),
        market_values_count=len(market_ids),
        coverage=round(market_coverage, 4),
        missing=max(len(player_ids) - len(market_ids), 0),
        missing_sample=missing_market_ids[:sample_limit] if detailed else [],
    )

    odds_query = """
        SELECT o.fixture_id, COUNT(DISTINCT o.selection_key)
        FROM odds_snapshots o
        JOIN fixtures_historical f ON f.fixture_id = o.fixture_id
        WHERE f.season = %s
          AND f.league_id = %s
          AND o.market_key = '1X2'
          AND o.selection_key IN ('HOME', 'DRAW', 'AWAY')
        GROUP BY o.fixture_id
    """
    with conn.cursor() as cur:
        cur.execute(odds_query, (season, league_id))
        odds_rows = cur.fetchall()
    odds_by_fixture = {row[0]: int(row[1]) for row in odds_rows}
    odds_missing = [
        fixture_id
        for fixture_id in fixture_ids
        if odds_by_fixture.get(fixture_id, 0) < 3
    ]
    odds_expected = len(fixture_ids)
    odds_actual = sum(
        1 for fixture_id in fixture_ids if odds_by_fixture.get(fixture_id, 0) >= 3
    )
    odds = _coverage_metric(
        odds_expected,
        odds_actual,
        odds_missing if detailed else [],
        sample_limit,
    )

    return DataCompletenessReport(
        season=season,
        league_id=league_id,
        generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        fixtures=fixtures,
        team_match_stats=team_match_stats,
        lineups=lineups,
        player_market_values=player_market_values,
        odds=odds,
    )
