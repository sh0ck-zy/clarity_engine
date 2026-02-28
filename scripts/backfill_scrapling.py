#!/usr/bin/env python3
"""
Backfill detailed match stats using Scrapling (stealth browser).

FotMob's /api/matchDetails is behind Cloudflare Turnstile.
This script loads match pages via a stealth browser, extracts the
__NEXT_DATA__ JSON which contains full match detail (xG, shots,
possession, lineups, shotmap, events).

Updates existing fotmob_matches rows that have basic data (from
backfill_fotmob_lite.py) but are missing detailed stats.

Supports parallel fetching via AsyncStealthySession (one browser,
multiple concurrent tabs).

Usage:
    python scripts/backfill_scrapling.py --league-id 61 --season "2025/2026"
    python scripts/backfill_scrapling.py --league-id 268 --season "2025" --workers 5
    python scripts/backfill_scrapling.py --league-id 61 --season "2025/2026" --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
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
logger = logging.getLogger("backfill_scrapling")

BASE_URL = "https://www.fotmob.com"


# ------------------------------------------------------------------ #
# League listing (works without Turnstile)
# ------------------------------------------------------------------ #

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

    r = s.get(
        f"{BASE_URL}/api/leagues",
        params={"id": league_id, "season": season},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    raw_all = data.get("fixtures", {}).get("allMatches", [])
    if isinstance(raw_all, dict):
        raw_all = raw_all.get("matches", [])

    return raw_all


def get_matches_needing_stats(conn, league_id: int) -> set[int]:
    """Get match IDs that exist in DB but have NULL stats."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT fotmob_match_id
            FROM fotmob_matches
            WHERE league_id = %s AND status = 'finished' AND stats IS NULL
            """,
            (league_id,),
        )
        return {row[0] for row in cur.fetchall()}


# ------------------------------------------------------------------ #
# __NEXT_DATA__ extraction (shared by sync and async paths)
# ------------------------------------------------------------------ #

def parse_next_data(html: str, page_url: str) -> dict | None:
    """Extract match detail from __NEXT_DATA__ in HTML."""
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        logger.warning("No __NEXT_DATA__ found for %s", page_url)
        return None

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error for %s: %s", page_url, exc)
        return None

    page_props = data.get("props", {}).get("pageProps", {})
    content = page_props.get("content", {})
    header = page_props.get("header", {})
    general = page_props.get("general", {})

    if not content:
        logger.warning("No content in __NEXT_DATA__ for %s", page_url)
        return None

    return {
        "content": content,
        "header": header,
        "general": general,
    }


def extract_match_detail(data: dict) -> dict:
    """Extract structured match detail from __NEXT_DATA__ pageProps."""
    content = data.get("content", {})
    header = data.get("header", {})

    # Stats: store the raw Periods structure
    stats_raw = content.get("stats", {})

    # Shotmap
    shotmap_raw = content.get("shotmap", {})
    shots = shotmap_raw.get("shots", []) if isinstance(shotmap_raw, dict) else []

    # Lineup
    lineup_raw = content.get("lineup", {})
    formation_home = None
    formation_away = None
    home_lineup = None
    away_lineup = None
    if isinstance(lineup_raw, dict):
        home_team_lineup = lineup_raw.get("homeTeam", {})
        away_team_lineup = lineup_raw.get("awayTeam", {})
        formation_home = home_team_lineup.get("formation", None)
        formation_away = away_team_lineup.get("formation", None)
        home_lineup = home_team_lineup
        away_lineup = away_team_lineup

    # Match facts
    match_facts = content.get("matchFacts", {})

    # Events from match facts
    events = match_facts.get("events", {}) if isinstance(match_facts, dict) else {}

    # Momentum
    momentum = content.get("superlive", {}).get("momentum", [])

    # Average ratings from header
    home_avg_rating = None
    away_avg_rating = None
    if isinstance(header, dict):
        teams = header.get("teams", [])
        if isinstance(teams, list) and len(teams) >= 2:
            home_avg_rating = teams[0].get("rating", {}).get("num") if isinstance(teams[0].get("rating"), dict) else None
            away_avg_rating = teams[1].get("rating", {}).get("num") if isinstance(teams[1].get("rating"), dict) else None

    # HT scores from header
    ht_home_score = None
    ht_away_score = None
    if isinstance(header, dict):
        ht = header.get("status", {}).get("halfs", {})
        if isinstance(ht, dict):
            ht_score = ht.get("firstHalfScore", "")
            if isinstance(ht_score, str) and " - " in ht_score:
                parts = ht_score.split(" - ")
                try:
                    ht_home_score = int(parts[0].strip())
                    ht_away_score = int(parts[1].strip())
                except ValueError:
                    pass

    return {
        "stats": stats_raw,
        "events": events,
        "shotmap": shots,
        "home_lineup": home_lineup,
        "away_lineup": away_lineup,
        "formation_home": formation_home,
        "formation_away": formation_away,
        "match_facts": match_facts,
        "momentum": momentum,
        "home_avg_rating": home_avg_rating,
        "away_avg_rating": away_avg_rating,
        "ht_home_score": ht_home_score,
        "ht_away_score": ht_away_score,
    }


# ------------------------------------------------------------------ #
# DB update
# ------------------------------------------------------------------ #

def update_match_stats(conn, match_id: int, detail: dict) -> None:
    """Update an existing fotmob_matches row with detailed stats."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE fotmob_matches SET
                stats = %s,
                events = %s,
                shotmap = %s,
                home_lineup = %s,
                away_lineup = %s,
                formation_home = COALESCE(%s, formation_home),
                formation_away = COALESCE(%s, formation_away),
                match_facts = %s,
                momentum = %s,
                home_avg_rating = COALESCE(%s, home_avg_rating),
                away_avg_rating = COALESCE(%s, away_avg_rating),
                ht_home_score = COALESCE(%s, ht_home_score),
                ht_away_score = COALESCE(%s, ht_away_score),
                updated_at = NOW()
            WHERE fotmob_match_id = %s
            """,
            (
                psycopg2.extras.Json(detail["stats"]),
                psycopg2.extras.Json(detail["events"]),
                psycopg2.extras.Json(detail["shotmap"]),
                psycopg2.extras.Json(detail["home_lineup"]),
                psycopg2.extras.Json(detail["away_lineup"]),
                detail["formation_home"],
                detail["formation_away"],
                psycopg2.extras.Json(detail["match_facts"]),
                psycopg2.extras.Json(detail["momentum"]),
                detail["home_avg_rating"],
                detail["away_avg_rating"],
                detail["ht_home_score"],
                detail["ht_away_score"],
                match_id,
            ),
        )


def get_xg_summary(stats: dict) -> str:
    """Extract xG string from stats for logging."""
    if isinstance(stats, dict) and "Periods" in stats:
        for cat in stats.get("Periods", {}).get("All", {}).get("stats", []):
            if cat.get("key") == "top_stats":
                for s in cat.get("stats", []):
                    if s.get("key") == "expected_goals":
                        vals = s.get("stats", ["?", "?"])
                        return f"{vals[0]} vs {vals[1]}"
    return "?"


# ------------------------------------------------------------------ #
# Sync fetch (legacy, for --no-async / dry-run)
# ------------------------------------------------------------------ #

def fetch_match_detail_sync(page_url: str, headless: bool = True) -> dict | None:
    """Load a FotMob match page via stealth browser (sync) and extract __NEXT_DATA__."""
    from scrapling.fetchers import StealthyFetcher

    full_url = f"{BASE_URL}{page_url}"

    try:
        page = StealthyFetcher.fetch(
            full_url,
            headless=headless,
            disable_resources=True,
            network_idle=True,
            timeout=45000,
        )
    except Exception as exc:
        logger.error("Scrapling fetch error for %s: %s", page_url, exc)
        return None

    if page.status != 200:
        logger.warning("Non-200 status (%d) for %s", page.status, page_url)
        return None

    html = ""
    if hasattr(page, "body") and page.body:
        html = page.body.decode("utf-8", errors="ignore")
    if not html:
        logger.warning("Empty HTML for %s", page_url)
        return None

    return parse_next_data(html, page_url)


# ------------------------------------------------------------------ #
# Async parallel fetch
# ------------------------------------------------------------------ #

def _fetch_and_update_one(args: tuple) -> tuple[int, bool, str]:
    """Fetch a single match detail and update DB. Runs in a worker process.

    Returns (match_id, success, message).
    """
    mid, page_url, delay, headless = args

    try:
        from scrapling.fetchers import StealthyFetcher

        full_url = f"{BASE_URL}{page_url}"
        page = StealthyFetcher.fetch(
            full_url,
            headless=headless,
            disable_resources=True,
            network_idle=True,
            timeout=45000,
        )

        if page.status != 200:
            return (mid, False, f"Non-200 status ({page.status})")

        html = ""
        if hasattr(page, "body") and page.body:
            html = page.body.decode("utf-8", errors="ignore")

        if not html:
            return (mid, False, "Empty HTML")

        data = parse_next_data(html, page_url)
        if not data:
            return (mid, False, "No __NEXT_DATA__")

        detail = extract_match_detail(data)

        # Each worker gets its own DB connection
        conn = get_connection()
        try:
            update_match_stats(conn, mid, detail)
            conn.commit()
        finally:
            conn.close()

        xg_str = get_xg_summary(detail["stats"])
        msg = f"xG: {xg_str} | Formation: {detail['formation_home']} vs {detail['formation_away']}"

        time.sleep(delay)
        return (mid, True, msg)

    except Exception as exc:
        return (mid, False, str(exc))


# ------------------------------------------------------------------ #
# Main backfill
# ------------------------------------------------------------------ #

def run_backfill(
    league_id: int,
    season: str,
    workers: int = 3,
    delay: float = 2.0,
    dry_run: bool = False,
    limit: int = 0,
    headless: bool = True,
    use_async: bool = True,
):
    """Run the Scrapling-based detail backfill."""
    # 1. Get match list from league endpoint
    logger.info("Fetching league %d season %s ...", league_id, season)
    all_matches = fetch_league_matches(league_id, season)
    finished = [m for m in all_matches if m.get("status", {}).get("finished", False)]
    logger.info("Found %d finished matches in season", len(finished))

    # 2. Find which matches need stats
    conn = get_connection()
    try:
        needs_stats = get_matches_needing_stats(conn, league_id)
        logger.info("%d matches in DB need stats", len(needs_stats))

        # Filter to only matches that need stats and are in the league listing
        to_fetch = []
        for m in finished:
            mid = int(m["id"])
            if mid in needs_stats:
                page_url = m.get("pageUrl", "")
                if page_url:
                    to_fetch.append((mid, page_url, m))

        logger.info("%d matches to fetch via Scrapling", len(to_fetch))

        if limit > 0:
            to_fetch = to_fetch[:limit]
            logger.info("Limited to %d matches", limit)

        if not to_fetch:
            logger.info("No matches need stats — all done!")
            return

        if dry_run:
            # Just fetch one match to verify
            mid, page_url, m_data = to_fetch[0]
            home = m_data.get("home", {}).get("name", "?")
            away = m_data.get("away", {}).get("name", "?")
            logger.info("DRY RUN: Fetching %s vs %s (id=%d)", home, away, mid)
            data = fetch_match_detail_sync(page_url, headless=headless)
            if data:
                detail = extract_match_detail(data)
                stats = detail["stats"]
                if isinstance(stats, dict) and "Periods" in stats:
                    periods = stats["Periods"]
                    all_stats = periods.get("All", {}).get("stats", [])
                    for cat in all_stats:
                        if cat.get("key") == "top_stats":
                            for s in cat.get("stats", []):
                                title = s.get("title", "?")
                                vals = s.get("stats", [None, None])
                                logger.info("  %s: %s vs %s", title, vals[0], vals[1])
                logger.info("  Formation: %s vs %s", detail["formation_home"], detail["formation_away"])
                logger.info("  Shotmap: %d shots", len(detail["shotmap"]))
                logger.info("  Ratings: %.1f vs %.1f",
                            detail["home_avg_rating"] or 0,
                            detail["away_avg_rating"] or 0)
            else:
                logger.error("Failed to fetch match detail")
            return

        # 3. Fetch details
        total = len(to_fetch)
        if use_async and workers > 1:
            from concurrent.futures import ProcessPoolExecutor, as_completed

            logger.info("Using %d parallel workers, %.1fs delay each", workers, delay)

            # Build worker args
            worker_args = [(mid, page_url, delay, headless) for mid, page_url, m_data in to_fetch]
            match_names = {mid: f"{m.get('home',{}).get('name','?')} vs {m.get('away',{}).get('name','?')}"
                          for mid, _, m in to_fetch}

            success = 0
            errors_count = 0
            completed = 0

            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_fetch_and_update_one, args): args[0]
                          for args in worker_args}

                for future in as_completed(futures):
                    mid = futures[future]
                    completed += 1
                    try:
                        match_id, ok, msg = future.result()
                        if ok:
                            success += 1
                            logger.info("[%d/%d] ✓ %s — %s", completed, total, match_names[mid], msg)
                        else:
                            errors_count += 1
                            logger.error("[%d/%d] ✗ %s — %s", completed, total, match_names[mid], msg)
                    except Exception as exc:
                        errors_count += 1
                        logger.error("[%d/%d] ✗ %s — %s", completed, total, match_names[mid], exc)

            logger.info("Done! %d/%d succeeded, %d errors", success, total, errors_count)
        else:
            # Sequential fallback
            logger.info("Using sequential mode, %.1fs delay", delay)
            success = 0
            errors_count = 0
            for i, (mid, page_url, m_data) in enumerate(to_fetch):
                home = m_data.get("home", {}).get("name", "?")
                away = m_data.get("away", {}).get("name", "?")
                logger.info("[%d/%d] Fetching %s vs %s (id=%d) ...", i + 1, len(to_fetch), home, away, mid)

                data = fetch_match_detail_sync(page_url, headless=headless)
                if data:
                    detail = extract_match_detail(data)
                    update_match_stats(conn, mid, detail)
                    conn.commit()
                    success += 1
                    xg_str = get_xg_summary(detail["stats"])
                    logger.info("  ✓ xG: %s | Formation: %s vs %s",
                                xg_str, detail["formation_home"], detail["formation_away"])
                else:
                    errors_count += 1
                    logger.error("  ✗ Failed to fetch detail")

                if i < len(to_fetch) - 1:
                    time.sleep(delay)

            logger.info("Done! %d/%d succeeded, %d errors", success, len(to_fetch), errors_count)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill match details via Scrapling (stealth browser)"
    )
    parser.add_argument("--league-id", type=int, required=True, help="FotMob league ID")
    parser.add_argument("--season", type=str, required=True, help="Season (e.g. '2025/2026' or '2025')")
    parser.add_argument("--workers", type=int, default=3, help="Number of parallel browser tabs (default: 3)")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between requests per worker (default: 2)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch 1 match and print stats")
    parser.add_argument("--limit", type=int, default=0, help="Max matches to fetch (0 = all)")
    parser.add_argument("--no-headless", action="store_true", help="Show browser window")
    parser.add_argument("--no-parallel", action="store_true", help="Use sequential fetching (debug)")

    args = parser.parse_args()

    run_backfill(
        league_id=args.league_id,
        season=args.season,
        workers=args.workers,
        delay=args.delay,
        dry_run=args.dry_run,
        limit=args.limit,
        headless=not args.no_headless,
        use_async=not args.no_parallel,
    )


if __name__ == "__main__":
    main()
