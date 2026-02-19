"""
Configuration for Clarity Sports Agent.
"""

import os

# Database
DB_CONFIG = {
    "dbname": os.getenv("CLARITY_DB_NAME", "clarity_football"),
    "user": os.getenv("CLARITY_DB_USER", "joao"),
    "host": os.getenv("CLARITY_DB_HOST", "localhost"),
    "port": os.getenv("CLARITY_DB_PORT", "5432"),
}

# FotMob League IDs
LEAGUE_IDS = {
    "premier_league": 47,
    "la_liga": 87,
    "serie_a": 55,
    "bundesliga": 54,
    "ligue_1": 53,
    "liga_portugal": 61,
    "eredivisie": 57,
    "champions_league": 42,
}

# Default league
DEFAULT_LEAGUE_ID = 47  # Premier League

# Current season
CURRENT_SEASON = "2025/2026"
