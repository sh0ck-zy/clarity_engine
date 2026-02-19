"""
Player Tools - Functions for querying player state and context.
"""

from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path

import psycopg2

import sys
AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

from config import DB_CONFIG


# ============================================================
# Response Models
# ============================================================

@dataclass
class PlayerState:
    """Complete player state at a specific round."""
    player_id: int
    player_name: str
    team_name: str
    round_number: int
    
    # Season totals
    appearances: int
    starts: int
    minutes: int
    goals: int
    assists: int
    xg_total: float
    xa_total: float
    
    # Form (last 5)
    goals_last5: int
    assists_last5: int
    xg_last5: float
    avg_rating_last5: Optional[float]
    
    # Per 90 stats
    goals_per_90: float
    assists_per_90: float
    xg_per_90: float
    
    # Season average
    avg_rating_season: Optional[float]


@dataclass
class KeyPlayer:
    """A key player for a team."""
    player_name: str
    position: str
    importance: str            # "critical", "important", "rotation"
    goals: int
    assists: int
    avg_rating: Optional[float]
    form_goals_last5: int
    form_assists_last5: int
    is_in_form: bool


@dataclass
class InjuryImpact:
    """Impact of injuries on a team."""
    team_name: str
    total_missing: int
    key_players_missing: int
    impact_level: str          # "severe", "moderate", "minimal"
    missing_players: List[str]
    narrative: str


# ============================================================
# Database Connection
# ============================================================

def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


# ============================================================
# Tool Implementations
# ============================================================

def get_player_state(player_name: str, round_number: int = None) -> Optional[PlayerState]:
    """
    Get player state at a specific round.
    
    Args:
        player_name: Player name (fuzzy matched)
        round_number: Round to get state for (default: latest)
    
    Returns:
        PlayerState with stats and form
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Build query
        if round_number:
            cur.execute("""
                SELECT 
                    ps.player_id, p.player_name, t.team_name,
                    ps.round_number, ps.appearances, ps.starts, ps.minutes,
                    ps.goals, ps.assists, ps.xg_total, ps.xa_total,
                    ps.goals_last5, ps.assists_last5, ps.xg_last5,
                    ps.avg_rating_last5, ps.goals_per_90, ps.assists_per_90,
                    ps.xg_per_90, ps.avg_rating_season
                FROM player_states ps
                JOIN players p ON ps.player_id = p.player_id
                JOIN teams t ON ps.team_id = t.team_id
                WHERE LOWER(p.player_name) LIKE LOWER(%s)
                AND ps.round_number = %s
                LIMIT 1
            """, (f"%{player_name}%", round_number))
        else:
            cur.execute("""
                SELECT 
                    ps.player_id, p.player_name, t.team_name,
                    ps.round_number, ps.appearances, ps.starts, ps.minutes,
                    ps.goals, ps.assists, ps.xg_total, ps.xa_total,
                    ps.goals_last5, ps.assists_last5, ps.xg_last5,
                    ps.avg_rating_last5, ps.goals_per_90, ps.assists_per_90,
                    ps.xg_per_90, ps.avg_rating_season
                FROM player_states ps
                JOIN players p ON ps.player_id = p.player_id
                JOIN teams t ON ps.team_id = t.team_id
                WHERE LOWER(p.player_name) LIKE LOWER(%s)
                ORDER BY ps.round_number DESC
                LIMIT 1
            """, (f"%{player_name}%",))
        
        row = cur.fetchone()
        if not row:
            return None
        
        return PlayerState(
            player_id=row[0],
            player_name=row[1],
            team_name=row[2],
            round_number=row[3],
            appearances=row[4] or 0,
            starts=row[5] or 0,
            minutes=row[6] or 0,
            goals=row[7] or 0,
            assists=row[8] or 0,
            xg_total=float(row[9] or 0),
            xa_total=float(row[10] or 0),
            goals_last5=row[11] or 0,
            assists_last5=row[12] or 0,
            xg_last5=float(row[13] or 0),
            avg_rating_last5=float(row[14]) if row[14] else None,
            goals_per_90=float(row[15] or 0),
            assists_per_90=float(row[16] or 0),
            xg_per_90=float(row[17] or 0),
            avg_rating_season=float(row[18]) if row[18] else None,
        )
    finally:
        cur.close()
        conn.close()


def get_key_players(team_name: str, round_number: int = None, limit: int = 5) -> List[KeyPlayer]:
    """
    Get key players for a team based on contributions and ratings.
    
    Args:
        team_name: Team name
        round_number: Round to get state for (default: latest)
        limit: Number of players to return
    
    Returns:
        List of KeyPlayer objects
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get team ID
        cur.execute("""
            SELECT team_id FROM teams 
            WHERE LOWER(team_name) LIKE LOWER(%s)
            LIMIT 1
        """, (f"%{team_name}%",))
        
        row = cur.fetchone()
        if not row:
            return []
        
        team_id = row[0]
        
        # Get top players by goal contributions
        if round_number:
            cur.execute("""
                SELECT 
                    p.player_name,
                    ps.goals, ps.assists,
                    ps.avg_rating_season,
                    ps.goals_last5, ps.assists_last5,
                    ps.minutes
                FROM player_states ps
                JOIN players p ON ps.player_id = p.player_id
                WHERE ps.team_id = %s AND ps.round_number = %s
                AND ps.minutes > 200
                ORDER BY (ps.goals + ps.assists) DESC, ps.avg_rating_season DESC NULLS LAST
                LIMIT %s
            """, (team_id, round_number, limit))
        else:
            cur.execute("""
                SELECT 
                    p.player_name,
                    ps.goals, ps.assists,
                    ps.avg_rating_season,
                    ps.goals_last5, ps.assists_last5,
                    ps.minutes
                FROM player_states ps
                JOIN players p ON ps.player_id = p.player_id
                WHERE ps.team_id = %s
                AND ps.round_number = (SELECT MAX(round_number) FROM player_states WHERE team_id = %s)
                AND ps.minutes > 200
                ORDER BY (ps.goals + ps.assists) DESC, ps.avg_rating_season DESC NULLS LAST
                LIMIT %s
            """, (team_id, team_id, limit))
        
        results = []
        for row in cur.fetchall():
            name, goals, assists, rating, g5, a5, minutes = row
            
            # Determine importance based on contributions
            contributions = (goals or 0) + (assists or 0)
            if contributions >= 10:
                importance = "critical"
            elif contributions >= 5:
                importance = "important"
            else:
                importance = "rotation"
            
            # Determine if in form
            is_in_form = (g5 or 0) + (a5 or 0) >= 2
            
            results.append(KeyPlayer(
                player_name=name,
                position="",  # Would need position data
                importance=importance,
                goals=goals or 0,
                assists=assists or 0,
                avg_rating=float(rating) if rating else None,
                form_goals_last5=g5 or 0,
                form_assists_last5=a5 or 0,
                is_in_form=is_in_form,
            ))
        
        return results
    finally:
        cur.close()
        conn.close()


