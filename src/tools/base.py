"""
Base utilities for agent tools.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Generator
from decimal import Decimal
from datetime import date, datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    """Get a database connection."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url)
    return psycopg2.connect(
        dbname="clarity_football",
        user="joao",
        host="localhost",
        port="5432"
    )


@contextmanager
def db_cursor() -> Generator[RealDictCursor, None, None]:
    """Context manager for database operations."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    """Convert database row to clean dict (handle Decimal, date, etc)."""
    result = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            result[key] = float(value)
        elif isinstance(value, (date, datetime)):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


# ============================================================================
# Team name/ID resolution
# ============================================================================

# Common team aliases (nicknames, abbreviations)
TEAM_ALIASES = {
    # Manchester United
    "man united": "Manchester United",
    "man utd": "Manchester United",
    "united": "Manchester United",
    "mufc": "Manchester United",
    "red devils": "Manchester United",
    # Manchester City
    "man city": "Manchester City",
    "city": "Manchester City",
    "mcfc": "Manchester City",
    # Liverpool
    "liverpool": "Liverpool",
    "pool": "Liverpool",
    "lfc": "Liverpool",
    "reds": "Liverpool",
    # Arsenal
    "arsenal": "Arsenal",
    "gunners": "Arsenal",
    "afc": "Arsenal",
    # Chelsea
    "chelsea": "Chelsea",
    "blues": "Chelsea",
    "cfc": "Chelsea",
    # Tottenham
    "spurs": "Tottenham Hotspur",
    "tottenham": "Tottenham Hotspur",
    "thfc": "Tottenham Hotspur",
    # Others
    "wolves": "Wolverhampton Wanderers",
    "wolverhampton": "Wolverhampton Wanderers",
    "brighton": "Brighton & Hove Albion",
    "west ham": "West Ham United",
    "hammers": "West Ham United",
    "newcastle": "Newcastle United",
    "magpies": "Newcastle United",
    "toon": "Newcastle United",
    "villa": "Aston Villa",
    "everton": "Everton",
    "toffees": "Everton",
    "forest": "Nottingham Forest",
    "nottingham": "Nottingham Forest",
    "nffc": "Nottingham Forest",
    "bournemouth": "AFC Bournemouth",
    "cherries": "AFC Bournemouth",
    "brentford": "Brentford",
    "bees": "Brentford",
    "fulham": "Fulham",
    "palace": "Crystal Palace",
    "cpfc": "Crystal Palace",
    "eagles": "Crystal Palace",
    "leeds": "Leeds United",
    "burnley": "Burnley",
    "clarets": "Burnley",
    "leicester": "Leicester City",
    "foxes": "Leicester City",
    "southampton": "Southampton",
    "saints": "Southampton",
    "ipswich": "Ipswich Town",
}

# Cache for team lookups
_team_cache: Dict[str, int] = {}
_team_name_cache: Dict[int, str] = {}


def resolve_team(team: str | int) -> int:
    """Resolve team name or ID to team_id.
    
    Supports:
    - Team ID (int)
    - Exact team name
    - Common aliases (Spurs, Wolves, Gunners, etc.)
    - Partial name match
    """
    if isinstance(team, int):
        return team
    
    team_lower = team.lower().strip()
    
    # Check cache first
    if team_lower in _team_cache:
        return _team_cache[team_lower]
    
    # Check aliases
    canonical_name = TEAM_ALIASES.get(team_lower)
    if canonical_name:
        team_lower = canonical_name.lower()
    
    with db_cursor() as cur:
        # Try exact match first
        cur.execute(
            "SELECT team_id, team_name FROM teams WHERE LOWER(team_name) = %s",
            (team_lower,)
        )
        row = cur.fetchone()
        if row:
            _team_cache[team_lower] = row["team_id"]
            _team_name_cache[row["team_id"]] = row["team_name"]
            return row["team_id"]
        
        # Try partial match
        cur.execute(
            "SELECT team_id, team_name FROM teams WHERE LOWER(team_name) LIKE %s",
            (f"%{team_lower}%",)
        )
        row = cur.fetchone()
        if row:
            _team_cache[team_lower] = row["team_id"]
            _team_name_cache[row["team_id"]] = row["team_name"]
            return row["team_id"]
    
    raise ValueError(f"Team not found: {team}")


def get_team_name(team_id: int) -> str:
    """Get team name from ID."""
    if team_id in _team_name_cache:
        return _team_name_cache[team_id]
    
    with db_cursor() as cur:
        cur.execute("SELECT team_name FROM teams WHERE team_id = %s", (team_id,))
        row = cur.fetchone()
        if row:
            _team_name_cache[team_id] = row["team_name"]
            return row["team_name"]
    
    return f"Unknown ({team_id})"


def get_current_round() -> int:
    """Get the latest round number in the database."""
    with db_cursor() as cur:
        cur.execute("SELECT MAX(round_number) as max_round FROM team_states")
        row = cur.fetchone()
        return row["max_round"] if row else 1


# ============================================================================
# Response formatting
# ============================================================================

@dataclass
class ToolResponse:
    """Standard response from an agent tool."""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "summary": self.summary,
            "error": self.error,
        }


def format_form_string(form: str) -> str:
    """Format form string with visual indicators."""
    if not form:
        return "No recent matches"
    
    result = []
    for char in form:
        if char == "W":
            result.append("✅")
        elif char == "D":
            result.append("🟡")
        elif char == "L":
            result.append("❌")
        else:
            result.append(char)
    return " ".join(result)


def format_trend(trend: str) -> str:
    """Format trend with arrow."""
    trend_map = {
        "improving": "📈 Improving",
        "stable": "➡️ Stable", 
        "declining": "📉 Declining",
    }
    return trend_map.get(trend, trend or "Unknown")


def describe_position(position: int, played: int) -> str:
    """Describe table position in context."""
    if position <= 4:
        return f"#{position} - Champions League zone"
    elif position <= 6:
        return f"#{position} - Europa League zone"
    elif position <= 7:
        return f"#{position} - Conference League zone"
    elif position >= 18:
        return f"#{position} - Relegation zone ⚠️"
    elif position >= 15:
        return f"#{position} - Relegation battle"
    else:
        return f"#{position} - Mid-table"


# ============================================================================
# Manager-aware utilities
# ============================================================================

def get_current_manager_info(team_id: int) -> Optional[Dict[str, Any]]:
    """Get current manager's info including when they started."""
    with db_cursor() as cur:
        cur.execute("""
            SELECT manager_name, first_match_round, last_match_round, 
                   matches, wins, draws, losses
            FROM manager_history 
            WHERE team_id = %s AND is_current = true
            LIMIT 1
        """, (team_id,))
        row = cur.fetchone()
        if row:
            return row_to_dict(row)
    return None


