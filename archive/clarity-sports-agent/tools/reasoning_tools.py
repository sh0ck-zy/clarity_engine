"""
Reasoning Tools - Helper functions for agent reasoning.
"""

from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

import sys
AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))


# ============================================================
# Response Models
# ============================================================

@dataclass
class GameScenario:
    """A scenario in the game state tree."""
    trigger: str               # "home_scores_first", "0-0_at_halftime", etc.
    probability: str           # "likely", "possible", "unlikely"
    description: str
    likely_outcome: str
    home_reaction: str
    away_reaction: str


@dataclass
class GameStateTree:
    """Game state tree with branching scenarios."""
    home_team: str
    away_team: str
    
    # Key scenarios
    home_scores_first: GameScenario
    away_scores_first: GameScenario
    goalless_at_60: GameScenario
    
    # Most likely path
    most_likely_path: str
    most_likely_scoreline: str
    
    # Key insight
    narrative: str


# ============================================================
# Tool Implementations
# ============================================================

def build_game_state_tree(
    home_team: str,
    away_team: str,
    home_psychological_state: str = "neutral",
    away_psychological_state: str = "neutral",
    home_form: str = "",
    away_form: str = "",
) -> GameStateTree:
    """
    Build a game state tree with branching scenarios.
    
    This helps the agent think through how the game might unfold
    based on different triggering events.
    
    Args:
        home_team: Home team name
        away_team: Away team name
        home_psychological_state: "desperate", "comfortable", "rising", etc.
        away_psychological_state: Same as above
        home_form: Form string like "WWDLW"
        away_form: Form string
    
    Returns:
        GameStateTree with scenarios
    """
    # Analyze form
    home_recent_wins = home_form.count('W') if home_form else 0
    away_recent_wins = away_form.count('W') if away_form else 0
    home_recent_losses = home_form.count('L') if home_form else 0
    away_recent_losses = away_form.count('L') if away_form else 0
    
    # Build scenarios based on psychological states and form
    
    # Scenario 1: Home scores first
    if home_psychological_state == "desperate":
        home_scores_first_outcome = "Crowd lifts them. They push for a second."
        home_scores_first_away_reaction = f"{away_team} may struggle to respond against energized home side."
    elif away_psychological_state == "comfortable":
        home_scores_first_outcome = f"{home_team} will try to protect the lead."
        home_scores_first_away_reaction = f"{away_team} have the quality to respond but might accept the loss."
    else:
        home_scores_first_outcome = "Game opens up."
        home_scores_first_away_reaction = f"{away_team} will need to push forward, creating spaces."
    
    home_scores_first = GameScenario(
        trigger="home_scores_first",
        probability="likely" if home_recent_wins >= 2 else "possible",
        description=f"{home_team} take an early lead",
        likely_outcome=home_scores_first_outcome,
        home_reaction="Push for second while momentum is with them",
        away_reaction=home_scores_first_away_reaction,
    )
    
    # Scenario 2: Away scores first
    if home_psychological_state == "desperate":
        away_scores_first_outcome = f"Nerves set in. {home_team} may panic."
        away_scores_first_home_reaction = "Crowd turns anxious. Desperation kicks in."
    elif home_psychological_state in ["comfortable", "rising"]:
        away_scores_first_outcome = f"{home_team} have the quality to respond."
        away_scores_first_home_reaction = "Will push for equalizer with purpose."
    else:
        away_scores_first_outcome = "Depends on timing. Early goal = time to respond."
        away_scores_first_home_reaction = "Need to show character."
    
    away_scores_first = GameScenario(
        trigger="away_scores_first",
        probability="possible",
        description=f"{away_team} score against the run of play",
        likely_outcome=away_scores_first_outcome,
        home_reaction=away_scores_first_home_reaction,
        away_reaction="Sit back and hit on counter",
    )
    
    # Scenario 3: 0-0 at 60 minutes
    if home_psychological_state == "desperate":
        goalless_outcome = f"Crowd gets nervous. Pressure mounts on {home_team}."
        goalless_home_reaction = "Throw caution to wind. Leave spaces."
    elif away_psychological_state == "comfortable":
        goalless_outcome = f"{away_team} might be happy with a point."
        goalless_home_reaction = f"{home_team} must take initiative."
    else:
        goalless_outcome = "Next goal wins mentality kicks in."
        goalless_home_reaction = "Both teams will take more risks."
    
    goalless_at_60 = GameScenario(
        trigger="0-0_at_60",
        probability="possible",
        description="Goalless approaching final third",
        likely_outcome=goalless_outcome,
        home_reaction=goalless_home_reaction,
        away_reaction="Look for openings as home team pushes",
    )
    
    # Determine most likely path
    if home_psychological_state == "desperate" and home_recent_wins >= 2:
        most_likely_path = "home_scores_first"
        most_likely_scoreline = "2-1" if away_recent_wins >= 2 else "2-0"
        narrative = f"{home_team} are desperate and have found form. Expect them to start strong at home."
    elif away_psychological_state == "comfortable" and away_recent_wins >= 3:
        most_likely_path = "away_scores_first"
        most_likely_scoreline = "0-2"
        narrative = f"{away_team} are confident and in form. Could be a comfortable away win."
    elif home_recent_losses >= 3 and away_recent_losses >= 3:
        most_likely_path = "goalless_at_60"
        most_likely_scoreline = "1-1"
        narrative = "Two teams low on confidence. Expect a cagey affair with late drama."
    else:
        most_likely_path = "home_scores_first"
        most_likely_scoreline = "1-1"
        narrative = "Competitive match. Home advantage should count but away team will have chances."
    
    return GameStateTree(
        home_team=home_team,
        away_team=away_team,
        home_scores_first=home_scores_first,
        away_scores_first=away_scores_first,
        goalless_at_60=goalless_at_60,
        most_likely_path=most_likely_path,
        most_likely_scoreline=most_likely_scoreline,
        narrative=narrative,
    )


# ============================================================
# Testing
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Reasoning Tools")
    print("=" * 60)
    
    print("\n1. build_game_state_tree('West Ham', 'Liverpool')")
    tree = build_game_state_tree(
        home_team="West Ham",
        away_team="Liverpool",
        home_psychological_state="desperate",
        away_psychological_state="neutral",
        home_form="LWLDL",
        away_form="WDWLW",
    )
    
    print(f"\n   📖 Narrative: {tree.narrative}")
    print(f"   🎯 Most likely: {tree.most_likely_path} → {tree.most_likely_scoreline}")
    
    print(f"\n   If {tree.home_team} scores first:")
    print(f"      {tree.home_scores_first.likely_outcome}")
    
    print(f"\n   If {tree.away_team} scores first:")
    print(f"      {tree.away_scores_first.likely_outcome}")
    
    print(f"\n   If 0-0 at 60':")
    print(f"      {tree.goalless_at_60.likely_outcome}")
    
    print("\n" + "=" * 60)
    print("✅ All tests complete")
