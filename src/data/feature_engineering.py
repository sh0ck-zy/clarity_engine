from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional

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


def _fetch_recent_team_matches(
    conn,
    team_id: int,
    fixture_date: datetime,
    limit: int = 5,
) -> list[tuple]:
    query = """
        SELECT f.fixture_id,
               f.date,
               f.home_team_id,
               f.away_team_id,
               f.home_score,
               f.away_score,
               t.xg,
               t.xga
        FROM fixtures_historical f
        LEFT JOIN team_match_stats t
          ON t.fixture_id = f.fixture_id
         AND t.team_id = %s
        WHERE f.date < %s
          AND (f.home_team_id = %s OR f.away_team_id = %s)
          AND f.home_score IS NOT NULL
          AND f.away_score IS NOT NULL
        ORDER BY f.date DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (team_id, fixture_date, team_id, team_id, limit))
        return cur.fetchall()


def _calculate_form_totals(rows: Iterable[tuple], team_id: int) -> Dict[str, Optional[float]]:
    points = 0
    goals_for = 0
    goals_against = 0
    clean_sheets = 0
    xg_total = 0.0
    xga_total = 0.0
    xg_count = 0
    xga_count = 0

    for row in rows:
        home_team_id = row[2]
        away_team_id = row[3]
        home_score = row[4]
        away_score = row[5]
        xg = row[6]
        xga = row[7]

        if team_id == home_team_id:
            goals_for += int(home_score)
            goals_against += int(away_score)
            if home_score > away_score:
                points += 3
            elif home_score == away_score:
                points += 1
        else:
            goals_for += int(away_score)
            goals_against += int(home_score)
            if away_score > home_score:
                points += 3
            elif away_score == home_score:
                points += 1

        if (team_id == home_team_id and away_score == 0) or (
            team_id == away_team_id and home_score == 0
        ):
            clean_sheets += 1

        if xg is not None:
            xg_total += float(xg)
            xg_count += 1
        if xga is not None:
            xga_total += float(xga)
            xga_count += 1

    return {
        "points": float(points),
        "goals_for": float(goals_for),
        "goals_against": float(goals_against),
        "xg": xg_total if xg_count > 0 else None,
        "xga": xga_total if xga_count > 0 else None,
        "clean_sheets": float(clean_sheets),
    }


def _fetch_h2h_matches(
    conn,
    home_team_id: int,
    away_team_id: int,
    fixture_date: datetime,
    limit: int = 5,
) -> list[tuple]:
    query = """
        SELECT fixture_id,
               date,
               home_team_id,
               away_team_id,
               home_score,
               away_score
        FROM fixtures_historical
        WHERE date < %s
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND (
            (home_team_id = %s AND away_team_id = %s)
            OR (home_team_id = %s AND away_team_id = %s)
          )
        ORDER BY date DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(
            query,
            (fixture_date, home_team_id, away_team_id, away_team_id, home_team_id, limit),
        )
        return cur.fetchall()


def _calculate_h2h_totals(
    rows: Iterable[tuple],
    home_team_id: int,
    away_team_id: int,
) -> Dict[str, Optional[float]]:
    home_wins = 0
    away_wins = 0
    draws = 0
    total_goals = 0
    match_count = 0

    for row in rows:
        home_id = row[2]
        away_id = row[3]
        home_score = row[4]
        away_score = row[5]
        total_goals += int(home_score) + int(away_score)
        match_count += 1

        if home_score == away_score:
            draws += 1
            continue

        winner_id = home_id if home_score > away_score else away_id
        if winner_id == home_team_id:
            home_wins += 1
        elif winner_id == away_team_id:
            away_wins += 1

    avg_goals = None
    if match_count > 0:
        avg_goals = float(total_goals) / float(match_count)

    return {
        "home_wins": float(home_wins),
        "away_wins": float(away_wins),
        "draws": float(draws),
        "avg_goals": avg_goals,
    }


