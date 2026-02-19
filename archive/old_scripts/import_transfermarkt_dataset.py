import argparse
import csv
import json
import re
import sys
import unicodedata
import urllib.request
import zlib
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from rapidfuzz import fuzz, process

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection

BASE_URL = "https://raw.githubusercontent.com/salimt/football-datasets/main/datalake/transfermarkt/raw"
DATA_FILES = {
    "market_values": "player_market_values/player_market_values",
    "injury_histories": "player_injury_histories/player_injury_histories",
    "player_profiles": "player_profiles/player_profiles",
}


def _normalize_columns(row: dict) -> dict:
    return {
        str(key).strip().lower().replace(" ", "_"): value
        for key, value in row.items()
    }


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    normalized = unicodedata.normalize("NFKD", name)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"\([^\)]*\)", "", normalized)
    normalized = re.sub(r"[^a-zA-Z\s-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


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


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    return int(digits)


def _parse_date(value: Optional[str], fmt: str) -> Optional[datetime.date]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    try:
        return datetime.strptime(text, fmt).date()
    except ValueError:
        return None


def _download_file(url: str, destination: Path, force: bool) -> None:
    if destination.exists() and not force:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"⬇️  Downloading {url} -> {destination}")
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        handle.write(response.read())


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            if not row:
                continue
            cleaned = {key.strip(): (value.strip() if value is not None else "") for key, value in row.items()}
            if any(cleaned.values()):
                rows.append(cleaned)
        return rows


