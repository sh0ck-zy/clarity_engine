import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from database.config import get_connection

SCHEMA_PATH = SRC_PATH / "database" / "schema.sql"

load_dotenv()


def setup_schema():
    print("🛠️  Setting up V1 Database Schema...")
    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to the database.")
        return

    sql_text = SCHEMA_PATH.read_text()
    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.commit()
    conn.close()
    print("✅ Schema created successfully.")


if __name__ == "__main__":
    setup_schema()
