"""
Team Resolver - Resolve team names to canonical IDs.
"""

from dataclasses import dataclass
from typing import Optional, Dict
from pathlib import Path

import psycopg2

import sys
AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

from config import DB_CONFIG


@dataclass
class Team:
    """Canonical team information."""
    team_id: int
    name: str
    short_name: Optional[str] = None
    fotmob_id: Optional[int] = None


class TeamResolver:
    """
    Resolve any team name to canonical team information.
    
    Supports:
    - Exact matches
    - Fuzzy matching
    - Common aliases
    """
    
    # Common aliases
    ALIASES = {
        "man united": "Manchester United",
        "man utd": "Manchester United",
        "united": "Manchester United",
        "man city": "Manchester City",
        "city": "Manchester City",
        "liverpool": "Liverpool",
        "pool": "Liverpool",
        "arsenal": "Arsenal",
        "gunners": "Arsenal",
        "chelsea": "Chelsea",
        "blues": "Chelsea",
        "spurs": "Tottenham Hotspur",
        "tottenham": "Tottenham Hotspur",
        "wolves": "Wolverhampton Wanderers",
        "wolverhampton": "Wolverhampton Wanderers",
        "brighton": "Brighton & Hove Albion",
        "west ham": "West Ham United",
        "hammers": "West Ham United",
        "newcastle": "Newcastle United",
        "magpies": "Newcastle United",
        "villa": "Aston Villa",
        "everton": "Everton",
        "toffees": "Everton",
        "forest": "Nottingham Forest",
        "nottingham": "Nottingham Forest",
        "bournemouth": "AFC Bournemouth",
        "brentford": "Brentford",
        "bees": "Brentford",
        "fulham": "Fulham",
        "palace": "Crystal Palace",
        "leeds": "Leeds United",
        "burnley": "Burnley",
        "sunderland": "Sunderland",
    }
    
    def __init__(self):
        self._cache: Dict[str, Team] = {}
    
    def resolve(self, name: str) -> Optional[Team]:
        """
        Resolve a team name to canonical team information.
        
        Args:
            name: Team name (can be alias, partial, or canonical)
        
        Returns:
            Team object with canonical info, or None if not found
        """
        # Check cache first
        cache_key = name.lower().strip()
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Check aliases
        canonical_name = self.ALIASES.get(cache_key)
        if canonical_name:
            name = canonical_name
        
        # Query database
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        try:
            # Try exact match first
            cur.execute("""
                SELECT team_id, team_name, short_name
                FROM teams
                WHERE LOWER(team_name) = LOWER(%s)
                LIMIT 1
            """, (name,))
            
            row = cur.fetchone()
            
            # Try fuzzy match if exact fails
            if not row:
                cur.execute("""
                    SELECT team_id, team_name, short_name
                    FROM teams
                    WHERE LOWER(team_name) LIKE LOWER(%s)
                    LIMIT 1
                """, (f"%{name}%",))
                row = cur.fetchone()
            
            if not row:
                return None
            
            team = Team(
                team_id=row[0],
                name=row[1],
                short_name=row[2],
                fotmob_id=row[0],  # In our schema, team_id is fotmob_id
            )
            
            # Cache the result
            self._cache[cache_key] = team
            
            return team
            
        finally:
            cur.close()
            conn.close()


# Global resolver instance
_resolver = TeamResolver()


def resolve_team(name: str) -> Optional[Team]:
    """Convenience function to resolve a team name."""
    return _resolver.resolve(name)


# ============================================================
# Testing
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Team Resolver")
    print("=" * 60)
    
    resolver = TeamResolver()
    
    test_names = [
        "Liverpool",
        "liverpool",
        "Man United",
        "Wolves",
        "Spurs",
        "Brighton",
        "Arsenal",
        "NonExistentTeam",
    ]
    
    for name in test_names:
        team = resolver.resolve(name)
        if team:
            print(f"   '{name}' → {team.name} (ID: {team.team_id})")
        else:
            print(f"   '{name}' → Not found")
    
    print("\n" + "=" * 60)
