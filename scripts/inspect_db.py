import sys
from pathlib import Path
from psycopg2 import sql

# Ensure project root is on path so we can import db config
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from database.config import get_connection


def truncate_value(value, max_len=80):
    """Render values as readable strings and truncate long blobs."""
    text = str(value)
    return text if len(text) <= max_len else text[:max_len] + "..."


def fetch_columns(conn, table_name):
    query = """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """
    with conn.cursor() as cur:
        cur.execute(query, (table_name,))
        rows = cur.fetchall()
        return rows


def inspect_table(conn, table_name):
    print(f"\n========= TABLE: {table_name} =========")

    try:
        cols = fetch_columns(conn, table_name)
        if not cols:
            print("Columns: (none found)")
        else:
            print("Columns:")
            for col_name, data_type, is_nullable in cols:
                print(f" - {col_name}: {data_type} (nullable: {is_nullable})")
    except Exception as e:
        print(f"Error fetching columns: {e}")
        return

    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name)))
            row_count = cur.fetchone()[0]
        print(f"Row count: {row_count}")
    except Exception as e:
        print(f"Error counting rows: {e}")
        return

    if row_count == 0:
        print("Sample rows: (table is empty)")
        return

    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT * FROM {} LIMIT 5").format(sql.Identifier(table_name))
            )
            rows = cur.fetchall()
            col_names = [desc[0] for desc in cur.description]

        print("Sample rows (up to 5):")
        for idx, row in enumerate(rows, start=1):
            rendered = {
                col: truncate_value(row[pos])
                for pos, col in enumerate(col_names)
            }
            print(f" - Row {idx}: {rendered}")
    except Exception as e:
        print(f"Error fetching sample rows: {e}")


def inspect_database():
    conn = get_connection()
    if not conn:
        print("❌ DB Connection Failed")
        return

    print("\n📊 FULL DATABASE INSPECTION")
    print("===========================")

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                ORDER BY tablename
                """
            )
            tables = [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"❌ Could not list tables: {e}")
        conn.close()
        return

    if not tables:
        print("⚠️ No tables found in public schema.")
        conn.close()
        return

    print(f"Found {len(tables)} tables.")
    for table_name in tables:
        inspect_table(conn, table_name)

    conn.close()
    print("\n✅ Inspection complete.")


if __name__ == "__main__":
    inspect_database()
