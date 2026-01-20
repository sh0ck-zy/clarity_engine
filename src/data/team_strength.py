from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, Optional

from src.database.config import get_connection


STARTING_KEYWORDS = ("starting", "start", "xi", "first")
BENCH_KEYWORDS = ("bench", "sub", "substitute", "reserve")


def _normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, datetime.min.time())


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _average(values: Iterable[float]) -> Optional[float]:
    values_list = list(values)
    if not values_list:
        return None
    return round(sum(values_list) / len(values_list), 3)


def _fetch_fixture_context(conn, fixture_id: str) -> Optional[dict[str, Any]]:
    query = """
        SELECT fixture_id, season, league_id, date
        FROM fixtures_historical
        WHERE fixture_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (fixture_id,))
        row = cur.fetchone()
    if not row:
        return None
    return {
        "fixture_id": row[0],
        "season": int(row[1]),
        "league_id": int(row[2]),
        "fixture_date": _normalize_datetime(row[3]),
    }


def _fetch_lineup_rows(conn, fixture_id: str, team_id: int) -> list[tuple[str, Any]]:
    query = """
        SELECT lineup_type, players
        FROM lineups_historical
        WHERE fixture_id = %s AND team_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (fixture_id, team_id))
        return cur.fetchall()


def _fetch_recent_lineup_fixture(
    conn, team_id: int, fixture_date: datetime
) -> Optional[str]:
    query = """
        SELECT f.fixture_id
        FROM lineups_historical l
        JOIN fixtures_historical f ON f.fixture_id = l.fixture_id
        WHERE l.team_id = %s
          AND f.date < %s
        ORDER BY f.date DESC
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query, (team_id, fixture_date))
        row = cur.fetchone()
    if not row:
        return None
    return row[0]


def _load_players(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(raw, dict):
        if "players" in raw and isinstance(raw["players"], list):
            return raw["players"]
        return list(raw.values())
    if isinstance(raw, list):
        return raw
    return []


def _extract_player_id(player: Any) -> Optional[int]:
    if isinstance(player, int):
        return player
    if isinstance(player, str):
        return _safe_int(player)
    if isinstance(player, dict):
        for key in ("player_id", "playerId", "id"):
            if key in player:
                return _safe_int(player.get(key))
    return None


def _extract_rating(player: Any) -> Optional[float]:
    if isinstance(player, dict):
        for key in ("rating", "player_rating", "avg_rating", "match_rating"):
            if key in player:
                return _safe_float(player.get(key))
    return None


def _lineup_bucket(lineup_type: Optional[str]) -> str:
    if not lineup_type:
        return "unknown"
    normalized = lineup_type.strip().lower()
    if any(keyword in normalized for keyword in STARTING_KEYWORDS):
        return "starting"
    if any(keyword in normalized for keyword in BENCH_KEYWORDS):
        return "bench"
    return "unknown"


def _split_lineup_entries(entries: list[tuple[str, Any]]) -> tuple[list[Any], list[Any]]:
    starting: list[Any] = []
    bench: list[Any] = []
    unknown_entries: list[list[Any]] = []
    for lineup_type, players in entries:
        bucket = _lineup_bucket(lineup_type)
        parsed_players = _load_players(players)
        if bucket == "starting":
            starting.extend(parsed_players)
        elif bucket == "bench":
            bench.extend(parsed_players)
        else:
            unknown_entries.append(parsed_players)
    if not starting and unknown_entries:
        starting = unknown_entries[0]
        for extra in unknown_entries[1:]:
            bench.extend(extra)
    return starting, bench


def _fetch_market_values(
    conn, player_ids: list[int], fixture_date: datetime
) -> dict[int, Optional[float]]:
    if not player_ids:
        return {}
    query = """
        SELECT DISTINCT ON (player_id)
               player_id,
               market_value_eur
        FROM player_market_values
        WHERE player_id = ANY(%s)
          AND valuation_date <= %s
        ORDER BY player_id, valuation_date DESC
    """
    with conn.cursor() as cur:
        cur.execute(query, (player_ids, fixture_date.date()))
        rows = cur.fetchall()
    return {int(row[0]): _safe_float(row[1]) for row in rows}


def _fetch_player_roles(
    conn,
    player_ids: list[int],
    season: int,
    league_id: int,
) -> dict[int, dict[str, Optional[float]]]:
    if not player_ids:
        return {}
    query = """
        SELECT DISTINCT ON (ps.player_id)
               ps.player_id,
               ps.position,
               COALESCE(
                   im.xg_per90,
                   CASE WHEN ps.minutes > 0 THEN ps.xg / (ps.minutes / 90.0) END
               ) AS xg_per90,
               COALESCE(
                   im.tackles_per90,
                   CASE WHEN ps.minutes > 0 THEN ps.tackles / (ps.minutes / 90.0) END
               ) AS tackles_per90,
               COALESCE(
                   im.interceptions_per90,
                   CASE WHEN ps.minutes > 0 THEN ps.interceptions / (ps.minutes / 90.0) END
               ) AS interceptions_per90
        FROM player_season_stats ps
        LEFT JOIN player_impact_metrics im
          ON im.player_id = ps.player_id
         AND im.season = ps.season
         AND im.league_id = ps.league_id
        WHERE ps.player_id = ANY(%s)
          AND ps.season = %s
          AND ps.league_id = %s
        ORDER BY ps.player_id, ps.minutes DESC NULLS LAST
    """
    with conn.cursor() as cur:
        cur.execute(query, (player_ids, season, league_id))
        rows = cur.fetchall()
    roles: dict[int, dict[str, Optional[float]]] = {}
    for player_id, position, xg_per90, tackles_per90, interceptions_per90 in rows:
        roles[int(player_id)] = {
            "position": position,
            "xg_per90": _safe_float(xg_per90),
            "tackles_per90": _safe_float(tackles_per90),
            "interceptions_per90": _safe_float(interceptions_per90),
        }
    return roles


def _position_group(position: Optional[str]) -> Optional[str]:
    if not position:
        return None
    normalized = position.strip().upper()
    if any(key in normalized for key in ("FW", "FWD", "ST", "CF", "LW", "RW", "ATT")):
        return "attack"
    if any(key in normalized for key in ("DF", "DEF", "CB", "LB", "RB", "WB", "FB")):
        return "defense"
    return None


def _sum_metric(values: Iterable[Optional[float]]) -> Optional[float]:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers), 3)


def _store_lineup_strength(
    conn,
    fixture_id: str,
    team_id: int,
    metrics: dict[str, Optional[float]],
) -> None:
    query = """
        INSERT INTO lineup_strength_metrics (
            fixture_id,
            team_id,
            avg_player_rating,
            total_market_value,
            offensive_strength,
            defensive_strength,
            bench_strength,
            data_source
        )
        VALUES (
            %(fixture_id)s,
            %(team_id)s,
            %(avg_player_rating)s,
            %(total_market_value)s,
            %(offensive_strength)s,
            %(defensive_strength)s,
            %(bench_strength)s,
            %(data_source)s
        )
        ON CONFLICT (fixture_id, team_id) DO UPDATE SET
            avg_player_rating = EXCLUDED.avg_player_rating,
            total_market_value = EXCLUDED.total_market_value,
            offensive_strength = EXCLUDED.offensive_strength,
            defensive_strength = EXCLUDED.defensive_strength,
            bench_strength = EXCLUDED.bench_strength,
            data_source = EXCLUDED.data_source,
            updated_at = NOW()
    """
    payload = {
        "fixture_id": fixture_id,
        "team_id": team_id,
        "avg_player_rating": metrics["avg_player_rating"],
        "total_market_value": metrics["total_market_value"],
        "offensive_strength": metrics["offensive_strength"],
        "defensive_strength": metrics["defensive_strength"],
        "bench_strength": metrics["bench_strength"],
        "data_source": "derived",
    }
    with conn.cursor() as cur:
        cur.execute(query, payload)


def calculate_lineup_strength(fixture_id: str, team_id: int) -> Optional[dict[str, Any]]:
    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to database.")
        return None

    try:
        context = _fetch_fixture_context(conn, fixture_id)
        if not context:
            raise ValueError(f"Unknown fixture_id {fixture_id}")

        lineup_rows = _fetch_lineup_rows(conn, fixture_id, team_id)
        if not lineup_rows:
            recent_fixture = _fetch_recent_lineup_fixture(
                conn, team_id, context["fixture_date"]
            )
            if recent_fixture:
                lineup_rows = _fetch_lineup_rows(conn, recent_fixture, team_id)

        if not lineup_rows:
            print(f"⚠️  No lineup data for fixture_id={fixture_id} team_id={team_id}.")
            return None

        starting_players, bench_players = _split_lineup_entries(lineup_rows)
        starting_ids = [pid for pid in (_extract_player_id(p) for p in starting_players) if pid]
        bench_ids = [pid for pid in (_extract_player_id(p) for p in bench_players) if pid]

        if not starting_ids:
            print(
                f"⚠️  No starting XI player IDs for fixture_id={fixture_id} team_id={team_id}."
            )
            return None

        starting_ratings = [
            rating for rating in (_extract_rating(p) for p in starting_players) if rating is not None
        ]
        bench_ratings = [
            rating for rating in (_extract_rating(p) for p in bench_players) if rating is not None
        ]

        market_values = _fetch_market_values(conn, starting_ids, context["fixture_date"])
        total_market_value = _sum_metric(market_values.get(pid) for pid in starting_ids)

        roles = _fetch_player_roles(
            conn,
            starting_ids,
            season=context["season"],
            league_id=context["league_id"],
        )

        offensive_values: list[Optional[float]] = []
        defensive_values: list[Optional[float]] = []
        for player_id in starting_ids:
            role = roles.get(player_id, {})
            group = _position_group(role.get("position"))
            if group == "attack":
                offensive_values.append(role.get("xg_per90"))
            elif group == "defense":
                defensive_values.append(role.get("tackles_per90"))
                defensive_values.append(role.get("interceptions_per90"))

        metrics = {
            "avg_player_rating": _average(starting_ratings),
            "total_market_value": total_market_value,
            "offensive_strength": _sum_metric(offensive_values),
            "defensive_strength": _sum_metric(defensive_values),
            "bench_strength": _average(bench_ratings),
        }

        _store_lineup_strength(conn, fixture_id, team_id, metrics)
        conn.commit()
        return metrics
    except Exception as exc:
        conn.rollback()
        print(f"❌ Failed to compute lineup strength: {exc}")
        return None
    finally:
        conn.close()
