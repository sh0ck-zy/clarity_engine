"""
Matchup Tools - Functions for comparing teams and analyzing matchups.
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
class H2HMatch:
    """A single head-to-head match."""
    date: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    venue: str


@dataclass
class H2HRecord:
    """Head-to-head record between two teams."""
    team1: str
    team2: str
    total_matches: int
    team1_wins: int
    team2_wins: int
    draws: int
    team1_goals: int
    team2_goals: int
    recent_matches: List[H2HMatch]
    pattern: str               # "team1_dominant", "team2_dominant", "balanced"


@dataclass
class MatchupAnalysis:
    """Tactical analysis of a matchup."""
    home_team: str
    away_team: str
    
    # Position comparison
    home_position: int
    away_position: int
    position_diff: int
    
    # Form comparison
    home_form: str
    away_form: str
    home_form_points: int
    away_form_points: int
    form_advantage: str        # "home", "away", "neutral"
    
    # xG comparison
    home_xg_per_game: float
    away_xg_per_game: float
    home_xga_per_game: float
    away_xga_per_game: float
    xg_advantage: str          # "home", "away", "neutral"
    
    # Style matchup
    home_style: str
    away_style: str
    style_clash: str           # Description of how styles interact
    
    # Key insight
    headline: str


# ============================================================
# Database Connection
# ============================================================

def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


# ============================================================
# Tool Implementations
# ============================================================

def get_h2h(team1_name: str, team2_name: str, n_matches: int = 5) -> Optional[H2HRecord]:
    """
    Get head-to-head record between two teams.
    
    Args:
        team1_name: First team name
        team2_name: Second team name
        n_matches: Number of recent matches to include
    
    Returns:
        H2HRecord with historical data
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Resolve team names
        cur.execute("""
            SELECT team_id, team_name FROM teams 
            WHERE LOWER(team_name) LIKE LOWER(%s)
            LIMIT 1
        """, (f"%{team1_name}%",))
        row1 = cur.fetchone()
        
        cur.execute("""
            SELECT team_id, team_name FROM teams 
            WHERE LOWER(team_name) LIKE LOWER(%s)
            LIMIT 1
        """, (f"%{team2_name}%",))
        row2 = cur.fetchone()
        
        if not row1 or not row2:
            return None
        
        team1_id, team1_canonical = row1
        team2_id, team2_canonical = row2
        
        # Get H2H matches
        cur.execute("""
            SELECT 
                match_date, home_team_name, away_team_name,
                home_score, away_score, venue,
                home_team_id, away_team_id
            FROM fotmob_matches
            WHERE (
                (home_team_id = %s AND away_team_id = %s) OR
                (home_team_id = %s AND away_team_id = %s)
            )
            AND status = 'finished'
            ORDER BY match_date DESC
            LIMIT %s
        """, (team1_id, team2_id, team2_id, team1_id, n_matches))
        
        matches = cur.fetchall()
        
        if not matches:
            return H2HRecord(
                team1=team1_canonical,
                team2=team2_canonical,
                total_matches=0,
                team1_wins=0,
                team2_wins=0,
                draws=0,
                team1_goals=0,
                team2_goals=0,
                recent_matches=[],
                pattern="no_history",
            )
        
        # Calculate stats
        team1_wins = 0
        team2_wins = 0
        draws = 0
        team1_goals = 0
        team2_goals = 0
        recent_matches = []
        
        for m in matches:
            date, home_name, away_name, home_score, away_score, venue, home_id, away_id = m
            
            recent_matches.append(H2HMatch(
                date=str(date),
                home_team=home_name,
                away_team=away_name,
                home_score=home_score or 0,
                away_score=away_score or 0,
                venue=venue or "",
            ))
            
            # Determine winner relative to team1
            if home_id == team1_id:
                team1_goals += home_score or 0
                team2_goals += away_score or 0
                if (home_score or 0) > (away_score or 0):
                    team1_wins += 1
                elif (home_score or 0) < (away_score or 0):
                    team2_wins += 1
                else:
                    draws += 1
            else:
                team1_goals += away_score or 0
                team2_goals += home_score or 0
                if (away_score or 0) > (home_score or 0):
                    team1_wins += 1
                elif (away_score or 0) < (home_score or 0):
                    team2_wins += 1
                else:
                    draws += 1
        
        # Determine pattern
        if team1_wins > team2_wins + 1:
            pattern = "team1_dominant"
        elif team2_wins > team1_wins + 1:
            pattern = "team2_dominant"
        else:
            pattern = "balanced"
        
        return H2HRecord(
            team1=team1_canonical,
            team2=team2_canonical,
            total_matches=len(matches),
            team1_wins=team1_wins,
            team2_wins=team2_wins,
            draws=draws,
            team1_goals=team1_goals,
            team2_goals=team2_goals,
            recent_matches=recent_matches,
            pattern=pattern,
        )
    finally:
        cur.close()
        conn.close()