def get_injuries_impact(team_name: str) -> Optional[InjuryImpact]:
    """
    Get impact of injuries on a team.
    
    Note: This is a placeholder - would need injury data integration.
    
    Args:
        team_name: Team name
    
    Returns:
        InjuryImpact with severity assessment
    """
    # TODO: Integrate with injury data source (API-Football or scraped)
    # For now, return a placeholder
    
    return InjuryImpact(
        team_name=team_name,
        total_missing=0,
        key_players_missing=0,
        impact_level="minimal",
        missing_players=[],
        narrative=f"Injury data not yet integrated for {team_name}.",
    )


# ============================================================
# Testing
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Player Tools")
    print("=" * 60)
    
    # Test get_player_state
    print("\n1. get_player_state('Salah')")
    state = get_player_state("Salah")
    if state:
        print(f"   {state.player_name} ({state.team_name})")
        print(f"   Goals: {state.goals}, Assists: {state.assists}")
        print(f"   xG: {state.xg_total:.1f}, Rating: {state.avg_rating_season}")
        print(f"   Last 5: {state.goals_last5}G, {state.assists_last5}A")
    
    # Test get_key_players
    print("\n2. get_key_players('Liverpool')")
    players = get_key_players("Liverpool")
    for p in players:
        form_str = "🔥" if p.is_in_form else ""
        print(f"   {p.player_name}: {p.goals}G {p.assists}A ({p.importance}) {form_str}")
    
    # Test get_key_players for another team
    print("\n3. get_key_players('Manchester City')")
    players = get_key_players("Manchester City")
    for p in players:
        form_str = "🔥" if p.is_in_form else ""
        print(f"   {p.player_name}: {p.goals}G {p.assists}A ({p.importance}) {form_str}")
    
    print("\n" + "=" * 60)
    print("✅ All tests complete")