def get_formation_under_current_manager(team_id: int, round_number: int) -> Optional[str]:
    """
    Get the primary formation used under the current manager.
    
    Returns the most common formation since the current manager took charge,
    or the last 5 games if manager started recently.
    """
    with db_cursor() as cur:
        # Get when current manager started
        cur.execute("""
            SELECT first_match_round 
            FROM manager_history 
            WHERE team_id = %s AND is_current = true
            LIMIT 1
        """, (team_id,))
        row = cur.fetchone()
        
        if row:
            manager_start_round = row["first_match_round"]
        else:
            # No manager info, use last 5 rounds
            manager_start_round = max(1, round_number - 4)
        
        # Get formations since manager started (up to current round)
        cur.execute("""
            SELECT 
                CASE WHEN home_team_id = %s THEN formation_home ELSE formation_away END as formation
            FROM fotmob_matches
            WHERE (home_team_id = %s OR away_team_id = %s)
              AND round_number >= %s
              AND round_number <= %s
              AND status = 'finished'
            ORDER BY round_number DESC
        """, (team_id, team_id, team_id, manager_start_round, round_number))
        
        formations = [r["formation"] for r in cur.fetchall() if r["formation"]]
        
        if not formations:
            return None
        
        # Return most common formation under this manager
        from collections import Counter
        formation_counts = Counter(formations)
        return formation_counts.most_common(1)[0][0]
