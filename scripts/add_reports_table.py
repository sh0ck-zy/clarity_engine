import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from database.config import get_connection

def add_table():
    print("📦 Adding 'analysis_reports' table to database...")
    conn = get_connection()
    if not conn: return

    sql = """
    CREATE TABLE IF NOT EXISTS analysis_reports (
        id SERIAL PRIMARY KEY,
        fixture_id TEXT REFERENCES fixtures(id) ON DELETE CASCADE,
        
        -- Metadata
        prompt_version TEXT NOT NULL,     -- e.g. "hybrid", "contrarian"
        model_name TEXT NOT NULL,         -- e.g. "gpt-4o"
        created_at TIMESTAMP DEFAULT NOW(),
        
        -- Outputs (Structured for fast SQL queries)
        headline TEXT,
        predicted_score TEXT,
        confidence INT,
        betting_recommendation TEXT,
        
        -- Logic Storage (For Glass Box transparency)
        weights JSONB,
        
        -- The Full Payload (Crucial for the Dashboard to re-render)
        full_json JSONB,
        
        -- Validation (Filled later)
        actual_score TEXT,
        is_correct BOOLEAN,
        pnl DECIMAL(6,2)
    );

    -- Add Indexes for speed
    CREATE INDEX IF NOT EXISTS idx_reports_fixture ON analysis_reports(fixture_id);
    CREATE INDEX IF NOT EXISTS idx_reports_version ON analysis_reports(prompt_version);
    """
    
    try:
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        print("✅ Success! Table 'analysis_reports' is ready.")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_table()