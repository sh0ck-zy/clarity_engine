"""
Orchestrates data ingestion to refresh the database from external sources.

Steps (default order):
1) FBRef scraper for fixtures and basic xG (selenium-based).
2) Understat enrichment for PPDA and field tilt.
3) Elo backfill to fill missing Elo ratings.

Usage examples (from repo root, venv active):
    python scripts/update_from_sources.py
    python scripts/update_from_sources.py --skip-understat
    python scripts/update_from_sources.py --only understat
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.ingestion.scraper import run_scraper
from src.ingestion.understat_enrich import run_enrichment
from src.ingestion.elo_backfill import run_elo_backfill


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh DB from scrapers/enrichers.")
    parser.add_argument(
        "--only",
        choices=["scraper", "understat", "elo"],
        help="Run only a specific step.",
    )
    parser.add_argument(
        "--skip-understat",
        action="store_true",
        help="Skip Understat enrichment step.",
    )
    parser.add_argument(
        "--skip-elo",
        action="store_true",
        help="Skip Elo backfill step.",
    )
    args = parser.parse_args()

    if args.only:
        if args.only == "scraper":
            run_scraper()
        elif args.only == "understat":
            run_enrichment()
        elif args.only == "elo":
            run_elo_backfill()
        return

    # Default full pipeline
    run_scraper()

    if not args.skip_understat:
        run_enrichment()

    if not args.skip_elo:
        run_elo_backfill()


if __name__ == "__main__":
    main()
