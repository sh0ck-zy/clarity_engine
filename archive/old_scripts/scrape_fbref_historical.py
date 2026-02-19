import argparse
import random
import re
import sys
import time
import zlib
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd
import soccerdata as sd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection

DEFAULT_LEAGUE = "ENG-Premier League"
DEFAULT_SEASONS = ["2122", "2223", "2324", "2425"]
LEAGUE_ID_MAP = {
    "ENG-Premier League": 1,
}
STAT_TYPES = {
    "standard": "standard",
    "shooting": "shooting",
    "possession": "possession",
    "misc": "misc",
}
PLAYER_STATS_FILENAME = "player_stats.json"


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


def load_cache(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    try:
        return pd.read_json(path)
    except ValueError as exc:
        print(f"   Failed to load cache {path}: {exc}")
        return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(col).strip().lower().replace(" ", "_") for col in df.columns]
    return df


def _normalize_value(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _extract_value(row: dict, keys: list[str]) -> Optional[object]:
    for key in keys:
        if key in row and pd.notna(row[key]):
            return row[key]
    for key, value in row.items():
        for candidate in keys:
            if candidate in key and pd.notna(value):
                return value
    return None


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
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _stable_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int,)):
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
    return _safe_int(code) or 0


def _league_id(league: str) -> int:
    return LEAGUE_ID_MAP.get(league, 0)


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


def fetch_player_stats(fbref: sd.FBref, season_dir: Path) -> None:
    print(" - Fetching player season stats...")
    try:
        stats = fbref.read_player_season_stats()
    except Exception as exc:
        print(f"   Failed to fetch player stats: {exc}")
        return
    if stats is None or stats.empty:
        print("   No player stats returned.")
        return
    write_cache(stats, season_dir / PLAYER_STATS_FILENAME)


def _build_fixture_id(row: dict, home_team: str, away_team: str, match_date: pd.Timestamp) -> str:
    fixture_id = _extract_value(row, ["fixture_id", "match_id", "game_id", "id"])
    fixture_id = _normalize_value(fixture_id)
    if fixture_id:
        return fixture_id
    date_str = match_date.strftime("%Y-%m-%d")
    safe_home = home_team.replace(" ", "_") if home_team else "home"
    safe_away = away_team.replace(" ", "_") if away_team else "away"
    return f"{date_str}_{safe_home}_{safe_away}"


def _build_team_stats_lookup(
    team_stats_frames: dict[str, Optional[pd.DataFrame]]
) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for stats_df in team_stats_frames.values():
        if stats_df is None or stats_df.empty:
            continue
        stats_df = _normalize_columns(stats_df)
        for _, row in stats_df.iterrows():
            row_dict = {str(k).lower(): v for k, v in row.items()}
            team_name = _extract_value(row_dict, ["team", "squad", "club"])
            team_name = _normalize_value(team_name)
            if not team_name:
                continue
            key = team_name.lower()
            payload = lookup.setdefault(key, {"team": team_name})
            matches = _safe_int(_extract_value(row_dict, ["mp", "matches", "games", "games_played"]))
            payload["matches"] = payload.get("matches") or matches
            xg = _safe_float(_extract_value(row_dict, ["xg", "npxg"]))
            xga = _safe_float(_extract_value(row_dict, ["xga", "npxga"]))
            shots = _safe_int(_extract_value(row_dict, ["sh", "shots"]))
            possession = _safe_float(_extract_value(row_dict, ["poss", "possession"]))
            ppda = _safe_float(_extract_value(row_dict, ["ppda"]))
            if xg is not None:
                payload["xg_total"] = xg
            if xga is not None:
                payload["xga_total"] = xga
            if shots is not None:
                payload["shots_total"] = shots
            if possession is not None:
                payload["possession"] = possession
            if ppda is not None:
                payload["ppda"] = ppda
    return lookup


def _per_match(value: Optional[float], matches: Optional[int]) -> Optional[float]:
    if value is None:
        return None
    if not matches:
        return value
    return float(value) / matches


