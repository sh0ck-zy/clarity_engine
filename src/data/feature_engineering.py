from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional

from database.config import get_connection


@dataclass(frozen=True)
class FixtureContext:
    fixture_id: str
    season: int
    league_id: int
    fixture_date: datetime
    home_team_id: int
    away_team_id: int


def _normalize_datetime(value: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.min.time())


def _fetch_fixture_context(conn, fixture_id: str) -> Optional[FixtureContext]:
    query = """
        SELECT fixture_id, season, league_id, date, home_team_id, away_team_id
        FROM fixtures_historical
        WHERE fixture_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (fixture_id,))
        row = cur.fetchone()
    if not row:
        return None
    return FixtureContext(
        fixture_id=row[0],
        season=row[1],
        league_id=row[2],
        fixture_date=_normalize_datetime(row[3]),
        home_team_id=row[4],
        away_team_id=row[5],
    )


def _fetch_last_match_date(conn, team_id: int, fixture_date: datetime) -> Optional[datetime]:
    query = """
        SELECT date
        FROM fixtures_historical
        WHERE date < %s
          AND (home_team_id = %s OR away_team_id = %s)
        ORDER BY date DESC
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query, (fixture_date, team_id, team_id))
        row = cur.fetchone()
    if not row:
        return None
    return _normalize_datetime(row[0])


def _count_recent_matches(
    conn,
    team_id: int,
    fixture_date: datetime,
    window_days: int,
) -> int:
    window_start = fixture_date - timedelta(days=window_days)
    query = """
        SELECT COUNT(*)
        FROM fixtures_historical
        WHERE date < %s
          AND date >= %s
          AND (home_team_id = %s OR away_team_id = %s)
    """
    with conn.cursor() as cur:
        cur.execute(query, (fixture_date, window_start, team_id, team_id))
        row = cur.fetchone()
    return int(row[0]) if row else 0


def _calculate_rest_days(last_match_date: Optional[datetime], fixture_date: datetime) -> Optional[int]:
    if last_match_date is None:
        return None
    delta = fixture_date - last_match_date
    return int(delta.days)


def _upsert_features(
    conn,
    fixture_context: FixtureContext,
    features: Dict[str, Optional[float]],
    data_source: str,
) -> None:
    query = """
        INSERT INTO match_features (
            fixture_id,
            season,
            league_id,
            feature_key,
            feature_value,
            data_source
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (fixture_id, feature_key) DO UPDATE SET
            feature_value = EXCLUDED.feature_value,
            updated_at = NOW()
    """
    rows = [
        (
            fixture_context.fixture_id,
            fixture_context.season,
            fixture_context.league_id,
            key,
            value,
            data_source,
        )
        for key, value in features.items()
    ]
    with conn.cursor() as cur:
        cur.executemany(query, rows)


def derive_rest_features(fixture_id: str, conn=None) -> Dict[str, Optional[float]]:
    managed_connection = False
    if conn is None:
        conn = get_connection()
        managed_connection = True
    if conn is None:
        raise RuntimeError("Database connection unavailable")

    try:
        context = _fetch_fixture_context(conn, fixture_id)
        if context is None:
            raise ValueError(f"Unknown fixture_id {fixture_id}")

        home_last_match = _fetch_last_match_date(conn, context.home_team_id, context.fixture_date)
        away_last_match = _fetch_last_match_date(conn, context.away_team_id, context.fixture_date)

        features: Dict[str, Optional[float]] = {
            "home_rest_days": _calculate_rest_days(home_last_match, context.fixture_date),
            "away_rest_days": _calculate_rest_days(away_last_match, context.fixture_date),
            "home_matches_last_7d": _count_recent_matches(
                conn, context.home_team_id, context.fixture_date, 7
            ),
            "away_matches_last_7d": _count_recent_matches(
                conn, context.away_team_id, context.fixture_date, 7
            ),
            "home_matches_last_14d": _count_recent_matches(
                conn, context.home_team_id, context.fixture_date, 14
            ),
            "away_matches_last_14d": _count_recent_matches(
                conn, context.away_team_id, context.fixture_date, 14
            ),
        }

        _upsert_features(conn, context, features, data_source="feature_engineering")
        conn.commit()
        return features
    except Exception:
        conn.rollback()
        raise
    finally:
        if managed_connection:
            conn.close()
