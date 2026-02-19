"""
Add position column to player_injuries_historical table.

This migration adds a TEXT column to store player positions (GK, CB, LW, etc.)
for injury records, replacing the hardcoded default of "MF".
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection


def add_position_column():
    """Add position column to player_injuries_historical table."""
    conn = get_connection()
    cur = conn.cursor()

    try:
        print("Adding position column to player_injuries_historical...")

        # Add position column if it doesn't exist
        cur.execute("""
            ALTER TABLE player_injuries_historical
            ADD COLUMN IF NOT EXISTS position TEXT;
        """)

        conn.commit()
        print("✓ Successfully added position column to player_injuries_historical")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error adding position column: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    add_position_column()
