import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_connection():
    """
    Creates a new connection to the Postgres database.
    Returns: psycopg2 connection object or None if failed.
    """
    try:
        # Check if URL exists
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            # Fallback for manual config if .env is missing/broken
            return psycopg2.connect(
                dbname="clarity_football",
                user="postgres",
                password="password", # Update if needed
                host="localhost",
                port="5432"
            )
            
        return psycopg2.connect(db_url)
    except Exception as e:
        print(f"❌ DATABASE CONNECTION ERROR: {e}")
        return None