def get_matchup_analysis(home_team: str, away_team: str, round_number: int = None) -> Optional[MatchupAnalysis]:
    """
    Get tactical analysis of a matchup.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        round_number: Round for state comparison (default: latest)
    
    Returns:
        MatchupAnalysis with comparison data
    """
    # Import here to avoid circular imports
    from .team_tools import get_team_state, get_team_profile
    
    home_state = get_team_state(home_team, round_number)
    away_state = get_team_state(away_team, round_number)
    
    if not home_state or not away_state:
        return None
    
    home_profile = get_team_profile(home_team)
    away_profile = get_team_profile(away_team)
    
    # Calculate advantages
    position_diff = away_state.position - home_state.position
    
    # Form advantage
    if home_state.form_points >= away_state.form_points + 3:
        form_advantage = "home"
    elif away_state.form_points >= home_state.form_points + 3:
        form_advantage = "away"
    else:
        form_advantage = "neutral"
    
    # xG advantage
    home_xg_diff = home_state.xg_per_game - home_state.xg_against_per_game
    away_xg_diff = away_state.xg_per_game - away_state.xg_against_per_game
    
    if home_xg_diff >= away_xg_diff + 0.3:
        xg_advantage = "home"
    elif away_xg_diff >= home_xg_diff + 0.3:
        xg_advantage = "away"
    else:
        xg_advantage = "neutral"
    
    # Style clash analysis
    home_style = home_profile.style if home_profile else "unknown"
    away_style = away_profile.style if away_profile else "unknown"
    
    if home_style == "possession" and away_style == "counter":
        style_clash = "Classic matchup: possession vs counter-attack. Away team will look to exploit spaces."
    elif home_style == "counter" and away_style == "possession":
        style_clash = "Away team will dominate the ball. Home team dangerous on transitions."
    elif home_style == away_style:
        style_clash = f"Similar styles ({home_style}). Quality and form likely to decide."
    else:
        style_clash = f"Contrasting approaches: {home_style} vs {away_style}."
    
    # Generate headline
    if position_diff > 10:
        headline = f"David vs Goliath: {home_state.team_name} ({home_state.position}th) host high-flying {away_state.team_name} ({away_state.position}th)"
    elif position_diff < -10:
        headline = f"Mismatch on paper: {home_state.team_name} ({home_state.position}th) should handle {away_state.team_name} ({away_state.position}th)"
    elif abs(position_diff) <= 3:
        headline = f"Close contest: {home_state.team_name} and {away_state.team_name} separated by {abs(position_diff)} places"
    else:
        headline = f"{home_state.team_name} ({home_state.position}th) vs {away_state.team_name} ({away_state.position}th)"
    
    return MatchupAnalysis(
        home_team=home_state.team_name,
        away_team=away_state.team_name,
        home_position=home_state.position,
        away_position=away_state.position,
        position_diff=position_diff,
        home_form=home_state.form_string,
        away_form=away_state.form_string,
        home_form_points=home_state.form_points,
        away_form_points=away_state.form_points,
        form_advantage=form_advantage,
        home_xg_per_game=home_state.xg_per_game,
        away_xg_per_game=away_state.xg_per_game,
        home_xga_per_game=home_state.xg_against_per_game,
        away_xga_per_game=away_state.xg_against_per_game,
        xg_advantage=xg_advantage,
        home_style=home_style,
        away_style=away_style,
        style_clash=style_clash,
        headline=headline,
    )


# ============================================================
# Testing
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Matchup Tools")
    print("=" * 60)
    
    # Test get_h2h
    print("\n1. get_h2h('Liverpool', 'Arsenal')")
    h2h = get_h2h("Liverpool", "Arsenal")
    if h2h:
        print(f"   {h2h.team1} vs {h2h.team2}: {h2h.total_matches} matches")
        print(f"   {h2h.team1}: {h2h.team1_wins}W, {h2h.team2}: {h2h.team2_wins}W, Draws: {h2h.draws}")
        print(f"   Pattern: {h2h.pattern}")
        if h2h.recent_matches:
            print(f"   Last match: {h2h.recent_matches[0].home_team} {h2h.recent_matches[0].home_score}-{h2h.recent_matches[0].away_score} {h2h.recent_matches[0].away_team}")
    
    # Test get_matchup_analysis
    print("\n2. get_matchup_analysis('Arsenal', 'Liverpool')")
    analysis = get_matchup_analysis("Arsenal", "Liverpool")
    if analysis:
        print(f"   {analysis.headline}")
        print(f"   Form: {analysis.home_form} vs {analysis.away_form} → {analysis.form_advantage}")
        print(f"   xG/game: {analysis.home_xg_per_game:.2f} vs {analysis.away_xg_per_game:.2f}")
        print(f"   Style: {analysis.style_clash}")
    
    print("\n" + "=" * 60)
    print("✅ All tests complete")
