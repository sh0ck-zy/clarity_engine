import argparse
import csv
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection

BASE_URL = "https://raw.githubusercontent.com/salimt/football-datasets/main/datalake/transfermarkt/raw"
DATA_PATH = "player_market_values/player_market_values"


def _parse_int(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    return int(digits)


def _parse_date(value, fmt="%Y-%m-%d"):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    try:
        return datetime.strptime(text, fmt).date()
    except ValueError:
        return None


def _download_file(url, destination, force):
    if destination.exists() and not force:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} -> {destination}")
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        handle.write(response.read())


def _load_csv(path):
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


def _ensure_table(conn):
    sql = """
        CREATE TABLE IF NOT EXISTS player_market_values (
            player_id INT NOT NULL,
            market_value_eur DECIMAL(12,2),
            valuation_date DATE NOT NULL,
            data_source TEXT NOT NULL,
            ingested_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (player_id, valuation_date)
        )
    """
    with conn.cursor() as cur:
        cur.execute(sql)


def _prepare_rows(rows):
    prepared = []
    skipped = 0
    for row in rows:
        player_id = _parse_int(row.get("player_id"))
        if not player_id:
            skipped += 1
            continue
        valuation_date = _parse_date(row.get("date_unix") or row.get("date"))
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


def _insert_rows(conn, rows):
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


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Import Transfermarkt player market values into Postgres.")
    parser.add_argument(
        "--data-dir",
        default=str(PROJECT_ROOT / "data" / "transfermarkt"),
        help="Directory to store/download Transfermarkt CSV files.",
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
    return parser.parse_args(list(argv))


def main(argv):
    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    url = f"{BASE_URL}/{DATA_PATH}"
    destination = data_dir / Path(DATA_PATH).name
    _download_file(url, destination, args.force_download)
    if not destination.exists():
        print(f"Missing required file: {destination}")
        return 1

    rows = _load_csv(destination)
    prepared, skipped = _prepare_rows(rows)
    print(f"Prepared market values: {len(prepared)} (skipped {skipped})")

    if args.skip_db:
        print("Skipping DB insertion (--skip-db).")
        return 0

    conn = get_connection()
    if conn is None:
        print("Could not connect to database.")
        return 1

    try:
        _ensure_table(conn)
        inserted = _insert_rows(conn, prepared)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"DB insert failed: {exc}")
        return 1
    finally:
        conn.close()

    print(f"Import complete: market_values={inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
