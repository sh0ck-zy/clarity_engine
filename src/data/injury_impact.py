from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from src.database.config import get_connection


DECAY_FACTOR = 0.7


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


def _per90(value: Optional[float], minutes: Optional[int]) -> Optional[float]:
    if value is None or not minutes or minutes <= 0:
        return None
    return round(value / (minutes / 90.0), 3)


def _position_group(position: Optional[str]) -> Optional[str]:
    if not position:
        return None
    normalized = position.strip().upper()
    if any(key in normalized for key in ("FW", "FWD", "ST", "CF", "LW", "RW", "ATT")):
        return "attack"
    if any(key in normalized for key in ("DF", "DEF", "CB", "LB", "RB", "WB", "FB")):
        return "defense"
    return None


def _sum_optional(first: Optional[float], second: Optional[float]) -> Optional[float]:
    if first is None and second is None:
        return None
    return round((first or 0.0) + (second or 0.0), 3)


def _diminishing_sum(values: Iterable[Optional[float]], decay: float = DECAY_FACTOR) -> Optional[float]:
    cleaned = [value for value in values if value is not None]
    if not cleaned:
        return None
    ordered = sorted(cleaned, reverse=True)
    total = 0.0
    for index, value in enumerate(ordered):
        total += value * (decay ** index)
    return round(total, 3)


def _fetch_fixture_context(conn, fixture_id: str) -> Optional[dict[str, Any]]:
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
    return {
        "fixture_id": row[0],
        "season": int(row[1]),
        "league_id": int(row[2]),
        "fixture_date": _normalize_datetime(row[3]),
        "home_team_id": int(row[4]),
        "away_team_id": int(row[5]),
    }


def _fetch_team_baseline(conn, fixture_id: str, team_id: int) -> dict[str, Optional[float]]:
    query = """
        SELECT xg, xga
        FROM team_match_stats
        WHERE fixture_id = %s AND team_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (fixture_id, team_id))
        row = cur.fetchone()
    if not row:
        return {"xg": None, "xga": None}
    return {"xg": _safe_float(row[0]), "xga": _safe_float(row[1])}


def _fetch_injured_players(
    conn,
    fixture_date: datetime,
    season: int,
    league_id: int,
    team_ids: list[int],
) -> list[dict[str, Any]]:
    query = """
        SELECT DISTINCT ON (i.player_id)
               i.player_id,
               ps.team_id,
               ps.position,
               ps.minutes,
               ps.xg,
               ps.xa,
               ps.tackles,
               ps.interceptions,
               im.offensive_impact,
               im.defensive_impact
        FROM injuries_historical i
        JOIN player_season_stats ps
          ON ps.player_id = i.player_id
         AND ps.season = %s
         AND ps.league_id = %s
        LEFT JOIN player_impact_metrics im
          ON im.player_id = i.player_id
         AND im.season = %s
         AND im.league_id = %s
        WHERE i.valid_at < %s
          AND ps.team_id = ANY(%s)
        ORDER BY i.player_id, i.valid_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(query, (season, league_id, season, league_id, fixture_date, team_ids))
        rows = cur.fetchall()

    injuries: list[dict[str, Any]] = []
    for row in rows:
        injuries.append(
            {
                "player_id": _safe_int(row[0]),
                "team_id": _safe_int(row[1]),
                "position": row[2],
                "minutes": _safe_int(row[3]),
                "xg": _safe_float(row[4]),
                "xa": _safe_float(row[5]),
                "tackles": _safe_float(row[6]),
                "interceptions": _safe_float(row[7]),
                "offensive_impact": _safe_float(row[8]),
                "defensive_impact": _safe_float(row[9]),
            }
        )
    return injuries


def _derive_offensive_impact(injury: dict[str, Any]) -> Optional[float]:
    if injury.get("offensive_impact") is not None:
        return injury["offensive_impact"]
    minutes = injury.get("minutes")
    xg_per90 = _per90(injury.get("xg"), minutes)
    xa_per90 = _per90(injury.get("xa"), minutes)
    return _sum_optional(xg_per90, xa_per90)


