import argparse
import csv
import re
import sys
import zlib
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

import requests
from rapidfuzz import process

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection

BASE_URL = "https://www.football-data.co.uk/mmz4281"
DEFAULT_SEASONS = ["2122", "2223", "2324", "2425"]
LEAGUE_CODE = "E0"

# Opening odds columns (early prices)
BOOKMAKER_COLUMNS_OPEN = {
    "B365": {"HOME": "B365H", "DRAW": "B365D", "AWAY": "B365A"},
    "PS": {"HOME": "PSH", "DRAW": "PSD", "AWAY": "PSA"},
    "WH": {"HOME": "WHH", "DRAW": "WHD", "AWAY": "WHA"},
}

# Closing odds columns (final prices before kickoff)
BOOKMAKER_COLUMNS_CLOSE = {
    "B365": {"HOME": "B365CH", "DRAW": "B365CD", "AWAY": "B365CA"},
    "PS": {"HOME": "PSCH", "DRAW": "PSCD", "AWAY": "PSCA"},
    "WH": {"HOME": "WHCH", "DRAW": "WHCD", "AWAY": "WHCA"},
}

# Backward compatibility
BOOKMAKER_COLUMNS = BOOKMAKER_COLUMNS_OPEN

CANONICAL_TEAMS = [
    "AFC Bournemouth",
    "Arsenal",
    "Aston Villa",
    "Brentford",
    "Brighton and Hove Albion",
    "Burnley",
    "Chelsea",
    "Crystal Palace",
    "Everton",
    "Fulham",
    "Leeds United",
    "Leicester City",
    "Liverpool",
    "Luton Town",
    "Manchester City",
    "Manchester United",
    "Newcastle United",
    "Norwich City",
    "Nottingham Forest",
    "Sheffield United",
    "Southampton",
    "Sunderland",
    "Tottenham Hotspur",
    "West Ham United",
    "Wolverhampton Wanderers",
]

TEAM_ALIASES = {
    "brighton": "Brighton and Hove Albion",
    "brighton and hove": "Brighton and Hove Albion",
    "brighton and hove albion": "Brighton and Hove Albion",
    "bournemouth": "AFC Bournemouth",
    "afc bournemouth": "AFC Bournemouth",
    "leeds": "Leeds United",
    "leicester": "Leicester City",
    "man city": "Manchester City",
    "man utd": "Manchester United",
    "man united": "Manchester United",
    "manchester city": "Manchester City",
    "manchester utd": "Manchester United",
    "manchester united": "Manchester United",
    "newcastle": "Newcastle United",
    "newcastle utd": "Newcastle United",
    "norwich": "Norwich City",
    "nott m forest": "Nottingham Forest",
    "nott ham forest": "Nottingham Forest",
    "nottm forest": "Nottingham Forest",
    "nottingham forest": "Nottingham Forest",
    "sheffield utd": "Sheffield United",
    "sheff utd": "Sheffield United",
    "spurs": "Tottenham Hotspur",
    "tottenham": "Tottenham Hotspur",
    "west ham": "West Ham United",
    "west ham utd": "West Ham United",
    "wolves": "Wolverhampton Wanderers",
    "wolverhampton": "Wolverhampton Wanderers",
    "sunderland": "Sunderland",
    "burnley": "Burnley",
}

NORMALIZED_CANONICAL = {
    re.sub(r"\s+", " ", name.lower().replace("&", "and")).strip(): name
    for name in CANONICAL_TEAMS
}


def _normalize_team_name(name: str) -> str:
    cleaned = name.lower().replace("&", "and")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _map_team_name(name: str) -> Optional[str]:
    normalized = _normalize_team_name(name)
    if normalized in TEAM_ALIASES:
        return TEAM_ALIASES[normalized]
    if normalized in NORMALIZED_CANONICAL:
        return NORMALIZED_CANONICAL[normalized]
    candidate = process.extractOne(
        normalized,
        list(NORMALIZED_CANONICAL.keys()),
    )
    if candidate and candidate[1] >= 84:
        return NORMALIZED_CANONICAL[candidate[0]]
    return None


