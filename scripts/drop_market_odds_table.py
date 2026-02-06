"""
Drop the legacy market_odds table.

The market_odds table is empty and redundant with the odds_snapshots table.
This script safely drops it after user confirmation.

Comparison:
- market_odds: Simple structure, one row per fixture, single provider, no timestamps
- odds_snapshots: Granular, multiple snapshots, multiple markets, source tracking, time-travel safe

Current usage:
- All ingestion scripts use odds_snapshots
- market_odds is not referenced in active code
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection


def drop_market_odds():
    """Drop the market_odds table from the database."""
    conn = get_connection()
    cur = conn.cursor()

    try:
        print("Dropping market_odds table...")

        # Drop table with CASCADE in case there are any foreign keys
        cur.execute("DROP TABLE IF EXISTS market_odds CASCADE;")

        conn.commit()
        print("✓ Successfully dropped market_odds table")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error dropping market_odds table: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("WARNING: This will permanently drop the market_odds table")
    print("="*60)
    print("\nReason: Table is empty and redundant with odds_snapshots")
    print("Impact: No data loss (table is empty)")
    print("Rollback: Can be recreated from schema.sql if needed\n")

    response = input("Are you sure you want to drop market_odds table? (yes/no): ")

    if response.lower() == 'yes':
        drop_market_odds()
        print("\n✓ Operation completed successfully\n")
    else:
        print("\n✗ Operation aborted\n")
