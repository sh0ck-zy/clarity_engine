import argparse
import random
import sys
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import soccerdata as sd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

DEFAULT_LEAGUE = "ENG-Premier League"
DEFAULT_SEASONS = ["2122", "2223", "2324", "2425"]
STAT_TYPES = {
    "standard": "standard",
    "shooting": "shooting",
    "possession": "possession",
    "misc": "misc",
}


def sleep_with_jitter(min_delay: float, max_delay: float) -> None:
    delay = random.uniform(min_delay, max_delay)
    print(f"   Sleeping {delay:.1f}s to respect rate limits...")
    time.sleep(delay)


def ensure_cache_dir(base_dir: Path, season: str) -> Path:
    season_dir = base_dir / season
    season_dir.mkdir(parents=True, exist_ok=True)
    return season_dir


def write_cache(df: pd.DataFrame, path: Path) -> None:
    df.reset_index().to_json(
        path,
        orient="records",
        date_format="iso",
        indent=2,
        force_ascii=True,
    )
    print(f"   Cached {len(df)} rows to {path}")


def fetch_schedule(fbref: sd.FBref, season_dir: Path) -> None:
    print(" - Fetching fixtures schedule...")
    schedule = fbref.read_schedule()
    if schedule is None or schedule.empty:
        print("   No schedule data returned.")
        return
    write_cache(schedule, season_dir / "fixtures_schedule.json")


def fetch_team_stats(fbref: sd.FBref, season_dir: Path) -> None:
    for label, stat_type in STAT_TYPES.items():
        print(f" - Fetching team season stats ({label})...")
        try:
            stats = fbref.read_team_season_stats(stat_type=stat_type)
        except Exception as exc:
            print(f"   Failed to fetch {label} stats: {exc}")
            continue

        if stats is None or stats.empty:
            print(f"   No {label} stats returned.")
            continue

        write_cache(stats, season_dir / f"team_stats_{label}.json")


def scrape_season(
    league: str,
    season: str,
    cache_dir: Path,
    min_delay: float,
    max_delay: float,
) -> None:
    print(f"\nSeason {season} - League {league}")
    fbref = sd.FBref(leagues=league, seasons=season)
    season_dir = ensure_cache_dir(cache_dir, season)

    fetch_schedule(fbref, season_dir)
    sleep_with_jitter(min_delay, max_delay)

    fetch_team_stats(fbref, season_dir)
    sleep_with_jitter(min_delay, max_delay)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape FBref historical fixtures and team stats with caching.",
    )
    parser.add_argument(
        "--league",
        default=DEFAULT_LEAGUE,
        help="League identifier used by soccerdata (default: ENG-Premier League).",
    )
    parser.add_argument(
        "--seasons",
        nargs="*",
        default=DEFAULT_SEASONS,
        help="Seasons to scrape (default: 2122 2223 2324 2425).",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(PROJECT_ROOT / "data" / "fbref_cache"),
        help="Directory to write JSON caches.",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=3.0,
        help="Minimum delay between requests in seconds.",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=5.0,
        help="Maximum delay between requests in seconds.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    print("FBref Historical Scraper")
    print(f"Caching to: {cache_dir}")
    print(f"Seasons: {', '.join(args.seasons)}")
    print(f"Rate limit: {args.min_delay:.1f}-{args.max_delay:.1f}s")

    for season in args.seasons:
        scrape_season(
            args.league,
            season,
            cache_dir,
            args.min_delay,
            args.max_delay,
        )

    print("\nDone. Cached data is ready for DB insertion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
