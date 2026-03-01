#!/usr/bin/env python3
"""
Lightweight FotMob backfill using only the league listing endpoint.

FotMob's match detail endpoint now requires Turnstile verification (403),
so this script uses only /api/leagues which returns basic match data:
team IDs, names, scores, round numbers, dates, and status.

This gives us enough to build team_states (W/D/L, goals, form) but
NOT detailed stats (xG, shots, possession, lineups, events).

Usage:
    python scripts/backfill_fotmob_lite.py --league-id 61 --season "2025/2026"
    python scripts/backfill_fotmob_lite.py --league-id 268 --season "2025"
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2.extras
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.config import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_fotmob_lite")

BASE_URL = "https://www.fotmob.com"


def fetch_league_matches(league_id: int, season: str) -> list[dict]:
    """Fetch all matches for a league season from /api/leagues."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Referer": "https://www.fotmob.com/",
    })

    r = s.get(f"{BASE_URL}/api/leagues", params={"id": league_id, "season": season}, timeout=30)
    r.raise_for_status()
    data = r.json()

    raw_all = data.get("fixtures", {}).get("allMatches", [])
    if isinstance(raw_all, dict):
        raw_all = raw_all.get("matches", [])

    return raw_all


def parse_score(score_str: str) -> tuple[int | None, int | None]:
    """Parse '2 - 1' into (2, 1)."""
    if not score_str:
        return None, None
    parts = score_str.split(" - ")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0].strip()), int(parts[1].strip())
    except ValueError:
        return None, None


def upsert_match_lite(
    conn, match: dict, league_id: int, season: str,
    include_upcoming: bool = False,
) -> bool:
    """Insert or update a match from league listing data.

    Returns True if a new match was inserted, False if skipped/updated.
    """
    match_id = int(match["id"])
    round_number = int(match.get("round") or match.get("roundName") or 0)

    status_data = match.get("status", {})
    utc_time = status_data.get("utcTime", "")
    finished = status_data.get("finished", False)
    started = status_data.get("started", False)
    score_str = status_data.get("scoreStr", "")

    # Parse date
    try:
        match_date = datetime.fromisoformat(utc_time.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        match_date = datetime.now(timezone.utc).date()

    # Determine status
    if finished:
        status = "finished"
    elif started:
        status = "started"
    else:
        status = "scheduled"

    # Only insert finished matches unless --include-upcoming
    if status != "finished" and not include_upcoming:
        return False

    home = match.get("home", {})
    away = match.get("away", {})
    home_score, away_score = parse_score(score_str)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO fotmob_matches (
                fotmob_match_id, league_id, season, round_number, match_date,
                home_team_id, home_team_name, away_team_id, away_team_name,
                home_score, away_score, status,
                raw_json, fetched_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (fotmob_match_id) DO UPDATE SET
                season = EXCLUDED.season,
                round_number = EXCLUDED.round_number,
                match_date = EXCLUDED.match_date,
                home_score = EXCLUDED.home_score,
                away_score = EXCLUDED.away_score,
                status = EXCLUDED.status,
                raw_json = EXCLUDED.raw_json,
                updated_at = NOW()
            """,
            (
                match_id,
                league_id,
                season,
                round_number if round_number > 0 else None,
                match_date,
                int(home.get("id", 0)),
                home.get("name", "Unknown"),
                int(away.get("id", 0)),
                away.get("name", "Unknown"),
                home_score,
                away_score,
                status,
                psycopg2.extras.Json(match),
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            ),
        )
    return True


def run_backfill(league_id: int, season: str, dry_run: bool = False, include_upcoming: bool = False):
    """Run the lightweight backfill."""
    logger.info("Fetching league %d season %s ...", league_id, season)
    matches = fetch_league_matches(league_id, season)
    logger.info("Found %d total matches", len(matches))

    if include_upcoming:
        eligible = matches
        logger.info("Including all matches (finished + upcoming)")
    else:
        eligible = [m for m in matches if m.get("status", {}).get("finished", False)]
        logger.info("Finished matches: %d", len(eligible))

    if dry_run:
        for m in eligible[:5]:
            home = m.get("home", {}).get("name", "?")
            away = m.get("away", {}).get("name", "?")
            score = m.get("status", {}).get("scoreStr", "?") or "vs"
            rnd = m.get("round", "?")
            status = "done" if m.get("status", {}).get("finished") else "upcoming"
            logger.info("  R%s: %s %s %s [%s]", rnd, home, score, away, status)
        logger.info("  ... and %d more", max(0, len(eligible) - 5))
        return

    conn = get_connection()
    inserted = 0
    try:
        for m in eligible:
            if upsert_match_lite(conn, m, league_id, season, include_upcoming=include_upcoming):
                inserted += 1
        conn.commit()
        logger.info("Inserted/updated %d matches for league %d", inserted, league_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Lightweight FotMob backfill (league listing only)")
    parser.add_argument("--league-id", type=int, required=True, help="FotMob league ID")
    parser.add_argument("--season", type=str, required=True, help="Season string (e.g. '2025/2026' or '2025')")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't insert")
    parser.add_argument("--include-upcoming", action="store_true", help="Also insert upcoming/scheduled matches")
    args = parser.parse_args()

    run_backfill(args.league_id, args.season, dry_run=args.dry_run, include_upcoming=args.include_upcoming)


if __name__ == "__main__":
    main()
