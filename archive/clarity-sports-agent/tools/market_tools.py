"""
Market Tools - Functions for querying odds and market data.

Note: This requires API-Football integration for odds data.
Currently a placeholder with structure ready for integration.
"""

from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path

import sys
AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))


# ============================================================
# Response Models
# ============================================================

@dataclass
class OddsLine:
    """Odds from a bookmaker."""
    bookmaker: str
    home_win: float
    draw: float
    away_win: float
    over_2_5: Optional[float] = None
    under_2_5: Optional[float] = None
    btts_yes: Optional[float] = None
    btts_no: Optional[float] = None


@dataclass
class MatchOdds:
    """Complete odds for a match."""
    home_team: str
    away_team: str
    match_date: str
    
    # Consensus odds (average across bookmakers)
    consensus_home_win: float
    consensus_draw: float
    consensus_away_win: float
    
    # Implied probabilities
    implied_home_prob: float
    implied_draw_prob: float
    implied_away_prob: float
    
    # Individual bookmaker odds
    bookmakers: List[OddsLine]
    
    # Market insight
    market_favourite: str      # "home", "draw", "away"
    confidence: str            # "strong", "slight", "toss-up"


# ============================================================
# Tool Implementations
# ============================================================

def get_odds(home_team: str, away_team: str) -> Optional[MatchOdds]:
    """
    Get odds for a match.
    
    Args:
        home_team: Home team name
        away_team: Away team name
    
    Returns:
        MatchOdds with bookmaker odds and implied probabilities
    
    Note:
        Currently returns placeholder data.
        TODO: Integrate with API-Football odds endpoint.
    """
    # TODO: Implement API-Football odds integration
    # For now, return a placeholder indicating data not available
    
    return MatchOdds(
        home_team=home_team,
        away_team=away_team,
        match_date="",
        consensus_home_win=0.0,
        consensus_draw=0.0,
        consensus_away_win=0.0,
        implied_home_prob=0.0,
        implied_draw_prob=0.0,
        implied_away_prob=0.0,
        bookmakers=[],
        market_favourite="unknown",
        confidence="unknown",
    )


def odds_to_probability(odds: float) -> float:
    """Convert decimal odds to implied probability."""
    if odds <= 0:
        return 0.0
    return 1.0 / odds


def calculate_value(our_prob: float, odds: float) -> float:
    """
    Calculate expected value of a bet.
    
    Args:
        our_prob: Our estimated probability (0-1)
        odds: Decimal odds offered
    
    Returns:
        Expected value (positive = value bet)
    """
    implied_prob = odds_to_probability(odds)
    return (our_prob - implied_prob) * odds


# ============================================================
# Testing
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Market Tools")
    print("=" * 60)
    
    print("\n⚠️  Market tools require API-Football integration")
    print("   Placeholder data returned until implemented")
    
    print("\n1. get_odds('Arsenal', 'Liverpool')")
    odds = get_odds("Arsenal", "Liverpool")
    if odds:
        print(f"   {odds.home_team} vs {odds.away_team}")
        print(f"   Market favourite: {odds.market_favourite}")
    
    print("\n" + "=" * 60)
    print("✅ Structure ready, awaiting API-Football integration")