def _stable_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    digits = re.sub(r"\D", "", text)
    if digits:
        return int(digits)
    return zlib.crc32(text.encode("utf-8")) % 1_000_000_000


def _season_start_year(season_code: str) -> int:
    code = str(season_code)
    if len(code) == 4 and code.isdigit():
        start = int(code[:2])
        end = int(code[2:])
        if (start + 1) % 100 == end % 100:
            century = 1900 if start > 80 else 2000
            return century + start
    if len(code) == 2 and code.isdigit():
        return 2000 + int(code)
    if len(code) == 4 and code.startswith("20"):
        return int(code)
    return 0


def _parse_match_date(value: str) -> Optional[date]:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if parsed <= 1:
        return None
    return parsed


def _download_csv(season: str, destination: Path, force: bool) -> None:
    if destination.exists() and not force:
        return
    url = f"{BASE_URL}/{season}/{LEAGUE_CODE}.csv"
    print(f"⬇️  Downloading {url}")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)


def _load_fixture_lookup(conn, season_year: int) -> dict[tuple[date, str, str], tuple[str, datetime]]:
    """Load fixtures from the fixtures table, keyed by (date, home_team, away_team)."""
    season_str = f"{season_year}-{season_year + 1}"
    query = """
        SELECT id, date, home_team, away_team
        FROM fixtures
        WHERE season = %s
    """
    lookup: dict[tuple[date, str, str], tuple[str, datetime]] = {}
    with conn.cursor() as cur:
        cur.execute(query, (season_str,))
        for fixture_id, fixture_date, home_team, away_team in cur.fetchall():
            if fixture_date is None:
                continue
            # Normalize team names for matching
            home_normalized = _map_team_name(home_team)
            away_normalized = _map_team_name(away_team)
            if home_normalized and away_normalized:
                # Use actual date (not datetime) for key
                match_date = fixture_date if isinstance(fixture_date, date) else fixture_date.date()
                # Create datetime at 15:00 for captured_at calculation
                fixture_datetime = datetime.combine(match_date, datetime.min.time().replace(hour=15))
                key = (match_date, home_normalized, away_normalized)
                lookup[key] = (fixture_id, fixture_datetime)
    return lookup


def _collect_odds(row: dict[str, str], columns_map: dict = None) -> dict[str, list[float]]:
    """Collect odds from specified bookmaker columns."""
    if columns_map is None:
        columns_map = BOOKMAKER_COLUMNS_OPEN
    odds: dict[str, list[float]] = {"HOME": [], "DRAW": [], "AWAY": []}
    for bookmaker, columns in columns_map.items():
        for selection, column in columns.items():
            value = row.get(column, "")
            parsed = _parse_decimal(value)
            if parsed is not None:
                odds[selection].append(parsed)
    return odds


