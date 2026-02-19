"""
Fixture loading for backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.database.config import get_connection


@dataclass
class Fixture:
    """A match to analyze."""
    fixture_id: str
    home_team: str
    away_team: str
    home_team_id: int
    away_team_id: int
    match_date: date
    round_number: int
    
    # Result (if match is completed)
    home_score: Optional[int] = None
    away_score: Optional[int] = None


def get_round_fixtures(round_number: int, league_id: int = 47) -> List[Fixture]:
    """
    Get all fixtures for a specific round.
    
    Args:
        round_number: Premier League round number
        league_id: League ID (47 = Premier League)
    
    Returns:
        List of Fixture objects
    """
    conn = get_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor()
        
        # Get fixtures from fotmob_matches
        cur.execute("""
            SELECT 
                m.fotmob_match_id,
                m.home_team_id,
                m.away_team_id,
                m.match_date,
                m.round_number,
                m.home_score,
                m.away_score,
                m.home_team_name,
                m.away_team_name
            FROM fotmob_matches m
            WHERE m.round_number = %s
            AND m.league_id = %s
            ORDER BY m.match_date, m.fotmob_match_id
        """, (round_number, league_id))
        
        rows = cur.fetchall()
        
        fixtures = []
        for row in rows:
            fixture = Fixture(
                fixture_id=str(row[0]),
                home_team=row[7] or f"Team_{row[1]}",
                away_team=row[8] or f"Team_{row[2]}",
                home_team_id=row[1],
                away_team_id=row[2],
                match_date=row[3],
                round_number=row[4],
                home_score=row[5],
                away_score=row[6],
            )
            fixtures.append(fixture)
        
        return fixtures
        
    finally:
        conn.close()


def get_fixtures_range(start_round: int, end_round: int, league_id: int = 47) -> List[Fixture]:
    """Get fixtures for a range of rounds."""
    fixtures = []
    for r in range(start_round, end_round + 1):
        fixtures.extend(get_round_fixtures(r, league_id))
    return fixtures


if __name__ == "__main__":
    # Test
    fixtures = get_round_fixtures(25)
    print(f"Round 25: {len(fixtures)} fixtures")
    for f in fixtures[:3]:
        print(f"  {f.home_team} vs {f.away_team} ({f.match_date})")
