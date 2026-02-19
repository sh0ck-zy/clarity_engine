"""
Reality fetching - get actual match results for comparison.
"""

from __future__ import annotations

from typing import Optional, Dict, Any
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.database.config import get_connection
from src.agents.base import MatchReality


def get_match_reality(fixture_id: str) -> Optional[MatchReality]:
    """
    Get the actual result and stats for a completed match.
    
    Args:
        fixture_id: Match ID from fotmob_matches
    
    Returns:
        MatchReality object or None if not found/not completed
    """
    conn = get_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                m.fotmob_match_id,
                m.home_team_id,
                m.away_team_id,
                m.home_score,
                m.away_score,
                m.stats,
                m.home_team_name,
                m.away_team_name
            FROM fotmob_matches m
            WHERE m.fotmob_match_id = %s
        """, (fixture_id,))
        
        row = cur.fetchone()
        
        if not row:
            return None
        
        home_score = row[3]
        away_score = row[4]
        
        # Match not played yet
        if home_score is None or away_score is None:
            return None
        
        # Determine result
        if home_score > away_score:
            result = "H"
        elif away_score > home_score:
            result = "A"
        else:
            result = "D"
        
        # Extract xG from stats JSON if available
        home_xg = None
        away_xg = None
        
        stats = row[5]
        if stats:
            if isinstance(stats, str):
                stats = json.loads(stats)
            
            # Try to find xG in stats
            if isinstance(stats, dict):
                home_xg = stats.get("home_xg") or stats.get("xg", {}).get("home")
                away_xg = stats.get("away_xg") or stats.get("xg", {}).get("away")
        
        return MatchReality(
            fixture_id=str(row[0]),
            home_team=row[6] or f"Team_{row[1]}",
            away_team=row[7] or f"Team_{row[2]}",
            home_score=home_score,
            away_score=away_score,
            result=result,
            home_xg=home_xg,
            away_xg=away_xg,
            summary=f"{row[6]} {home_score}-{away_score} {row[7]}",
        )
        
    finally:
        conn.close()


def get_round_realities(round_number: int, league_id: int = 47) -> Dict[str, MatchReality]:
    """
    Get all match results for a round.
    
    Returns:
        Dict mapping fixture_id to MatchReality
    """
    conn = get_connection()
    if not conn:
        return {}
    
    try:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                m.fotmob_match_id,
                m.home_team_id,
                m.away_team_id,
                m.home_score,
                m.away_score,
                m.stats,
                m.home_team_name,
                m.away_team_name
            FROM fotmob_matches m
            WHERE m.round_number = %s
            AND m.league_id = %s
            AND m.home_score IS NOT NULL
        """, (round_number, league_id))
        
        rows = cur.fetchall()
        
        realities = {}
        for row in rows:
            home_score = row[3]
            away_score = row[4]
            
            if home_score > away_score:
                result = "H"
            elif away_score > home_score:
                result = "A"
            else:
                result = "D"
            
            # Extract xG
            home_xg = None
            away_xg = None
            stats = row[5]
            if stats:
                if isinstance(stats, str):
                    stats = json.loads(stats)
                if isinstance(stats, dict):
                    home_xg = stats.get("home_xg")
                    away_xg = stats.get("away_xg")
            
            reality = MatchReality(
                fixture_id=str(row[0]),
                home_team=row[6] or f"Team_{row[1]}",
                away_team=row[7] or f"Team_{row[2]}",
                home_score=home_score,
                away_score=away_score,
                result=result,
                home_xg=home_xg,
                away_xg=away_xg,
                summary=f"{row[6]} {home_score}-{away_score} {row[7]}",
            )
            realities[str(row[0])] = reality
        
        return realities
        
    finally:
        conn.close()


if __name__ == "__main__":
    # Test
    realities = get_round_realities(25)
    print(f"Round 25: {len(realities)} completed matches")
    for fid, r in list(realities.items())[:3]:
        print(f"  {r.summary} (xG: {r.home_xg}-{r.away_xg})")