def _fetch_league_positions(
    conn,
    fixture_context: FixtureContext,
) -> Dict[str, Optional[float]]:
    query = """
        WITH team_results AS (
            SELECT home_team_id AS team_id,
                   SUM(CASE WHEN home_score > away_score THEN 3
                            WHEN home_score = away_score THEN 1
                            ELSE 0 END) AS points,
                   SUM(home_score) AS goals_for,
                   SUM(away_score) AS goals_against
            FROM fixtures_historical
            WHERE season = %s
              AND league_id = %s
              AND date < %s
              AND home_score IS NOT NULL
              AND away_score IS NOT NULL
            GROUP BY home_team_id
            UNION ALL
            SELECT away_team_id AS team_id,
                   SUM(CASE WHEN away_score > home_score THEN 3
                            WHEN away_score = home_score THEN 1
                            ELSE 0 END) AS points,
                   SUM(away_score) AS goals_for,
                   SUM(home_score) AS goals_against
            FROM fixtures_historical
            WHERE season = %s
              AND league_id = %s
              AND date < %s
              AND home_score IS NOT NULL
              AND away_score IS NOT NULL
            GROUP BY away_team_id
        ),
        team_totals AS (
            SELECT team_id,
                   SUM(points) AS points,
                   SUM(goals_for) AS goals_for,
                   SUM(goals_against) AS goals_against
            FROM team_results
            GROUP BY team_id
        ),
        ranked AS (
            SELECT team_id,
                   points,
                   goals_for,
                   goals_against,
                   (goals_for - goals_against) AS goal_diff,
                   ROW_NUMBER() OVER (
                       ORDER BY points DESC,
                                (goals_for - goals_against) DESC,
                                goals_for DESC,
                                team_id
                   ) AS position
            FROM team_totals
        )
        SELECT team_id, points, position
        FROM ranked
        WHERE team_id IN (%s, %s)
    """
    params = (
        fixture_context.season,
        fixture_context.league_id,
        fixture_context.fixture_date,
        fixture_context.season,
        fixture_context.league_id,
        fixture_context.fixture_date,
        fixture_context.home_team_id,
        fixture_context.away_team_id,
    )
    results: Dict[int, Dict[str, Optional[float]]] = {}
    with conn.cursor() as cur:
        cur.execute(query, params)
        for team_id, points, position in cur.fetchall():
            results[int(team_id)] = {
                "points": float(points) if points is not None else 0.0,
                "position": float(position) if position is not None else None,
            }

    home_stats = results.get(fixture_context.home_team_id, {})
    away_stats = results.get(fixture_context.away_team_id, {})
    return {
        "home_position_before": home_stats.get("position"),
        "away_position_before": away_stats.get("position"),
        "home_points_before": home_stats.get("points"),
        "away_points_before": away_stats.get("points"),
    }


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


def derive_form_features(fixture_id: str, conn=None) -> Dict[str, Optional[float]]:
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

        home_rows = _fetch_recent_team_matches(conn, context.home_team_id, context.fixture_date, limit=5)
        away_rows = _fetch_recent_team_matches(conn, context.away_team_id, context.fixture_date, limit=5)
        home_form = _calculate_form_totals(home_rows, context.home_team_id)
        away_form = _calculate_form_totals(away_rows, context.away_team_id)

        h2h_rows = _fetch_h2h_matches(
            conn,
            context.home_team_id,
            context.away_team_id,
            context.fixture_date,
            limit=5,
        )
        h2h_form = _calculate_h2h_totals(h2h_rows, context.home_team_id, context.away_team_id)
        league_positions = _fetch_league_positions(conn, context)

        features: Dict[str, Optional[float]] = {
            "home_form_points": home_form["points"],
            "away_form_points": away_form["points"],
            "home_form_goals_for": home_form["goals_for"],
            "away_form_goals_for": away_form["goals_for"],
            "home_form_goals_against": home_form["goals_against"],
            "away_form_goals_against": away_form["goals_against"],
            "home_form_xg": home_form["xg"],
            "away_form_xg": away_form["xg"],
            "home_form_xga": home_form["xga"],
            "away_form_xga": away_form["xga"],
            "home_form_clean_sheets": home_form["clean_sheets"],
            "away_form_clean_sheets": away_form["clean_sheets"],
            "h2h_home_wins": h2h_form["home_wins"],
            "h2h_away_wins": h2h_form["away_wins"],
            "h2h_draws": h2h_form["draws"],
            "h2h_avg_goals": h2h_form["avg_goals"],
            "home_position_before": league_positions["home_position_before"],
            "away_position_before": league_positions["away_position_before"],
            "home_points_before": league_positions["home_points_before"],
            "away_points_before": league_positions["away_points_before"],
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
