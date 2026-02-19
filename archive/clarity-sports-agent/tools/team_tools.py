"""
Team Tools - Functions for querying team state and context.
"""

from dataclasses import dataclass
from typing import Optional, List
from decimal import Decimal

import psycopg2
from pathlib import Path

# Add parent directory to path for imports
import sys
AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

from config import DB_CONFIG


# ============================================================
# Response Models
# ============================================================

@dataclass
class TeamState:
    """Complete team state at a specific round (8 KG layers)."""
    team_id: int
    team_name: str
    round_number: int
    
    # Position Layer
    position: int
    points: int
    played: int
    wins: int
    draws: int
    losses: int
    goal_difference: int
    
    # Form Layer
    form_string: str           # "WWDLW"
    form_points: int           # out of 15
    goals_scored_last5: int
    goals_conceded_last5: int
    clean_sheets_last5: int
    
    # xG Layer
    xg_for_last5: float
    xg_against_last5: float
    xg_diff_last5: float
    
    # Style Layer
    avg_possession: float
    primary_formation: str
    
    # Attack Layer
    shots_per_game: float
    xg_per_game: float
    
    # Defense Layer
    xg_against_per_game: float
    
    # Momentum Layer
    form_trend: str            # "improving", "stable", "declining"
    
    # Home/Away Split
    home_points: int
    away_points: int


@dataclass
class TeamForm:
    """Focused view on team form."""
    team_name: str
    form_string: str
    form_points: int
    xg_for_last5: float
    xg_against_last5: float
    xg_diff: float
    goals_scored: int
    goals_conceded: int
    clean_sheets: int
    trend: str


@dataclass
class TeamProfile:
    """Tactical profile of a team."""
    team_name: str
    primary_formation: str
    avg_possession: float
    style: str                 # "possession", "counter", "direct", "balanced"
    shots_per_game: float
    xg_per_game: float
    xg_against_per_game: float
    strength: str              # "attack", "defense", "balanced"


@dataclass
class PsychologicalState:
    """Psychological/narrative state of a team."""
    team_name: str
    state: str                 # "desperate", "comfortable", "rising", "crisis", "neutral"
    confidence: str            # "high", "medium", "low"
    pressure_type: Optional[str]  # "relegation", "title", "top4", "europe", None
    narrative: str             # Short description of current situation
    factors: List[str]         # What's driving this state


@dataclass  
class LastMatchSummary:
    """Summary of a team's last match."""
    team_name: str
    opponent: str
    result: str                # "W", "D", "L"
    score: str                 # "2-1"
    was_home: bool
    xg_for: float
    xg_against: float
    key_events: List[str]


# ============================================================
# Database Connection
# ============================================================

def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


# ============================================================
# Tool Implementations
# ============================================================

