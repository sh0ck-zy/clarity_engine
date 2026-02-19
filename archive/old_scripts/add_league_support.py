
"""
Migration script to add league support to fixtures table.
Run this to add the league column to your database.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from database.config import get_connection
from dotenv import load_dotenv

load_dotenv()


def add_league_column():
    """Add league column to fixtures table."""
    print("🛠️  Adding league support to fixtures table...")
    
    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to the database.")
        return False
    
    try:
        with conn.cursor() as cur:
            # Check if column exists
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='fixtures' AND column_name='league'
            """)
            exists = cur.fetchone()
            
            if not exists:
                # Add league column with default value
                cur.execute("""
                    ALTER TABLE fixtures 
                    ADD COLUMN league TEXT DEFAULT 'Premier League'
                """)
                
                # Update existing rows to have Premier League as default
                cur.execute("""
                    UPDATE fixtures 
                    SET league = 'Premier League' 
                    WHERE league IS NULL
                """)
                
                # Create index for performance
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_fixtures_league 
                    ON fixtures(league)
                """)
                
                print("✅ League column added successfully.")
                print("✅ Index created.")
            else:
                print("ℹ️  League column already exists.")
            
        conn.commit()
        return True
        
    except Exception as e:
        print(f"❌ Error adding league column: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = add_league_column()
    sys.exit(0 if success else 1)