def _extract_team_match_stats(
    row_dict: dict,
    team_role: str,
    team_lookup: dict[str, dict[str, object]],
    team_name: str,
) -> dict[str, Optional[float]]:
    role = team_role.lower()
    xg = _safe_float(
        _extract_value(
            row_dict,
            [f"{role}_xg", f"xg_{role}", f"{role}_expected_goals"],
        )
    )
    xga = _safe_float(
        _extract_value(
            row_dict,
            [f"{role}_xga", f"xga_{role}", f"{role}_expected_goals_against"],
        )
    )
    shots = _safe_int(
        _extract_value(
            row_dict,
            [f"{role}_shots", f"shots_{role}", f"{role}_sh"],
        )
    )
    possession = _safe_float(
        _extract_value(
            row_dict,
            [f"{role}_poss", f"poss_{role}", f"{role}_possession"],
        )
    )
    ppda = _safe_float(
        _extract_value(row_dict, [f"{role}_ppda", f"ppda_{role}"])
    )

    lookup = team_lookup.get(team_name.lower(), {})
    matches = _safe_int(lookup.get("matches"))
    if xg is None:
        xg = _per_match(_safe_float(lookup.get("xg_total")), matches)
    if xga is None:
        xga = _per_match(_safe_float(lookup.get("xga_total")), matches)
    if shots is None:
        shots_value = _per_match(_safe_float(lookup.get("shots_total")), matches)
        shots = _safe_int(shots_value)
    if possession is None:
        possession = _safe_float(lookup.get("possession"))
    if ppda is None:
        ppda = _safe_float(lookup.get("ppda"))

    return {
        "xg": xg,
        "xga": xga,
        "shots": shots,
        "possession": possession,
        "ppda": ppda,
    }


def _build_player_rows(
    player_df: Optional[pd.DataFrame],
    season: str,
    league: str,
) -> list[dict[str, object]]:
    if player_df is None or player_df.empty:
        return []
    player_df = _normalize_columns(player_df)
    rows: list[dict[str, object]] = []
    season_year = _season_start_year(season)
    league_id = _league_id(league)
    for _, row in player_df.iterrows():
        row_dict = {str(k).lower(): v for k, v in row.items()}
        player_name = _extract_value(row_dict, ["player", "player_name", "name"])
        player_id = _extract_value(row_dict, ["player_id", "fbref_id", "id", "player"])
        team_name = _extract_value(row_dict, ["team", "squad", "club"])
        position = _normalize_value(_extract_value(row_dict, ["pos", "position"]))
        minutes = _safe_int(_extract_value(row_dict, ["min", "minutes", "mins_played"]))
        xg = _safe_float(_extract_value(row_dict, ["xg", "npxg"]))
        xa = _safe_float(_extract_value(row_dict, ["xa", "xag", "xassists"]))
        shots = _safe_int(_extract_value(row_dict, ["sh", "shots"]))
        key_passes = _safe_int(_extract_value(row_dict, ["kp", "key_passes"]))
        progressive_passes = _safe_int(
            _extract_value(row_dict, ["prog", "progressive_passes", "prg_p"])
        )
        progressive_carries = _safe_int(
            _extract_value(row_dict, ["prog_carries", "progressive_carries", "prg_c"])
        )
        tackles = _safe_int(_extract_value(row_dict, ["tkl", "tackles"]))
        interceptions = _safe_int(_extract_value(row_dict, ["int", "interceptions"]))

        player_id = _stable_int(player_id or player_name)
        team_id = _stable_int(team_name)
        if not player_id or not team_id:
            continue

        rows.append(
            {
                "player_id": player_id,
                "team_id": team_id,
                "season": season_year,
                "league_id": league_id,
                "minutes": minutes,
                "position": position,
                "xg": xg,
                "xa": xa,
                "shots": shots,
                "key_passes": key_passes,
                "progressive_passes": progressive_passes,
                "progressive_carries": progressive_carries,
                "tackles": tackles,
                "interceptions": interceptions,
                "data_source": "fbref",
            }
        )
    return rows