def _derive_defensive_impact(injury: dict[str, Any]) -> Optional[float]:
    if injury.get("defensive_impact") is not None:
        return injury["defensive_impact"]
    minutes = injury.get("minutes")
    tackles_per90 = _per90(injury.get("tackles"), minutes)
    interceptions_per90 = _per90(injury.get("interceptions"), minutes)
    return _sum_optional(tackles_per90, interceptions_per90)


def _store_injury_impact(
    conn,
    fixture_id: str,
    team_id: int,
    metrics: dict[str, Optional[float]],
) -> None:
    query = """
        INSERT INTO injury_impact_metrics (
            fixture_id,
            team_id,
            offensive_impact,
            defensive_impact,
            adjusted_xg,
            adjusted_xga,
            data_source
        )
        VALUES (
            %(fixture_id)s,
            %(team_id)s,
            %(offensive_impact)s,
            %(defensive_impact)s,
            %(adjusted_xg)s,
            %(adjusted_xga)s,
            %(data_source)s
        )
        ON CONFLICT (fixture_id, team_id) DO UPDATE SET
            offensive_impact = EXCLUDED.offensive_impact,
            defensive_impact = EXCLUDED.defensive_impact,
            adjusted_xg = EXCLUDED.adjusted_xg,
            adjusted_xga = EXCLUDED.adjusted_xga,
            data_source = EXCLUDED.data_source,
            updated_at = NOW()
    """
    payload = {
        "fixture_id": fixture_id,
        "team_id": team_id,
        "offensive_impact": metrics["offensive_impact"],
        "defensive_impact": metrics["defensive_impact"],
        "adjusted_xg": metrics["adjusted_xg"],
        "adjusted_xga": metrics["adjusted_xga"],
        "data_source": "derived",
    }
    with conn.cursor() as cur:
        cur.execute(query, payload)


def calculate_injury_impact(fixture_id: str) -> Optional[dict[int, dict[str, Any]]]:
    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to database.")
        return None

    try:
        context = _fetch_fixture_context(conn, fixture_id)
        if not context:
            raise ValueError(f"Unknown fixture_id {fixture_id}")

        team_ids = [context["home_team_id"], context["away_team_id"]]
        injuries = _fetch_injured_players(
            conn,
            fixture_date=context["fixture_date"],
            season=context["season"],
            league_id=context["league_id"],
            team_ids=team_ids,
        )

        injuries_by_team: dict[int, list[dict[str, Any]]] = {team_id: [] for team_id in team_ids}
        for injury in injuries:
            team_id = injury.get("team_id")
            if team_id in injuries_by_team:
                injuries_by_team[team_id].append(injury)

        results: dict[int, dict[str, Any]] = {}
        for team_id in team_ids:
            offensive_values: list[Optional[float]] = []
            defensive_values: list[Optional[float]] = []
            for injury in injuries_by_team.get(team_id, []):
                group = _position_group(injury.get("position"))
                if group == "attack":
                    offensive_values.append(_derive_offensive_impact(injury))
                elif group == "defense":
                    defensive_values.append(_derive_defensive_impact(injury))

            offensive_impact = _diminishing_sum(offensive_values)
            defensive_impact = _diminishing_sum(defensive_values)
            baseline = _fetch_team_baseline(conn, fixture_id, team_id)
            adjusted_xg = (
                None
                if baseline["xg"] is None
                else round(baseline["xg"] - (offensive_impact or 0.0), 3)
            )
            adjusted_xga = (
                None
                if baseline["xga"] is None
                else round(baseline["xga"] + (defensive_impact or 0.0), 3)
            )

            metrics = {
                "offensive_impact": offensive_impact,
                "defensive_impact": defensive_impact,
                "adjusted_xg": adjusted_xg,
                "adjusted_xga": adjusted_xga,
            }
            _store_injury_impact(conn, fixture_id, team_id, metrics)
            results[team_id] = metrics

        conn.commit()
        return results
    except Exception as exc:
        conn.rollback()
        print(f"❌ Failed to compute injury impact: {exc}")
        return None
    finally:
        conn.close()