def _load_fbref_players(cache_dir: Path) -> tuple[dict[str, int], dict[str, str]]:
    name_counts: dict[str, dict[int, int]] = {}
    display_names: dict[str, str] = {}
    for path in cache_dir.glob("**/player_stats.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, list):
            continue
        for row in data:
            if not isinstance(row, dict):
                continue
            row = _normalize_columns(row)
            name = row.get("player") or row.get("player_name") or row.get("name")
            name = name.strip() if isinstance(name, str) else None
            if not name:
                continue
            raw_id = row.get("player_id") or row.get("fbref_id") or row.get("id") or row.get("player")
            player_id = _stable_int(raw_id or name)
            if not player_id:
                continue
            normalized = _normalize_name(name)
            if not normalized:
                continue
            bucket = name_counts.setdefault(normalized, {})
            bucket[player_id] = bucket.get(player_id, 0) + 1
            display_names.setdefault(normalized, name)
    name_to_id: dict[str, int] = {}
    for normalized, counts in name_counts.items():
        best_id = max(counts.items(), key=lambda item: item[1])[0]
        name_to_id[normalized] = best_id
    return name_to_id, display_names


def _build_transfermarkt_profiles(rows: list[dict[str, str]]) -> dict[int, str]:
    profiles: dict[int, str] = {}
    for row in rows:
        row = _normalize_columns(row)
        player_id = _parse_int(row.get("player_id"))
        if not player_id:
            continue
        name = row.get("player_name") or row.get("name") or row.get("player")
        if not name:
            continue
        profiles[player_id] = name
    return profiles


def _match_players(
    player_ids: Iterable[int],
    tm_profiles: dict[int, str],
    fbref_names: list[str],
    fbref_ids: dict[str, int],
    fbref_display: dict[str, str],
    min_score: int,
) -> tuple[dict[int, dict[str, object]], list[dict[str, object]]]:
    matched: dict[int, dict[str, object]] = {}
    report_rows: list[dict[str, object]] = []
    for tm_id in sorted(player_ids):
        tm_name = tm_profiles.get(tm_id)
        if not tm_name:
            report_rows.append(
                {
                    "transfermarkt_player_id": tm_id,
                    "transfermarkt_name": "",
                    "fbref_player_id": "",
                    "fbref_name": "",
                    "match_score": "",
                    "match_type": "missing_name",
                }
            )
            continue
        normalized = _normalize_name(tm_name)
        match_type = ""
        fbref_id = None
        fbref_name = None
        score = None
        if normalized in fbref_ids:
            fbref_id = fbref_ids[normalized]
            fbref_name = fbref_display.get(normalized, tm_name)
            score = 100
            match_type = "exact"
        else:
            candidate = process.extractOne(
                normalized,
                fbref_names,
                scorer=fuzz.token_sort_ratio,
            )
            if candidate:
                candidate_name, candidate_score, _ = candidate
                if candidate_score >= min_score:
                    fbref_id = fbref_ids.get(candidate_name)
                    fbref_name = fbref_display.get(candidate_name)
                    score = int(candidate_score)
                    match_type = "fuzzy"
        if fbref_id:
            matched[tm_id] = {
                "fbref_player_id": fbref_id,
                "fbref_name": fbref_name,
                "score": score,
                "match_type": match_type,
            }
        report_rows.append(
            {
                "transfermarkt_player_id": tm_id,
                "transfermarkt_name": tm_name,
                "fbref_player_id": fbref_id or "",
                "fbref_name": fbref_name or "",
                "match_score": score or "",
                "match_type": match_type or "unmatched",
            }
        )
    return matched, report_rows


def _write_report(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "transfermarkt_player_id",
        "transfermarkt_name",
        "fbref_player_id",
        "fbref_name",
        "match_score",
        "match_type",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _insert_market_values(conn, rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0
    query = """
        INSERT INTO player_market_values (
            player_id, market_value_eur, valuation_date, data_source
        )
        VALUES (%(player_id)s, %(market_value_eur)s, %(valuation_date)s, %(data_source)s)
        ON CONFLICT (player_id, valuation_date) DO UPDATE SET
            market_value_eur = EXCLUDED.market_value_eur,
            data_source = EXCLUDED.data_source,
            updated_at = NOW()
    """
    with conn.cursor() as cur:
        cur.executemany(query, rows)
    return len(rows)


def _insert_injury_histories(conn, rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0
    query = """
        INSERT INTO player_injuries_historical (
            player_id, season, injury_reason, from_date, end_date,
            days_missed, games_missed, data_source
        )
        VALUES (
            %(player_id)s, %(season)s, %(injury_reason)s, %(from_date)s, %(end_date)s,
            %(days_missed)s, %(games_missed)s, %(data_source)s
        )
        ON CONFLICT (player_id, from_date, injury_reason) DO UPDATE SET
            end_date = EXCLUDED.end_date,
            days_missed = EXCLUDED.days_missed,
            games_missed = EXCLUDED.games_missed,
            data_source = EXCLUDED.data_source,
            updated_at = NOW()
    """
    with conn.cursor() as cur:
        cur.executemany(query, rows)
    return len(rows)


def _prepare_market_rows(
    rows: list[dict[str, str]],
    mapping: dict[int, dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    prepared: list[dict[str, object]] = []
    skipped = 0
    for row in rows:
        row = _normalize_columns(row)
        tm_id = _parse_int(row.get("player_id"))
        if not tm_id or tm_id not in mapping:
            skipped += 1
            continue
        player_id = mapping[tm_id]["fbref_player_id"]
        date_value = row.get("date_unix") or row.get("date")
        valuation_date = _parse_date(date_value, "%Y-%m-%d")
        if not valuation_date:
            skipped += 1
            continue
        market_value = _parse_int(row.get("value"))
        if market_value is None:
            skipped += 1
            continue
        prepared.append(
            {
                "player_id": player_id,
                "market_value_eur": market_value,
                "valuation_date": valuation_date,
                "data_source": "transfermarkt",
            }
        )
    return prepared, skipped


def _prepare_injury_rows(
    rows: list[dict[str, str]],
    mapping: dict[int, dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    prepared: list[dict[str, object]] = []
    skipped = 0
    for row in rows:
        row = _normalize_columns(row)
        tm_id = _parse_int(row.get("player_id"))
        if not tm_id or tm_id not in mapping:
            skipped += 1
            continue
        player_id = mapping[tm_id]["fbref_player_id"]
        season = row.get("season") or ""
        injury_reason = row.get("injury_reason") or row.get("injury") or ""
        from_date = _parse_date(row.get("from_date"), "%d.%m.%Y")
        if not from_date:
            skipped += 1
            continue
        end_date = _parse_date(row.get("end_date"), "%d.%m.%Y")
        days_missed = _parse_int(row.get("days_missed"))
        games_missed = _parse_int(row.get("games_missed"))
        prepared.append(
            {
                "player_id": player_id,
                "season": season,
                "injury_reason": injury_reason.strip() if injury_reason else None,
                "from_date": from_date,
                "end_date": end_date,
                "days_missed": days_missed,
                "games_missed": games_missed,
                "data_source": "transfermarkt",
            }
        )
    return prepared, skipped


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Transfermarkt datasets into Postgres.")
    parser.add_argument(
        "--data-dir",
        default=str(PROJECT_ROOT / "data" / "transfermarkt"),
        help="Directory to store/download Transfermarkt CSV files.",
    )
    parser.add_argument(
        "--fbref-cache-dir",
        default=str(PROJECT_ROOT / "data" / "fbref_cache"),
        help="Directory containing FBref cached player stats.",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=86,
        help="Minimum fuzzy match score to accept mapping.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip downloading Transfermarkt data if already present.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Force re-download of Transfermarkt data.",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip inserting data into the database.",
    )
    parser.add_argument(
        "--report-path",
        default=str(PROJECT_ROOT / "data" / "transfermarkt" / "player_mapping_report.csv"),
        help="Output path for player mapping report.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    fbref_cache = Path(args.fbref_cache_dir)

    for label, remote_path in DATA_FILES.items():
        url = f"{BASE_URL}/{remote_path}"
        destination = data_dir / Path(remote_path).name
        if not args.skip_download:
            _download_file(url, destination, args.force_download)
        if not destination.exists():
            print(f"❌ Missing required file: {destination}")
            return 1

    profiles_path = data_dir / Path(DATA_FILES["player_profiles"]).name
    market_values_path = data_dir / Path(DATA_FILES["market_values"]).name
    injury_path = data_dir / Path(DATA_FILES["injury_histories"]).name

    print("Loading Transfermarkt files...")
    profiles_rows = _load_csv(profiles_path)
    market_rows = _load_csv(market_values_path)
    injury_rows = _load_csv(injury_path)

    tm_profiles = _build_transfermarkt_profiles(profiles_rows)
    tm_ids = {
        *{_parse_int(row.get("player_id")) for row in market_rows},
        *{_parse_int(row.get("player_id")) for row in injury_rows},
    }
    tm_ids = {pid for pid in tm_ids if pid}

    print("Building FBref player index...")
    fbref_ids, fbref_display = _load_fbref_players(fbref_cache)
    fbref_names = list(fbref_ids.keys())
    if not fbref_names:
        print("❌ No FBref cache data found. Run scripts/scrape_fbref_historical.py first.")
        return 1

    print("Matching Transfermarkt players to FBref IDs...")
    mapping, report_rows = _match_players(
        tm_ids, tm_profiles, fbref_names, fbref_ids, fbref_display, args.min_score
    )
    report_path = Path(args.report_path)
    _write_report(report_path, report_rows)

    match_rate = (len(mapping) / len(tm_ids) * 100) if tm_ids else 0.0
    print(
        f"Matched {len(mapping)} / {len(tm_ids)} players ({match_rate:.1f}%). "
        f"Report saved to {report_path}"
    )

    market_prepared, market_skipped = _prepare_market_rows(market_rows, mapping)
    injury_prepared, injury_skipped = _prepare_injury_rows(injury_rows, mapping)

    print(
        "Prepared rows: "
        f"market_values={len(market_prepared)} (skipped {market_skipped}), "
        f"injuries={len(injury_prepared)} (skipped {injury_skipped})"
    )

    if args.skip_db:
        print("Skipping DB insertion (--skip-db).")
        return 0

    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to the database.")
        return 1

    try:
        inserted_market = _insert_market_values(conn, market_prepared)
        inserted_injuries = _insert_injury_histories(conn, injury_prepared)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"❌ DB insert failed: {exc}")
        return 1
    finally:
        conn.close()

    print(
        "✅ Import complete: "
        f"market_values={inserted_market}, injuries={inserted_injuries}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