def _insert_fixtures(conn, fixtures: list[dict[str, object]]) -> None:
    if not fixtures:
        print("   No fixtures to insert.")
        return
    query = """
        INSERT INTO fixtures_historical (
            fixture_id, league_id, season, round, date, venue,
            home_team_id, away_team_id, home_score, away_score, status, data_source
        )
        VALUES (
            %(fixture_id)s, %(league_id)s, %(season)s, %(round)s, %(date)s, %(venue)s,
            %(home_team_id)s, %(away_team_id)s, %(home_score)s, %(away_score)s,
            %(status)s, %(data_source)s
        )
        ON CONFLICT (fixture_id) DO UPDATE SET
            league_id = EXCLUDED.league_id,
            season = EXCLUDED.season,
            round = EXCLUDED.round,
            date = EXCLUDED.date,
            venue = EXCLUDED.venue,
            home_team_id = EXCLUDED.home_team_id,
            away_team_id = EXCLUDED.away_team_id,
            home_score = EXCLUDED.home_score,
            away_score = EXCLUDED.away_score,
            status = EXCLUDED.status,
            data_source = EXCLUDED.data_source,
            updated_at = NOW()
    """
    with conn.cursor() as cur:
        cur.executemany(query, fixtures)


def _insert_team_match_stats(conn, team_rows: list[dict[str, object]]) -> None:
    if not team_rows:
        print("   No team stats to insert.")
        return
    query = """
        INSERT INTO team_match_stats (
            fixture_id, team_id, is_home, season, league_id,
            xg, xga, shots, possession, ppda, data_source
        )
        VALUES (
            %(fixture_id)s, %(team_id)s, %(is_home)s, %(season)s, %(league_id)s,
            %(xg)s, %(xga)s, %(shots)s, %(possession)s, %(ppda)s, %(data_source)s
        )
        ON CONFLICT (fixture_id, team_id) DO UPDATE SET
            is_home = EXCLUDED.is_home,
            season = EXCLUDED.season,
            league_id = EXCLUDED.league_id,
            xg = EXCLUDED.xg,
            xga = EXCLUDED.xga,
            shots = EXCLUDED.shots,
            possession = EXCLUDED.possession,
            ppda = EXCLUDED.ppda,
            data_source = EXCLUDED.data_source,
            updated_at = NOW()
    """
    with conn.cursor() as cur:
        cur.executemany(query, team_rows)


def _insert_player_season_stats(conn, player_rows: list[dict[str, object]]) -> None:
    if not player_rows:
        print("   No player stats to insert.")
        return
    query = """
        INSERT INTO player_season_stats (
            player_id, team_id, season, league_id, minutes, position,
            xg, xa, shots, key_passes, progressive_passes, progressive_carries,
            tackles, interceptions, data_source
        )
        VALUES (
            %(player_id)s, %(team_id)s, %(season)s, %(league_id)s, %(minutes)s, %(position)s,
            %(xg)s, %(xa)s, %(shots)s, %(key_passes)s, %(progressive_passes)s,
            %(progressive_carries)s, %(tackles)s, %(interceptions)s, %(data_source)s
        )
        ON CONFLICT (player_id, season, league_id) DO UPDATE SET
            team_id = EXCLUDED.team_id,
            minutes = EXCLUDED.minutes,
            position = EXCLUDED.position,
            xg = EXCLUDED.xg,
            xa = EXCLUDED.xa,
            shots = EXCLUDED.shots,
            key_passes = EXCLUDED.key_passes,
            progressive_passes = EXCLUDED.progressive_passes,
            progressive_carries = EXCLUDED.progressive_carries,
            tackles = EXCLUDED.tackles,
            interceptions = EXCLUDED.interceptions,
            data_source = EXCLUDED.data_source,
            updated_at = NOW()
    """
    with conn.cursor() as cur:
        cur.executemany(query, player_rows)


