import json
from typing import Any, Optional

from src.database.config import get_connection

PER90_METRICS = (
    "xg",
    "xa",
    "key_passes",
    "progressive_passes",
    "tackles",
    "interceptions",
)


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


def _per90(value: Optional[float], minutes: Optional[int]) -> Optional[float]:
    if value is None or not minutes or minutes <= 0:
        return None
    return round(value / (minutes / 90.0), 3)


def _sum_optional(first: Optional[float], second: Optional[float]) -> Optional[float]:
    if first is None and second is None:
        return None
    return round((first or 0.0) + (second or 0.0), 3)


def _delta(first: Optional[float], second: Optional[float]) -> Optional[float]:
    if first is None or second is None:
        return None
    return round(first - second, 3)


def _fetch_player_stats(conn, player_id: int, season: int) -> Optional[dict[str, Any]]:
    query = """
        SELECT player_id, team_id, season, league_id, minutes, position,
               xg, xa, key_passes, progressive_passes, tackles, interceptions
        FROM player_season_stats
        WHERE player_id = %s AND season = %s
        ORDER BY minutes DESC NULLS LAST
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query, (player_id, season))
        row = cur.fetchone()

    if not row:
        return None

    columns = [
        "player_id",
        "team_id",
        "season",
        "league_id",
        "minutes",
        "position",
        "xg",
        "xa",
        "key_passes",
        "progressive_passes",
        "tackles",
        "interceptions",
    ]
    data = dict(zip(columns, row))
    data["minutes"] = _safe_int(data.get("minutes"))
    for key in PER90_METRICS:
        data[key] = _safe_float(data.get(key))
    return data


def _fetch_replacement_stats(
    conn,
    team_id: int,
    position: Optional[str],
    season: int,
    league_id: int,
    player_id: int,
) -> Optional[dict[str, Any]]:
    base_columns = (
        "player_id, team_id, season, league_id, minutes, position, "
        "xg, xa, key_passes, progressive_passes, tackles, interceptions"
    )
    params = [team_id, season, league_id, player_id]
    query = f"""
        SELECT {base_columns}
        FROM player_season_stats
        WHERE team_id = %s
          AND season = %s
          AND league_id = %s
          AND player_id != %s
    """
    if position:
        query += " AND position = %s"
        params.append(position)
    query += " ORDER BY minutes DESC NULLS LAST LIMIT 1"

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()

    if not row and position:
        fallback_query = f"""
            SELECT {base_columns}
            FROM player_season_stats
            WHERE season = %s
              AND league_id = %s
              AND player_id != %s
              AND position = %s
            ORDER BY minutes DESC NULLS LAST
            LIMIT 1
        """
        with conn.cursor() as cur:
            cur.execute(fallback_query, (season, league_id, player_id, position))
            row = cur.fetchone()

    if not row:
        return None

    columns = [
        "player_id",
        "team_id",
        "season",
        "league_id",
        "minutes",
        "position",
        "xg",
        "xa",
        "key_passes",
        "progressive_passes",
        "tackles",
        "interceptions",
    ]
    data = dict(zip(columns, row))
    data["minutes"] = _safe_int(data.get("minutes"))
    for key in PER90_METRICS:
        data[key] = _safe_float(data.get(key))
    return data


def compute_player_impact_from_stats(
    player_stats: dict[str, Any],
    replacement_stats: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    minutes = _safe_int(player_stats.get("minutes"))
    per90 = {
        "xg_per90": _per90(_safe_float(player_stats.get("xg")), minutes),
        "xa_per90": _per90(_safe_float(player_stats.get("xa")), minutes),
        "key_passes_per90": _per90(
            _safe_float(player_stats.get("key_passes")), minutes
        ),
        "progressive_passes_per90": _per90(
            _safe_float(player_stats.get("progressive_passes")), minutes
        ),
        "tackles_per90": _per90(_safe_float(player_stats.get("tackles")), minutes),
        "interceptions_per90": _per90(
            _safe_float(player_stats.get("interceptions")), minutes
        ),
    }

    offensive_impact = _sum_optional(per90["xg_per90"], per90["xa_per90"])
    defensive_impact = _sum_optional(
        per90["tackles_per90"], per90["interceptions_per90"]
    )

    replacement_delta: dict[str, Optional[float]] = {}
    replacement_player_id = None
    if replacement_stats:
        replacement_player_id = replacement_stats.get("player_id")
        replacement_minutes = _safe_int(replacement_stats.get("minutes"))
        replacement_per90 = {
            "xg_per90": _per90(_safe_float(replacement_stats.get("xg")), replacement_minutes),
            "xa_per90": _per90(_safe_float(replacement_stats.get("xa")), replacement_minutes),
            "key_passes_per90": _per90(
                _safe_float(replacement_stats.get("key_passes")), replacement_minutes
            ),
            "progressive_passes_per90": _per90(
                _safe_float(replacement_stats.get("progressive_passes")),
                replacement_minutes,
            ),
            "tackles_per90": _per90(
                _safe_float(replacement_stats.get("tackles")), replacement_minutes
            ),
            "interceptions_per90": _per90(
                _safe_float(replacement_stats.get("interceptions")), replacement_minutes
            ),
        }
        replacement_offensive = _sum_optional(
            replacement_per90["xg_per90"], replacement_per90["xa_per90"]
        )
        replacement_defensive = _sum_optional(
            replacement_per90["tackles_per90"],
            replacement_per90["interceptions_per90"],
        )

        replacement_delta = {
            "xg_per90": _delta(per90["xg_per90"], replacement_per90["xg_per90"]),
            "xa_per90": _delta(per90["xa_per90"], replacement_per90["xa_per90"]),
            "key_passes_per90": _delta(
                per90["key_passes_per90"],
                replacement_per90["key_passes_per90"],
            ),
            "progressive_passes_per90": _delta(
                per90["progressive_passes_per90"],
                replacement_per90["progressive_passes_per90"],
            ),
            "tackles_per90": _delta(
                per90["tackles_per90"], replacement_per90["tackles_per90"]
            ),
            "interceptions_per90": _delta(
                per90["interceptions_per90"],
                replacement_per90["interceptions_per90"],
            ),
            "offensive_impact": _delta(offensive_impact, replacement_offensive),
            "defensive_impact": _delta(defensive_impact, replacement_defensive),
        }

    return {
        "minutes": minutes,
        "xg_per90": per90["xg_per90"],
        "xa_per90": per90["xa_per90"],
        "key_passes_per90": per90["key_passes_per90"],
        "progressive_passes_per90": per90["progressive_passes_per90"],
        "tackles_per90": per90["tackles_per90"],
        "interceptions_per90": per90["interceptions_per90"],
        "offensive_impact": offensive_impact,
        "defensive_impact": defensive_impact,
        "replacement_player_id": replacement_player_id,
        "replacement_delta": replacement_delta,
    }


def _store_player_impact(conn, player_stats: dict[str, Any], impact: dict[str, Any]) -> None:
    query = """
        INSERT INTO player_impact_metrics (
            player_id, season, league_id, minutes,
            xg_per90, xa_per90, key_passes_per90, progressive_passes_per90,
            tackles_per90, interceptions_per90, offensive_impact, defensive_impact,
            replacement_player_id, replacement_delta, data_source
        )
        VALUES (
            %(player_id)s, %(season)s, %(league_id)s, %(minutes)s,
            %(xg_per90)s, %(xa_per90)s, %(key_passes_per90)s, %(progressive_passes_per90)s,
            %(tackles_per90)s, %(interceptions_per90)s, %(offensive_impact)s, %(defensive_impact)s,
            %(replacement_player_id)s, %(replacement_delta)s, %(data_source)s
        )
        ON CONFLICT (player_id, season, league_id) DO UPDATE SET
            minutes = EXCLUDED.minutes,
            xg_per90 = EXCLUDED.xg_per90,
            xa_per90 = EXCLUDED.xa_per90,
            key_passes_per90 = EXCLUDED.key_passes_per90,
            progressive_passes_per90 = EXCLUDED.progressive_passes_per90,
            tackles_per90 = EXCLUDED.tackles_per90,
            interceptions_per90 = EXCLUDED.interceptions_per90,
            offensive_impact = EXCLUDED.offensive_impact,
            defensive_impact = EXCLUDED.defensive_impact,
            replacement_player_id = EXCLUDED.replacement_player_id,
            replacement_delta = EXCLUDED.replacement_delta,
            data_source = EXCLUDED.data_source,
            updated_at = NOW()
    """
    payload = {
        "player_id": player_stats["player_id"],
        "season": player_stats["season"],
        "league_id": player_stats["league_id"],
        "minutes": impact["minutes"],
        "xg_per90": impact["xg_per90"],
        "xa_per90": impact["xa_per90"],
        "key_passes_per90": impact["key_passes_per90"],
        "progressive_passes_per90": impact["progressive_passes_per90"],
        "tackles_per90": impact["tackles_per90"],
        "interceptions_per90": impact["interceptions_per90"],
        "offensive_impact": impact["offensive_impact"],
        "defensive_impact": impact["defensive_impact"],
        "replacement_player_id": impact["replacement_player_id"],
        "replacement_delta": json.dumps(impact["replacement_delta"]),
        "data_source": "derived",
    }
    with conn.cursor() as cur:
        cur.execute(query, payload)


def calculate_player_impact(player_id: int, season: int) -> Optional[dict[str, Any]]:
    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to database.")
        return None

    try:
        player_stats = _fetch_player_stats(conn, player_id, season)
        if not player_stats:
            print(f"⚠️  No stats found for player_id={player_id} season={season}.")
            return None

        replacement_stats = _fetch_replacement_stats(
            conn,
            team_id=player_stats["team_id"],
            position=player_stats.get("position"),
            season=player_stats["season"],
            league_id=player_stats["league_id"],
            player_id=player_stats["player_id"],
        )

        impact = compute_player_impact_from_stats(player_stats, replacement_stats)
        _store_player_impact(conn, player_stats, impact)
        conn.commit()
        return impact
    except Exception as exc:
        conn.rollback()
        print(f"❌ Failed to compute player impact: {exc}")
        return None
    finally:
        conn.close()