def _collect_odds_open_close(row: dict[str, str]) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Collect both opening and closing odds."""
    open_odds = _collect_odds(row, BOOKMAKER_COLUMNS_OPEN)
    close_odds = _collect_odds(row, BOOKMAKER_COLUMNS_CLOSE)
    return open_odds, close_odds


def _average(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _insert_odds_snapshots(conn, payloads: list[dict[str, object]]) -> None:
    if not payloads:
        return
    query = """
        INSERT INTO odds_snapshots (
            fixture_id, market_key, selection_key, odds_decimal, captured_at, source, data_source
        )
        VALUES (
            %(fixture_id)s, %(market_key)s, %(selection_key)s, %(odds_decimal)s,
            %(captured_at)s, %(source)s, %(data_source)s
        )
    """
    with conn.cursor() as cur:
        cur.executemany(query, payloads)


def _process_season(csv_path: Path, season: str, conn) -> None:
    season_year = _season_start_year(season)
    fixture_lookup = _load_fixture_lookup(conn, season_year)
    if not fixture_lookup:
        print(f"❌ No fixtures found for season {season} in fixtures_historical.")
        return

    payloads: list[dict[str, object]] = []
    matched_fixtures: set[str] = set()
    total_rows = 0
    missing_rows = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row:
                continue
            total_rows += 1
            match_date = _parse_match_date(row.get("Date", ""))
            if match_date is None:
                missing_rows += 1
                continue

            home_raw = row.get("HomeTeam", "").strip()
            away_raw = row.get("AwayTeam", "").strip()
            if not home_raw or not away_raw:
                missing_rows += 1
                continue

            home_name = _map_team_name(home_raw)
            away_name = _map_team_name(away_raw)
            if not home_name or not away_name:
                print(f"⚠️  Unknown team mapping: {home_raw} vs {away_raw}")
                missing_rows += 1
                continue

            # Lookup by (date, home_name, away_name) - names already normalized
            fixture_key = (match_date, home_name, away_name)
            fixture_entry = fixture_lookup.get(fixture_key)
            if fixture_entry is None:
                missing_rows += 1
                continue

            fixture_id, fixture_datetime = fixture_entry
            if fixture_datetime is None:
                missing_rows += 1
                continue

            # Collect both opening and closing odds
            open_odds, close_odds = _collect_odds_open_close(row)

            open_averaged = {
                selection: _average(values) for selection, values in open_odds.items()
            }
            close_averaged = {
                selection: _average(values) for selection, values in close_odds.items()
            }

            # Need at least one valid odds value
            has_open = any(value is not None for value in open_averaged.values())
            has_close = any(value is not None for value in close_averaged.values())
            if not has_open and not has_close:
                missing_rows += 1
                continue

            # Opening odds: captured ~48h before kickoff (early price)
            open_captured_at = fixture_datetime - timedelta(hours=48)
            for selection, value in open_averaged.items():
                if value is None:
                    continue
                payloads.append(
                    {
                        "fixture_id": fixture_id,
                        "market_key": "1X2",
                        "selection_key": selection,
                        "odds_decimal": value,
                        "captured_at": open_captured_at,
                        "source": "football-data-open",
                        "data_source": "football-data",
                    }
                )

            # Closing odds: captured ~1h before kickoff
            close_captured_at = fixture_datetime - timedelta(hours=1)
            for selection, value in close_averaged.items():
                if value is None:
                    continue
                payloads.append(
                    {
                        "fixture_id": fixture_id,
                        "market_key": "1X2",
                        "selection_key": selection,
                        "odds_decimal": value,
                        "captured_at": close_captured_at,
                        "source": "football-data-close",
                        "data_source": "football-data",
                    }
                )
            matched_fixtures.add(fixture_id)

    print(
        f"Season {season}: rows={total_rows}, matched_fixtures={len(matched_fixtures)}, "
        f"missing={missing_rows}, odds_rows={len(payloads)}"
    )

    match_rate = (len(matched_fixtures) / total_rows * 100) if total_rows else 0.0
    if match_rate < 95:
        print(f"⚠️  Match rate below target: {match_rate:.1f}% (target 95%)")
    else:
        print(f"✅ Match rate: {match_rate:.1f}%")

    _insert_odds_snapshots(conn, payloads)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download EPL odds from Football-Data.co.uk.")
    parser.add_argument(
        "--seasons",
        nargs="*",
        default=DEFAULT_SEASONS,
        help="Season codes to download (default: 2122 2223 2324 2425).",
    )
    parser.add_argument(
        "--data-dir",
        default=str(PROJECT_ROOT / "data" / "football_data" / "odds"),
        help="Directory to store downloaded CSVs.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip CSV downloads if files already exist.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Force re-download of CSVs.",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip inserting odds into the database.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    csv_paths: dict[str, Path] = {}
    for season in args.seasons:
        csv_path = data_dir / f"{LEAGUE_CODE}_{season}.csv"
        if not args.skip_download:
            _download_csv(season, csv_path, args.force_download)
        if not csv_path.exists():
            print(f"❌ Missing CSV for season {season}: {csv_path}")
            return 1
        csv_paths[season] = csv_path

    if args.skip_db:
        print("Skipping DB insert (--skip-db).")
        return 0

    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to the database.")
        return 1

    try:
        for season, csv_path in csv_paths.items():
            _process_season(csv_path, season, conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"❌ Failed to import odds: {exc}")
        return 1
    finally:
        conn.close()

    print("✅ Odds download/import complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