def insert_cached_season(
    league: str,
    season: str,
    cache_dir: Path,
) -> None:
    season_dir = ensure_cache_dir(cache_dir, season)
    schedule_df = load_cache(season_dir / "fixtures_schedule.json")
    player_df = load_cache(season_dir / PLAYER_STATS_FILENAME)
    team_stats_frames = {
        label: load_cache(season_dir / f"team_stats_{label}.json")
        for label in STAT_TYPES
    }

    if schedule_df is None or schedule_df.empty:
        print("   No cached schedule data available for DB insert.")
        return

    schedule_df = _normalize_columns(schedule_df)
    team_lookup = _build_team_stats_lookup(team_stats_frames)

    fixtures: list[dict[str, object]] = []
    team_rows: list[dict[str, object]] = []

    season_year = _season_start_year(season)
    league_id = _league_id(league)

    for _, row in schedule_df.iterrows():
        row_dict = {str(k).lower(): v for k, v in row.items()}
        home_team = _normalize_value(_extract_value(row_dict, ["home", "home_team", "team_home"]))
        away_team = _normalize_value(_extract_value(row_dict, ["away", "away_team", "team_away"]))
        if not home_team or not away_team:
            continue

        date_value = _extract_value(row_dict, ["date", "match_date", "kickoff", "datetime"])
        if date_value is None:
            continue
        match_date = pd.to_datetime(str(date_value), errors="coerce")
        if pd.isna(match_date):
            continue

        fixture_id = _build_fixture_id(row_dict, home_team, away_team, match_date)
        venue = _normalize_value(_extract_value(row_dict, ["venue", "stadium"]))
        round_name = _normalize_value(_extract_value(row_dict, ["round", "week", "matchweek"]))
        home_score = _safe_int(
            _extract_value(row_dict, ["home_score", "home_goals", "gf_home", "home"])
        )
        away_score = _safe_int(
            _extract_value(row_dict, ["away_score", "away_goals", "gf_away", "away"])
        )
        status = _normalize_value(_extract_value(row_dict, ["status", "result"]))
        if not status:
            status = "FINISHED" if home_score is not None and away_score is not None else "SCHEDULED"

        home_team_id = _stable_int(home_team)
        away_team_id = _stable_int(away_team)

        fixtures.append(
            {
                "fixture_id": fixture_id,
                "league_id": league_id,
                "season": season_year,
                "round": round_name,
                "date": match_date.to_pydatetime(),
                "venue": venue,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "home_score": home_score,
                "away_score": away_score,
                "status": status,
                "data_source": "fbref",
            }
        )

        for team_name, is_home in ((home_team, True), (away_team, False)):
            metrics = _extract_team_match_stats(row_dict, "home" if is_home else "away", team_lookup, team_name)
            team_rows.append(
                {
                    "fixture_id": fixture_id,
                    "team_id": _stable_int(team_name),
                    "is_home": is_home,
                    "season": season_year,
                    "league_id": league_id,
                    "xg": metrics["xg"],
                    "xga": metrics["xga"],
                    "shots": metrics["shots"],
                    "possession": metrics["possession"],
                    "ppda": metrics["ppda"],
                    "data_source": "fbref",
                }
            )

    player_rows = _build_player_rows(player_df, season, league)

    print(f"   Parsed fixtures: {len(fixtures)}")
    print(f"   Parsed team stats rows: {len(team_rows)}")
    print(f"   Parsed player stats rows: {len(player_rows)}")

    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to the database.")
        return

    try:
        _insert_fixtures(conn, fixtures)
        _insert_team_match_stats(conn, team_rows)
        _insert_player_season_stats(conn, player_rows)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"❌ DB insertion failed: {exc}")
        return
    finally:
        conn.close()

    fixtures_with_stats = len({row["fixture_id"] for row in team_rows})
    expected_team_rows = len(fixtures) * 2
    completeness = 0.0
    if expected_team_rows:
        completeness = min(100.0, (fixtures_with_stats / len(fixtures)) * 100)

    print(
        "   Validation: "
        f"fixtures_count={len(fixtures)}, "
        f"teams_count={len(team_rows)}, "
        f"players_count={len(player_rows)}, "
        f"completeness={completeness:.1f}%"
    )


def scrape_season(
    league: str,
    season: str,
    cache_dir: Path,
    min_delay: float,
    max_delay: float,
    insert_db: bool,
) -> None:
    print(f"\nSeason {season} - League {league}")
    fbref = sd.FBref(leagues=league, seasons=season)
    season_dir = ensure_cache_dir(cache_dir, season)

    fetch_schedule(fbref, season_dir)
    sleep_with_jitter(min_delay, max_delay)

    fetch_team_stats(fbref, season_dir)
    sleep_with_jitter(min_delay, max_delay)

    fetch_player_stats(fbref, season_dir)
    sleep_with_jitter(min_delay, max_delay)

    if insert_db:
        print(" - Inserting cached data into database...")
        insert_cached_season(league, season, cache_dir)


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
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip inserting cached data into the database.",
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
            not args.skip_db,
        )

    print("\nDone. Cached data is ready for DB insertion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
