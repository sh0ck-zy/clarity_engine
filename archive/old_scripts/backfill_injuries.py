#!/usr/bin/env python3
"""
Backfill Injury Data from Transfermarkt

Scrapes injury history for all Premier League teams and stores in
the player_injuries_historical table.

Usage:
    # All teams, current season
    python scripts/backfill_injuries.py --season 2024

    # Single team
    python scripts/backfill_injuries.py --team Arsenal --season 2024

    # Current injuries only (filter to 24/25 season)
    python scripts/backfill_injuries.py --season 2024 --current-only

    # Dry run (don't save to DB)
    python scripts/backfill_injuries.py --team Arsenal --season 2024 --dry-run
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.ingestion.transfermarkt_injuries import TransfermarktInjuryScraper
from src.ingestion.transfermarkt_teams import PL_TEAMS, get_all_teams


def main():
    parser = argparse.ArgumentParser(
        description="Backfill injury data from Transfermarkt"
    )
    parser.add_argument(
        "--season",
        required=True,
        help="Season year (e.g., 2024 for 2024-25 season)"
    )
    parser.add_argument(
        "--team",
        help="Single team to scrape (default: all PL teams)"
    )
    parser.add_argument(
        "--current-only",
        action="store_true",
        help="Only scrape injuries from current season (24/25)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Delay between requests in seconds (default: 2.0)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save to database, just print results"
    )
    args = parser.parse_args()

    # Determine season filter
    season_filter = None
    if args.current_only:
        # Convert 2024 -> "24/25"
        year = int(args.season)
        season_filter = f"{str(year)[-2:]}/{str(year + 1)[-2:]}"
        print(f"Filtering to season: {season_filter}")

    # Determine teams to scrape
    if args.team:
        if args.team not in PL_TEAMS:
            print(f"Error: Team '{args.team}' not found in PL_TEAMS")
            print(f"Available teams: {', '.join(get_all_teams())}")
            sys.exit(1)
        teams = [args.team]
    else:
        teams = get_all_teams()

    print(f"\n{'='*60}")
    print(f"Transfermarkt Injury Backfill")
    print(f"{'='*60}")
    print(f"Season: {args.season}")
    print(f"Teams: {len(teams)}")
    print(f"Delay: {args.delay}s")
    print(f"Dry run: {args.dry_run}")
    print(f"{'='*60}\n")

    # Initialize scraper
    scraper = TransfermarktInjuryScraper(delay=args.delay)

    total_injuries = 0
    total_saved = 0

    for i, team_name in enumerate(teams):
        print(f"\n[{i+1}/{len(teams)}] {team_name}")
        print("-" * 40)

        try:
            injuries = scraper.scrape_team_injuries(
                team_name=team_name,
                season=args.season,
                season_filter=season_filter
            )

            total_injuries += len(injuries)
            print(f"  Found {len(injuries)} injury records")

            if injuries and not args.dry_run:
                saved = scraper.save_to_db(injuries)
                total_saved += saved
                print(f"  Saved {saved} records to DB")

            elif injuries and args.dry_run:
                print("  [DRY RUN] Would save to DB:")
                for inj in injuries[:5]:
                    status = "ongoing" if inj.to_date is None else f"until {inj.to_date}"
                    print(f"    - {inj.player_name}: {inj.injury_type} ({status})")
                if len(injuries) > 5:
                    print(f"    ... and {len(injuries) - 5} more")

        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    print(f"\n{'='*60}")
    print(f"COMPLETE")
    print(f"{'='*60}")
    print(f"Total injury records found: {total_injuries}")
    if not args.dry_run:
        print(f"Total records saved to DB: {total_saved}")
    print()


if __name__ == "__main__":
    main()
