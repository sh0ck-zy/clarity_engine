#!/usr/bin/env python3
"""
Backfill Historical Lineup Data

Fetches lineup data from Transfermarkt for all mapped fixtures
and stores in lineups_historical table.

Usage:
    python scripts/backfill_lineups.py
    python scripts/backfill_lineups.py --limit 10
    python scripts/backfill_lineups.py --fixture 2025-08-15_Liverpool_Bournemouth
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.ingestion.transfermarkt_lineups import TransfermarktLineupScraper, MatchLineup


def ensure_table_exists(conn) -> None:
    """Create lineups_historical table if not exists."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lineups_historical (
            id SERIAL PRIMARY KEY,
            fixture_id TEXT NOT NULL,
            match_id TEXT,
            match_date DATE,
            team_name TEXT NOT NULL,
            is_home BOOLEAN,
            formation TEXT,
            starters JSONB,
            bench JSONB,
            source TEXT DEFAULT 'transfermarkt',
            ingested_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(fixture_id, team_name)
        )
    """)
    conn.commit()


def get_mapped_fixtures(conn, limit: int = None) -> list[tuple[str, str]]:
    """Get fixtures that have TM mappings but no lineup data yet."""
    cur = conn.cursor()

    query = """
        SELECT m.fixture_id, m.tm_match_id
        FROM tm_match_mapping m
        LEFT JOIN lineups_historical l ON m.fixture_id = l.fixture_id
        WHERE l.fixture_id IS NULL
        ORDER BY m.match_date
    """
    if limit:
        query += f" LIMIT {limit}"

    cur.execute(query)
    return cur.fetchall()


def save_lineup(conn, lineup: MatchLineup) -> int:
    """Save lineup to database. Returns number of rows inserted."""
    cur = conn.cursor()
    count = 0

    # Insert home team lineup
    cur.execute("""
        INSERT INTO lineups_historical
        (fixture_id, match_id, match_date, team_name, is_home, formation, starters, bench, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fixture_id, team_name) DO UPDATE SET
            formation = EXCLUDED.formation,
            starters = EXCLUDED.starters,
            bench = EXCLUDED.bench
    """, (
        lineup.fixture_id,
        lineup.match_id,
        lineup.match_date,
        lineup.home_team,
        True,
        lineup.home_formation,
        json.dumps([{
            "player_id": p.player_id,
            "player_name": p.player_name,
            "position": p.position,
            "shirt_number": p.shirt_number,
        } for p in lineup.home_starters]),
        json.dumps([{
            "player_id": p.player_id,
            "player_name": p.player_name,
            "position": p.position,
            "shirt_number": p.shirt_number,
        } for p in lineup.home_bench]),
        lineup.source,
    ))
    count += cur.rowcount

    # Insert away team lineup
    cur.execute("""
        INSERT INTO lineups_historical
        (fixture_id, match_id, match_date, team_name, is_home, formation, starters, bench, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fixture_id, team_name) DO UPDATE SET
            formation = EXCLUDED.formation,
            starters = EXCLUDED.starters,
            bench = EXCLUDED.bench
    """, (
        lineup.fixture_id,
        lineup.match_id,
        lineup.match_date,
        lineup.away_team,
        False,
        lineup.away_formation,
        json.dumps([{
            "player_id": p.player_id,
            "player_name": p.player_name,
            "position": p.position,
            "shirt_number": p.shirt_number,
        } for p in lineup.away_starters]),
        json.dumps([{
            "player_id": p.player_id,
            "player_name": p.player_name,
            "position": p.position,
            "shirt_number": p.shirt_number,
        } for p in lineup.away_bench]),
        lineup.source,
    ))
    count += cur.rowcount

    return count


def main():
    parser = argparse.ArgumentParser(description="Backfill lineup data")
    parser.add_argument("--limit", type=int, help="Limit number of fixtures to process")
    parser.add_argument("--fixture", help="Process specific fixture ID")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests")
    args = parser.parse_args()

    conn = get_connection()
    if not conn:
        print("Could not connect to database")
        return 1

    try:
        ensure_table_exists(conn)

        scraper = TransfermarktLineupScraper(delay=args.delay)

        if args.fixture:
            # Process single fixture
            fixtures = [(args.fixture, scraper.get_tm_match_id(args.fixture))]
            if not fixtures[0][1]:
                print(f"No TM mapping found for {args.fixture}")
                return 1
        else:
            # Get all unmapped fixtures
            fixtures = get_mapped_fixtures(conn, args.limit)

        print(f"Processing {len(fixtures)} fixtures...")
        print("=" * 60)

        total_saved = 0
        failed = 0

        for i, (fixture_id, tm_match_id) in enumerate(fixtures):
            print(f"\n[{i+1}/{len(fixtures)}] {fixture_id}")
            print(f"  TM ID: {tm_match_id}")

            lineup = scraper.get_match_lineup(tm_match_id)
            if not lineup:
                print("  Failed to fetch lineup")
                failed += 1
                continue

            lineup.fixture_id = fixture_id
            print(f"  {lineup.home_team} ({lineup.home_formation}) vs {lineup.away_team} ({lineup.away_formation})")
            print(f"  Starters: {len(lineup.home_starters)} vs {len(lineup.away_starters)}")

            saved = save_lineup(conn, lineup)
            total_saved += saved
            conn.commit()
            print(f"  Saved {saved} lineup records")

        print("\n" + "=" * 60)
        print(f"COMPLETE")
        print(f"  Total saved: {total_saved}")
        print(f"  Failed: {failed}")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        conn.rollback()
        return 1
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
