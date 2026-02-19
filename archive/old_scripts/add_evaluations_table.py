"""
Migration script to add analysis_evaluations table.
Run this to add the evaluation tracking table to your database.
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


def create_evaluations_table():
    """Create the analysis_evaluations table."""
    print("🛠️  Creating analysis_evaluations table...")
    
    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to the database.")
        return False
    
    # First, ensure match_reality table exists (it might not be in schema.sql if created separately)
    create_match_reality_if_not_exists = """
    CREATE TABLE IF NOT EXISTS match_reality (
        fixture_id TEXT PRIMARY KEY REFERENCES fixtures(id) ON DELETE CASCADE,
        score_home INT,
        score_away INT,
        xg_home DECIMAL(4,2),
        xg_away DECIMAL(4,2),
        possession_home DECIMAL(4,1),
        key_events JSONB,
        narrative_summary TEXT,
        luck_factor TEXT,
        source_type TEXT DEFAULT 'forensic_auditor',
        created_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    create_evaluations_table_sql = """
    CREATE TABLE IF NOT EXISTS analysis_evaluations (
        id SERIAL PRIMARY KEY,
        report_id INT NOT NULL UNIQUE REFERENCES analysis_reports(id) ON DELETE CASCADE,
        fixture_id TEXT NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
        prompt_version TEXT NOT NULL,
        
        -- Dimensão 1: Narrative Quality
        narrative_score INT, -- 0-100
        narrative_feedback TEXT,
        narrative_critical_flags JSONB, -- ["missed_key_event", "overemphasized_factor"]
        
        -- Dimensão 2: Score Prediction
        score_accuracy BOOLEAN,
        score_explanation TEXT,
        
        -- Dimensão 3: Betting Tip
        tip_accuracy BOOLEAN,
        tip_explanation TEXT,
        
        -- Meta
        evaluation_json JSONB, -- Full response
        created_at TIMESTAMP DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_evaluations_fixture ON analysis_evaluations(fixture_id);
    CREATE INDEX IF NOT EXISTS idx_evaluations_prompt ON analysis_evaluations(prompt_version);
    CREATE INDEX IF NOT EXISTS idx_evaluations_report ON analysis_evaluations(report_id);
    """
    
    try:
        with conn.cursor() as cur:
            # Create match_reality if it doesn't exist
            cur.execute(create_match_reality_if_not_exists)
            
            # Create analysis_evaluations table
            cur.execute(create_evaluations_table_sql)
            
        conn.commit()
        print("✅ analysis_evaluations table created successfully.")
        print("✅ Indexes created.")
        return True
        
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = create_evaluations_table()
    sys.exit(0 if success else 1)