def get_team_state(team_name: str, round_number: int = None) -> Optional[TeamState]:
    """
    Get complete team state at a specific round.
    
    Args:
        team_name: Team name (fuzzy matched)
        round_number: Round to get state for (default: latest)
    
    Returns:
        TeamState with all 8 KG layers
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Resolve team name to ID
        cur.execute("""
            SELECT team_id, team_name FROM teams 
            WHERE LOWER(team_name) LIKE LOWER(%s)
            LIMIT 1
        """, (f"%{team_name}%",))
        
        row = cur.fetchone()
        if not row:
            return None
        
        team_id, canonical_name = row
        
        # Get state for round (or latest)
        if round_number:
            cur.execute("""
                SELECT * FROM team_states 
                WHERE team_id = %s AND round_number = %s
            """, (team_id, round_number))
        else:
            cur.execute("""
                SELECT * FROM team_states 
                WHERE team_id = %s 
                ORDER BY round_number DESC 
                LIMIT 1
            """, (team_id,))
        
        state_row = cur.fetchone()
        if not state_row:
            return None
        
        # Map to TeamState (column order from schema)
        return TeamState(
            team_id=team_id,
            team_name=canonical_name,
            round_number=state_row[2],   # round_number
            position=state_row[4] or 0,  # position
            points=state_row[5] or 0,    # points
            played=state_row[6] or 0,    # played
            wins=state_row[7] or 0,      # wins
            draws=state_row[8] or 0,     # draws
            losses=state_row[9] or 0,    # losses
            goal_difference=state_row[12] or 0,  # goal_difference
            form_string=state_row[13] or "",     # form_string
            form_points=state_row[14] or 0,      # form_points
            goals_scored_last5=state_row[15] or 0,    # goals_scored_last5
            goals_conceded_last5=state_row[16] or 0,  # goals_conceded_last5
            clean_sheets_last5=state_row[17] or 0,    # clean_sheets_last5
            xg_for_last5=float(state_row[18] or 0),   # xg_for_last5
            xg_against_last5=float(state_row[19] or 0),  # xg_against_last5
            xg_diff_last5=float(state_row[20] or 0),  # xg_diff_last5
            avg_possession=float(state_row[21] or 50),  # avg_possession
            primary_formation=state_row[22] or "",    # primary_formation
            shots_per_game=float(state_row[23] or 0), # shots_per_game
            xg_per_game=float(state_row[25] or 0),    # xg_per_game
            xg_against_per_game=float(state_row[27] or 0),  # xg_against_per_game
            form_trend=state_row[29] or "stable",     # form_trend
            home_points=state_row[36] or 0,           # home_points
            away_points=state_row[37] or 0,           # away_points
        )
    finally:
        cur.close()
        conn.close()


def get_team_form(team_name: str, n_games: int = 5) -> Optional[TeamForm]:
    """
    Get focused form summary for a team.
    
    Args:
        team_name: Team name
        n_games: Number of recent games to consider (default: 5)
    
    Returns:
        TeamForm with recent performance metrics
    """
    state = get_team_state(team_name)
    if not state:
        return None
    
    return TeamForm(
        team_name=state.team_name,
        form_string=state.form_string,
        form_points=state.form_points,
        xg_for_last5=state.xg_for_last5,
        xg_against_last5=state.xg_against_last5,
        xg_diff=state.xg_diff_last5,
        goals_scored=state.goals_scored_last5,
        goals_conceded=state.goals_conceded_last5,
        clean_sheets=state.clean_sheets_last5,
        trend=state.form_trend,
    )


def get_team_profile(team_name: str) -> Optional[TeamProfile]:
    """
    Get tactical profile of a team.
    
    Args:
        team_name: Team name
    
    Returns:
        TeamProfile with style and tactical info
    """
    state = get_team_state(team_name)
    if not state:
        return None
    
    # Determine style based on possession
    if state.avg_possession >= 55:
        style = "possession"
    elif state.avg_possession <= 45:
        style = "counter"
    else:
        style = "balanced"
    
    # Determine strength
    xg_diff = state.xg_per_game - state.xg_against_per_game
    if state.xg_per_game > 1.5 and xg_diff > 0.3:
        strength = "attack"
    elif state.xg_against_per_game < 1.0:
        strength = "defense"
    else:
        strength = "balanced"
    
    return TeamProfile(
        team_name=state.team_name,
        primary_formation=state.primary_formation,
        avg_possession=state.avg_possession,
        style=style,
        shots_per_game=state.shots_per_game,
        xg_per_game=state.xg_per_game,
        xg_against_per_game=state.xg_against_per_game,
        strength=strength,
    )


def get_psychological_state(team_name: str) -> Optional[PsychologicalState]:
    """
    Determine psychological/narrative state of a team.
    
    Uses position, form, and context to determine if team is:
    - desperate: relegation battle, losing streak
    - crisis: big club underperforming badly
    - rising: improving form, climbing table
    - comfortable: secure position, good form
    - neutral: mid-table, mixed form
    
    Args:
        team_name: Team name
    
    Returns:
        PsychologicalState with narrative context
    """
    state = get_team_state(team_name)
    if not state:
        return None
    
    factors = []
    
    # Determine pressure type based on position
    pressure_type = None
    if state.position >= 18:
        pressure_type = "relegation"
        factors.append(f"In relegation zone (position {state.position})")
    elif state.position <= 4:
        pressure_type = "top4"
        factors.append(f"Fighting for top 4 (position {state.position})")
    elif state.position == 1:
        pressure_type = "title"
        factors.append("Title race")
    
    # Analyze form
    recent_wins = state.form_string.count('W')
    recent_losses = state.form_string.count('L')
    
    if recent_losses >= 4:
        factors.append(f"Losing streak ({recent_losses} losses in last 5)")
    elif recent_wins >= 4:
        factors.append(f"Winning streak ({recent_wins} wins in last 5)")
    
    # xG analysis
    if state.xg_diff_last5 < -3:
        factors.append(f"Being outplayed (xG diff: {state.xg_diff_last5:.1f})")
    elif state.xg_diff_last5 > 3:
        factors.append(f"Dominant performances (xG diff: +{state.xg_diff_last5:.1f})")
    
    # Determine overall state
    if state.position >= 18 and recent_losses >= 3:
        psychological_state = "desperate"
        confidence = "low"
        narrative = f"{state.team_name} are in serious trouble. In the relegation zone with poor form."
    elif state.position >= 18:
        psychological_state = "desperate"
        confidence = "low"
        narrative = f"{state.team_name} are fighting for survival in the relegation zone."
    elif state.form_trend == "declining" and recent_losses >= 3:
        psychological_state = "crisis"
        confidence = "low"
        narrative = f"{state.team_name} are in crisis mode with a terrible run of form."
    elif state.form_trend == "improving" and recent_wins >= 3:
        psychological_state = "rising"
        confidence = "high"
        narrative = f"{state.team_name} are on the rise with momentum building."
    elif state.position <= 6 and state.form_points >= 10:
        psychological_state = "comfortable"
        confidence = "high"
        narrative = f"{state.team_name} are in a strong position with consistent performances."
    else:
        psychological_state = "neutral"
        confidence = "medium"
        narrative = f"{state.team_name} are in a stable position with mixed recent form."
    
    return PsychologicalState(
        team_name=state.team_name,
        state=psychological_state,
        confidence=confidence,
        pressure_type=pressure_type,
        narrative=narrative,
        factors=factors,
    )


def get_last_match_summary(team_name: str) -> Optional[LastMatchSummary]:
    """
    Get summary of a team's last match.
    
    Args:
        team_name: Team name
    
    Returns:
        LastMatchSummary with result and key info
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Find team
        cur.execute("""
            SELECT team_id, team_name FROM teams 
            WHERE LOWER(team_name) LIKE LOWER(%s)
            LIMIT 1
        """, (f"%{team_name}%",))
        
        row = cur.fetchone()
        if not row:
            return None
        
        team_id, canonical_name = row
        
        # Get last match
        cur.execute("""
            SELECT 
                fotmob_match_id,
                home_team_id, home_team_name, away_team_id, away_team_name,
                home_score, away_score,
                stats
            FROM fotmob_matches
            WHERE (home_team_id = %s OR away_team_id = %s)
            AND status = 'finished'
            ORDER BY match_date DESC
            LIMIT 1
        """, (team_id, team_id))
        
        match_row = cur.fetchone()
        if not match_row:
            return None
        
        (match_id, home_id, home_name, away_id, away_name,
         home_score, away_score, stats) = match_row
        
        was_home = (home_id == team_id)
        
        if was_home:
            opponent = away_name
            goals_for = home_score
            goals_against = away_score
        else:
            opponent = home_name
            goals_for = away_score
            goals_against = home_score
        
        # Determine result
        if goals_for > goals_against:
            result = "W"
        elif goals_for < goals_against:
            result = "L"
        else:
            result = "D"
        
        score = f"{goals_for}-{goals_against}"
        
        # Extract xG from stats if available
        xg_for = 0.0
        xg_against = 0.0
        # (would need to parse stats JSON here)
        
        return LastMatchSummary(
            team_name=canonical_name,
            opponent=opponent,
            result=result,
            score=score,
            was_home=was_home,
            xg_for=xg_for,
            xg_against=xg_against,
            key_events=[],
        )
    finally:
        cur.close()
        conn.close()


