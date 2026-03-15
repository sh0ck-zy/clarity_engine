#!/usr/bin/env python
"""Backfill historical odds from football-data.co.uk → parquet.

Usage:
    python scripts/backfill_odds.py                      # all leagues, all seasons
    python scripts/backfill_odds.py --league-id 47       # PL only
    python scripts/backfill_odds.py --season 2425        # specific season
    python scripts/backfill_odds.py --no-download        # parse existing CSVs only
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from odds.importer import LEAGUE_CONFIG, SEASONS, download_csv, parse_csv, save_parquet

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical odds to parquet")
    parser.add_argument("--league-id", type=int, help="Single league ID to process")
    parser.add_argument("--season", type=str, help="Single season to process (e.g. 2425)")
    parser.add_argument("--no-download", action="store_true", help="Skip download, parse existing CSVs only")
    parser.add_argument("--force", action="store_true", help="Re-download even if CSV exists (refresh stale data)")
    args = parser.parse_args()

    leagues = {args.league_id: LEAGUE_CONFIG[args.league_id]} if args.league_id else LEAGUE_CONFIG
    seasons = [args.season] if args.season else SEASONS

    summary: list[dict] = []

    for league_id, config in leagues.items():
        code = config["code"]
        for season in seasons:
            csv_dir = _PROJECT_ROOT / "data" / "football_data" / "odds"
            csv_path = csv_dir / f"{code}_{season}.csv"

            # Download
            if not args.no_download:
                try:
                    csv_path = download_csv(league_id, season, force=args.force)
                except Exception as e:
                    logger.warning("Download failed %s_%s: %s", code, season, e)
                    continue

            if not csv_path.exists():
                logger.debug("No CSV for %s_%s, skipping", code, season)
                continue

            # Parse
            try:
                df = parse_csv(csv_path, league_id, season)
            except Exception as e:
                logger.warning("Parse failed %s_%s: %s", code, season, e)
                continue

            if df.empty:
                logger.info("Empty result for %s_%s", code, season)
                continue

            # Save parquet
            out = save_parquet(df)
            n_open = df["odds_H_open"].notna().sum()
            n_close = df["odds_H_close"].notna().sum()
            summary.append({
                "league": code,
                "season": season,
                "matches": len(df),
                "opening": int(n_open),
                "closing": int(n_close),
                "file": str(out.name),
            })

    # Print summary
    if summary:
        print(f"\n{'League':<8} {'Season':<8} {'Matches':>8} {'Opening':>8} {'Closing':>8} {'File'}")
        print("-" * 64)
        for row in summary:
            print(f"{row['league']:<8} {row['season']:<8} {row['matches']:>8} {row['opening']:>8} {row['closing']:>8} {row['file']}")
        total = sum(r["matches"] for r in summary)
        print(f"\nTotal: {total} matches across {len(summary)} league-seasons")
    else:
        print("No data processed.")


if __name__ == "__main__":
    main()
