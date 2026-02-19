import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from data.feature_engineering import derive_form_features, derive_rest_features
from database.config import get_connection

load_dotenv()


def fetch_fixture_ids(conn, season: int) -> list[str]:
    query = """
        SELECT fixture_id
        FROM fixtures_historical
        WHERE season = %s
        ORDER BY date
    """
    with conn.cursor() as cur:
        cur.execute(query, (season,))
        return [row[0] for row in cur.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive match rest and form features.")
    parser.add_argument("--season", type=int, required=True, help="Season year (e.g. 2023).")
    args = parser.parse_args()

    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to the database.")
        return 1

    try:
        fixture_ids = fetch_fixture_ids(conn, args.season)
        if not fixture_ids:
            print(f"⚠️  No fixtures found for season {args.season}.")
            return 0

        print(
            f"✅ Deriving rest + form features for {len(fixture_ids)} fixtures in {args.season}..."
        )
        for index, fixture_id in enumerate(fixture_ids, start=1):
            derive_rest_features(fixture_id, conn=conn)
            derive_form_features(fixture_id, conn=conn)
            if index % 50 == 0:
                print(f"   Processed {index}/{len(fixture_ids)} fixtures")

        print("✅ Rest + form features stored in match_features.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