# ============================================================
# Testing
# ============================================================

if __name__ == "__main__":
    # Test the tools
    print("=" * 60)
    print("Testing Team Tools")
    print("=" * 60)
    
    # Test get_team_state
    print("\n1. get_team_state('Liverpool')")
    state = get_team_state("Liverpool")
    if state:
        print(f"   Position: {state.position}")
        print(f"   Points: {state.points}")
        print(f"   Form: {state.form_string}")
        print(f"   xG last 5: {state.xg_for_last5:.1f} for / {state.xg_against_last5:.1f} against")
    
    # Test get_team_form
    print("\n2. get_team_form('Arsenal')")
    form = get_team_form("Arsenal")
    if form:
        print(f"   Form: {form.form_string} ({form.form_points}/15 pts)")
        print(f"   Trend: {form.trend}")
        print(f"   xG diff: {form.xg_diff:.1f}")
    
    # Test get_psychological_state
    print("\n3. get_psychological_state('Wolves')")
    psych = get_psychological_state("Wolves")
    if psych:
        print(f"   State: {psych.state}")
        print(f"   Confidence: {psych.confidence}")
        print(f"   Narrative: {psych.narrative}")
        print(f"   Factors: {psych.factors}")
    
    # Test get_last_match_summary
    print("\n4. get_last_match_summary('Chelsea')")
    last = get_last_match_summary("Chelsea")
    if last:
        print(f"   vs {last.opponent}: {last.result} ({last.score})")
        print(f"   Home: {last.was_home}")
    
    print("\n" + "=" * 60)
    print("✅ All tests complete")
