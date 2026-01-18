import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from database.config import get_connection

load_dotenv()

REQUIRED_COLUMNS = {
    "fixture_id",
    "market_key",
    "selection_key",
    "odds_decimal",
    "captured_at",
}


class OddsImportError(Exception):
    pass


class TimeTravelViolationError(OddsImportError):
    """Raised when odds are captured after the fixture date (time-travel violation)."""
    pass


def parse_timestamp(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise OddsImportError(f"Invalid captured_at timestamp: {value}")


def load_rows(csv_path: Path) -> Iterable[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise OddsImportError("CSV has no headers")
        missing = REQUIRED_COLUMNS.difference({name.strip() for name in reader.fieldnames})
        if missing:
            raise OddsImportError(f"CSV missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            if not any(value.strip() for value in row.values() if value is not None):
                continue
            yield {key.strip(): (value.strip() if value is not None else "") for key, value in row.items()}


def fetch_fixture_kickoffs(conn, fixture_ids: Iterable[str]) -> Dict[str, datetime]:
    fixture_ids = [fid for fid in fixture_ids if fid]
    if not fixture_ids:
        return {}
    query = "SELECT id, date FROM fixtures WHERE id = ANY(%s)"
    with conn.cursor() as cur:
        cur.execute(query, (fixture_ids,))
        rows = cur.fetchall()
    return {row[0]: row[1] for row in rows}


def normalize_kickoff(kickoff: datetime) -> datetime:
    if isinstance(kickoff, datetime):
        return kickoff
    return datetime.combine(kickoff, datetime.min.time())


def validate_row_time_travel(row: Dict[str, str], fixture_dates: Dict[str, datetime]) -> None:
    """
    Validate that odds were captured BEFORE the fixture kickoff.

    Raises TimeTravelViolationError if odds captured_at >= fixture date.
    This is critical - using future data makes all validation worthless.
    """
    fixture_id = row["fixture_id"]
    captured_at = parse_timestamp(row["captured_at"])

    if fixture_id not in fixture_dates:
        raise OddsImportError(f"Unknown fixture: {fixture_id}")

    fixture_date = normalize_kickoff(fixture_dates[fixture_id])

    # Critical check: odds must be captured BEFORE kickoff
    if captured_at >= fixture_date:
        raise TimeTravelViolationError(
            f"TIME TRAVEL VIOLATION: Odds for {fixture_id} were captured at {captured_at} "
            f"but fixture kickoff is {fixture_date}. "
            f"Odds MUST be captured BEFORE the match starts! "
            f"This makes all validation results worthless."
        )


def parse_decimal(value: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise OddsImportError(f"Invalid odds_decimal value: {value}") from exc


def insert_snapshot(conn, payload: Dict[str, object]) -> None:
    query = """
        INSERT INTO odds_snapshots (
            fixture_id, market_key, selection_key, odds_decimal, captured_at, source
        )
        VALUES (%(fixture_id)s, %(market_key)s, %(selection_key)s, %(odds_decimal)s,
                %(captured_at)s, %(source)s)
    """
    with conn.cursor() as cur:
        cur.execute(query, payload)


def import_odds(csv_path: Path, default_source: Optional[str] = None) -> None:
    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to the database.")
        return

    try:
        rows = list(load_rows(csv_path))
        fixture_ids = {row["fixture_id"] for row in rows}
        fixture_dates = fetch_fixture_kickoffs(conn, fixture_ids)

        inserted = 0
        rejected = 0

        for row in rows:
            # Validate time-travel correctness
            try:
                validate_row_time_travel(row, fixture_dates)
            except TimeTravelViolationError as e:
                print(f"❌ TIME TRAVEL VIOLATION: {e}")
                print(f"   Skipping row to prevent validation contamination.")
                rejected += 1
                continue
            except OddsImportError as e:
                print(f"⚠️  Row validation error: {e}. Skipping.")
                rejected += 1
                continue

            odds_decimal = parse_decimal(row["odds_decimal"])
            if odds_decimal <= 1:
                print(
                    "⚠️  Odds decimal must be > 1 for "
                    f"fixture_id={fixture_id} value={row['odds_decimal']}. Skipping row."
                )
                rejected += 1
                continue

            payload = {
                "fixture_id": fixture_id,
                "market_key": row.get("market_key") or "1X2",
                "selection_key": row.get("selection_key") or "UNKNOWN",
                "odds_decimal": odds_decimal,
                "captured_at": captured_at,
                "source": row.get("source") or default_source or "manual_csv",
            }

            try:
                insert_snapshot(conn, payload)
                inserted += 1
            except Exception as exc:
                conn.rollback()
                print(f"❌ Failed to insert odds for fixture_id={fixture_id}: {exc}")
                rejected += 1
            else:
                conn.commit()

        print(f"✅ Imported odds snapshots: {inserted}")
        if rejected:
            print(f"⚠️  Rejected rows: {rejected}")

    except OddsImportError as exc:
        print(f"❌ {exc}")
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python scripts/import_odds_csv.py <csv_path> [source]")
        return 1

    csv_path = Path(argv[1])
    if not csv_path.exists():
        print(f"❌ CSV not found at {csv_path}")
        return 1

    default_source = argv[2] if len(argv) > 2 else None
    import_odds(csv_path, default_source=default_source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
