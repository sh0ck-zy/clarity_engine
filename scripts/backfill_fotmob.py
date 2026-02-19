#!/usr/bin/env python3
"""
Backfill FotMob match data for the Premier League.

Usage:
    python scripts/backfill_fotmob.py                           # all finished rounds
    python scripts/backfill_fotmob.py --round 25                # specific round
    python scripts/backfill_fotmob.py --from-round 1 --to-round 10
    python scripts/backfill_fotmob.py --force                   # re-fetch existing
    python scripts/backfill_fotmob.py --dry-run                 # preview only
    python scripts/backfill_fotmob.py --delay 3                 # override rate limit
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2.extras

# Ensure src is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.config import get_connection
# Import directly to avoid broken providers __init__.py
import importlib.util as _ilu
import types as _types

# Shim the providers package so Python doesn't load the broken __init__.py
_pkg = _types.ModuleType("src.data.providers")
_pkg.__path__ = [str(SRC_PATH / "data" / "providers")]
_pkg.__package__ = "src.data.providers"
sys.modules.setdefault("src.data.providers", _pkg)

from src.data.providers.fotmob import FotMobProvider, _safe_float, _safe_int
from src.models.fotmob import FotMobMatchDetail, FotMobLeagueMatch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_fotmob")


# ------------------------------------------------------------------ #
# Schema creation
# ------------------------------------------------------------------ #

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS fotmob_matches (
    fotmob_match_id   INT PRIMARY KEY,
    league_id         INT NOT NULL DEFAULT 47,
    season            TEXT NOT NULL,
    round_number      INT,
    match_date        DATE NOT NULL,
    home_team_id      INT NOT NULL,
    home_team_name    TEXT NOT NULL,
    away_team_id      INT NOT NULL,
    away_team_name    TEXT NOT NULL,
    home_score        INT,
    away_score        INT,
    ht_home_score     INT,
    ht_away_score     INT,
    status            TEXT NOT NULL,
    venue             TEXT,
    attendance        INT,
    referee           TEXT,
    formation_home    TEXT,
    formation_away    TEXT,
    events            JSONB,
    stats             JSONB,
    home_lineup       JSONB,
    away_lineup       JSONB,
    shotmap           JSONB,
    commentary        JSONB,
    match_facts       JSONB,
    momentum          JSONB,
    home_avg_rating   DECIMAL(4,2),
    away_avg_rating   DECIMAL(4,2),
    motm_player_id    INT,
    motm_player_name  TEXT,
    raw_json          JSONB NOT NULL,
    fetched_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    clarity_fixture_id TEXT
);

CREATE TABLE IF NOT EXISTS fotmob_player_performances (
    id SERIAL PRIMARY KEY,
    fotmob_match_id   INT REFERENCES fotmob_matches(fotmob_match_id) ON DELETE CASCADE,
    player_id         INT,
    player_name       TEXT NOT NULL,
    team_id           INT,
    team_name         TEXT NOT NULL,
    is_home           BOOLEAN,
    is_starter        BOOLEAN,
    position_id       INT,
    shirt_number      TEXT,
    rating            DECIMAL(3,1),
    minutes_played    INT,
    goals             INT DEFAULT 0,
    assists           INT DEFAULT 0,
    xg                DECIMAL(5,3),
    xgot              DECIMAL(5,3),
    xa                DECIMAL(5,3),
    shots             INT,
    shots_on_target   INT,
    passes            INT,
    passes_accurate   INT,
    chances_created   INT,
    tackles           INT,
    interceptions     INT,
    defensive_actions INT,
    fantasy_score     TEXT,
    sub_in_minute     INT,
    sub_out_minute    INT,
    stats_json        JSONB,
    UNIQUE(fotmob_match_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_fpp_match ON fotmob_player_performances(fotmob_match_id);
CREATE INDEX IF NOT EXISTS idx_fpp_player ON fotmob_player_performances(player_id);
CREATE INDEX IF NOT EXISTS idx_fpp_player_name ON fotmob_player_performances(player_name);
CREATE INDEX IF NOT EXISTS idx_fpp_rating ON fotmob_player_performances(rating);
CREATE INDEX IF NOT EXISTS idx_fpp_team ON fotmob_player_performances(team_name);
CREATE INDEX IF NOT EXISTS idx_fotmob_matches_date ON fotmob_matches(match_date);
CREATE INDEX IF NOT EXISTS idx_fotmob_matches_round ON fotmob_matches(round_number);
CREATE INDEX IF NOT EXISTS idx_fotmob_matches_season ON fotmob_matches(season);
"""


def ensure_tables(conn) -> None:
    """Create FotMob tables if they don't exist."""
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLES_SQL)
    conn.commit()
    logger.info("FotMob tables ensured")


# ------------------------------------------------------------------ #
# DB operations
# ------------------------------------------------------------------ #


def match_exists(conn, match_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM fotmob_matches WHERE fotmob_match_id = %s", (match_id,)
        )
        return cur.fetchone() is not None


def upsert_match(conn, detail: FotMobMatchDetail) -> None:
    """Insert or update a match and its player performances."""
    motm = detail.match_facts.player_of_the_match if detail.match_facts else None
    motm_id = motm.get("id") if isinstance(motm, dict) else None
    motm_name_raw = motm.get("name") if isinstance(motm, dict) else None
    if isinstance(motm_name_raw, dict):
        motm_name = motm_name_raw.get("fullName") or motm_name_raw.get("name")
    else:
        motm_name = motm_name_raw

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO fotmob_matches (
                fotmob_match_id, league_id, season, round_number, match_date,
                home_team_id, home_team_name, away_team_id, away_team_name,
                home_score, away_score, ht_home_score, ht_away_score, status,
                venue, attendance, referee, formation_home, formation_away,
                events, stats, home_lineup, away_lineup, shotmap,
                match_facts, momentum,
                home_avg_rating, away_avg_rating,
                motm_player_id, motm_player_name,
                raw_json, fetched_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (fotmob_match_id) DO UPDATE SET
                season = EXCLUDED.season,
                round_number = EXCLUDED.round_number,
                match_date = EXCLUDED.match_date,
                home_score = EXCLUDED.home_score,
                away_score = EXCLUDED.away_score,
                ht_home_score = EXCLUDED.ht_home_score,
                ht_away_score = EXCLUDED.ht_away_score,
                status = EXCLUDED.status,
                venue = EXCLUDED.venue,
                attendance = EXCLUDED.attendance,
                referee = EXCLUDED.referee,
                formation_home = EXCLUDED.formation_home,
                formation_away = EXCLUDED.formation_away,
                events = EXCLUDED.events,
                stats = EXCLUDED.stats,
                home_lineup = EXCLUDED.home_lineup,
                away_lineup = EXCLUDED.away_lineup,
                shotmap = EXCLUDED.shotmap,
                match_facts = EXCLUDED.match_facts,
                momentum = EXCLUDED.momentum,
                home_avg_rating = EXCLUDED.home_avg_rating,
                away_avg_rating = EXCLUDED.away_avg_rating,
                motm_player_id = EXCLUDED.motm_player_id,
                motm_player_name = EXCLUDED.motm_player_name,
                raw_json = EXCLUDED.raw_json,
                fetched_at = EXCLUDED.fetched_at,
                updated_at = NOW()
            """,
            (
                detail.fotmob_match_id,
                47,  # league_id
                detail.season or "2025/2026",
                detail.round_number,
                detail.match_date.date() if detail.match_date else datetime.now(timezone.utc).date(),
                detail.home_team.id if detail.home_team else 0,
                detail.home_team.name if detail.home_team else "",
                detail.away_team.id if detail.away_team else 0,
                detail.away_team.name if detail.away_team else "",
                detail.home_team.score if detail.home_team else None,
                detail.away_team.score if detail.away_team else None,
                detail.ht_score_home,
                detail.ht_score_away,
                detail.status or "unknown",
                detail.venue,
                detail.attendance,
                detail.referee,
                detail.home_lineup.formation if detail.home_lineup else None,
                detail.away_lineup.formation if detail.away_lineup else None,
                _to_jsonb(detail.events),
                _to_jsonb(detail.stat_periods),
                _to_jsonb(detail.home_lineup),
                _to_jsonb(detail.away_lineup),
                _to_jsonb(detail.shotmap),
                _to_jsonb(detail.match_facts),
                _to_jsonb(detail.momentum),
                detail.home_lineup.avg_rating if detail.home_lineup else None,
                detail.away_lineup.avg_rating if detail.away_lineup else None,
                motm_id,
                motm_name,
                psycopg2.extras.Json(detail.raw_json, dumps=lambda x: json.dumps(x, default=str)),
                detail.fetched_at or datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            ),
        )

        # Upsert player performances
        _upsert_player_performances(cur, detail)

    conn.commit()


def _upsert_player_performances(cur, detail: FotMobMatchDetail) -> None:
    """Insert/update player performances for a match."""
    # Delete existing performances for this match (simpler than per-player upsert)
    cur.execute(
        "DELETE FROM fotmob_player_performances WHERE fotmob_match_id = %s",
        (detail.fotmob_match_id,),
    )

    players_to_insert = []

    for lineup, is_home in [
        (detail.home_lineup, True),
        (detail.away_lineup, False),
    ]:
        if not lineup:
            continue
        all_players = lineup.starters + lineup.subs
        for player in all_players:
            if not player.id:
                continue

            # Merge with detailed stats if available
            pid_str = str(player.id)
            detailed = detail.player_stats.get(pid_str)
            stats_dict = detailed.stats if detailed else None

            # Extract key stats from detailed stats
            extracted = _extract_player_stats(stats_dict)

            # Sub minutes - substitution_events can be a dict or a list
            sub_in = None
            sub_out = None
            se = player.substitution_events
            if isinstance(se, dict):
                sub_in = se.get("subIn")
                sub_out = se.get("subOut")
            elif isinstance(se, list):
                for sev in se:
                    if isinstance(sev, dict):
                        if sev.get("type") == "subIn" or "subbedIn" in str(sev.get("type", "")):
                            sub_in = sev.get("time")
                        elif sev.get("type") == "subOut" or "subbedOut" in str(sev.get("type", "")):
                            sub_out = sev.get("time")
            if isinstance(sub_in, dict):
                sub_in = sub_in.get("time")
            if isinstance(sub_out, dict):
                sub_out = sub_out.get("time")

            players_to_insert.append((
                detail.fotmob_match_id,
                player.id,
                player.name or "",
                lineup.team_id,
                lineup.team_name or "",
                is_home,
                player.is_starter,
                player.position_id,
                player.shirt_number,
                player.rating,
                extracted.get("minutes_played"),
                extracted.get("goals", 0),
                extracted.get("assists", 0),
                extracted.get("xg"),
                extracted.get("xgot"),
                extracted.get("xa"),
                extracted.get("shots"),
                extracted.get("shots_on_target"),
                extracted.get("passes"),
                extracted.get("passes_accurate"),
                extracted.get("chances_created"),
                extracted.get("tackles"),
                extracted.get("interceptions"),
                extracted.get("defensive_actions"),
                player.fantasy_score,
                _safe_int(sub_in),
                _safe_int(sub_out),
                psycopg2.extras.Json(stats_dict, dumps=lambda x: json.dumps(x, default=str)) if stats_dict else None,
            ))

    if players_to_insert:
        cur.executemany(
            """
            INSERT INTO fotmob_player_performances (
                fotmob_match_id, player_id, player_name, team_id, team_name,
                is_home, is_starter, position_id, shirt_number,
                rating, minutes_played, goals, assists,
                xg, xgot, xa,
                shots, shots_on_target, passes, passes_accurate,
                chances_created, tackles, interceptions, defensive_actions,
                fantasy_score, sub_in_minute, sub_out_minute, stats_json
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            players_to_insert,
        )


def _extract_player_stats(stats_raw: object) -> dict:
    """Extract key stats from the detailed player stats structure.

    Structure: list of groups, each with:
      title, key, stats: {displayName: {key: str, stat: {value, type}}}
    """
    result: dict = {}
    if not stats_raw:
        return result

    key_map = {
        "minutes_played": "minutes_played",
        "goals": "goals",
        "assists": "assists",
        "expected_goals": "xg",
        "expected_goals_on_target_faced": "xgot",
        "expected_goals_on_target": "xgot",
        "expected_assists": "xa",
        "total_shots": "shots",
        "ontarget_scoring_att": "shots_on_target",
        "accurate_passes": "passes_accurate",
        "total_pass": "passes",
        "chances_created": "chances_created",
        "won_tackle": "tackles",
        "interception": "interceptions",
        "defensive_actions": "defensive_actions",
    }

    groups = stats_raw if isinstance(stats_raw, list) else []

    for group in groups:
        if not isinstance(group, dict):
            continue
        stats_dict = group.get("stats", {})
        if not isinstance(stats_dict, dict):
            continue
        for display_name, stat_entry in stats_dict.items():
            if not isinstance(stat_entry, dict):
                continue
            key = stat_entry.get("key", "")
            stat_obj = stat_entry.get("stat", {})
            val = stat_obj.get("value") if isinstance(stat_obj, dict) else None

            mapped = key_map.get(key)
            if mapped and val is not None:
                if mapped in ("xg", "xgot", "xa"):
                    result[mapped] = _safe_float(val)
                else:
                    result[mapped] = _safe_int(val)

    return result


def _to_jsonb(obj: object):
    """Wrap a dataclass, dict or list for psycopg2 JSONB insertion."""
    if obj is None:
        return None
    try:
        if hasattr(obj, "__dataclass_fields__"):
            data = asdict(obj)
        elif isinstance(obj, list):
            data = [asdict(item) if hasattr(item, "__dataclass_fields__") else item for item in obj]
        else:
            data = obj
        return psycopg2.extras.Json(data, dumps=lambda x: json.dumps(x, default=str))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ #
# Main backfill logic
# ------------------------------------------------------------------ #


def run_backfill(args: argparse.Namespace) -> None:
    conn = get_connection()
    if conn is None:
        logger.error("Could not connect to database")
        sys.exit(1)

    ensure_tables(conn)

    provider = FotMobProvider(min_request_interval=args.delay)

    # Fetch league matches
    logger.info("Fetching league matches...")
    all_matches = provider.fetch_league_matches(
        league_id=args.league_id, season=args.season
    )
    logger.info("Total matches in season: %d", len(all_matches))

    # Group by round
    rounds: dict[int, list[FotMobLeagueMatch]] = defaultdict(list)
    for m in all_matches:
        r = m.round or 0
        rounds[r].append(m)

    # Filter rounds
    round_numbers = sorted(rounds.keys())
    if args.round is not None:
        round_numbers = [r for r in round_numbers if r == args.round]
    else:
        if args.from_round is not None:
            round_numbers = [r for r in round_numbers if r >= args.from_round]
        if args.to_round is not None:
            round_numbers = [r for r in round_numbers if r <= args.to_round]

    # Filter to finished matches only (unless --force)
    total_fetched = 0
    total_skipped = 0
    total_errors = 0
    rounds_processed = 0

    for rnd in round_numbers:
        matches = rounds[rnd]
        finished_matches = [m for m in matches if m.finished]

        if not finished_matches:
            logger.info("Round %d: no finished matches, skipping", rnd)
            continue

        round_log_parts = []
        rounds_processed += 1

        for match in finished_matches:
            label = f"{match.home_name} {match.score_str or '?'} {match.away_name}"

            if not args.force and match_exists(conn, match.id):
                round_log_parts.append(f"{label} [skipped]")
                total_skipped += 1
                continue

            if args.dry_run:
                round_log_parts.append(f"{label} [dry-run]")
                total_fetched += 1
                continue

            try:
                detail = provider.fetch_match_details(match.id)
                upsert_match(conn, detail)
                round_log_parts.append(f"{label} [fetched]")
                total_fetched += 1
            except Exception as exc:
                logger.error("Error fetching match %s (%s): %s", match.id, label, exc, exc_info=True)
                round_log_parts.append(f"{label} [ERROR]")
                total_errors += 1

        logger.info("Round %d: %s", rnd, " | ".join(round_log_parts))

    # Summary
    action = "Would fetch" if args.dry_run else "Fetched"
    logger.info(
        "Done! Rounds: %d | %s: %d | Skipped: %d | Errors: %d",
        rounds_processed,
        action,
        total_fetched,
        total_skipped,
        total_errors,
    )

    conn.close()


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill FotMob match data for the Premier League"
    )
    parser.add_argument("--round", type=int, default=None, help="Specific round to fetch")
    parser.add_argument("--from-round", type=int, default=None, help="Start from round N")
    parser.add_argument("--to-round", type=int, default=None, help="End at round N")
    parser.add_argument("--force", action="store_true", help="Re-fetch existing matches")
    parser.add_argument("--dry-run", action="store_true", help="Preview without fetching")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests (seconds)")
    parser.add_argument("--league-id", type=int, default=47, help="FotMob league ID (default: 47 = PL)")
    parser.add_argument("--season", type=str, default="2025/2026", help="Season string")
    args = parser.parse_args()

    run_backfill(args)


if __name__ == "__main__":
    main()
