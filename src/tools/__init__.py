"""
Agent Tools for Clarity Football Intelligence.

These tools provide the interface between the reasoning agent and the knowledge graph.
Each tool abstracts database queries and returns structured, interpretable data.

Tools:
- Team: get_team_state, get_team_form, get_team_profile, get_formation_history
- Manager: get_manager_info
- Player: get_key_players, get_injuries_impact
- Match: get_last_match_summary, get_h2h, get_matchup_analysis
- Context: get_psychological_state, search_news, get_odds, build_game_state_tree
- Helpers: odds_to_probability, calculate_value
"""

from .base import (
    ToolResponse,
    TEAM_ALIASES,
    resolve_team,
    get_team_name,
    get_current_round,
)
from .team_tools import (
    get_team_state,
    get_team_form,
    get_team_profile,
    get_formation_history,
)
from .manager_tools import (
    get_manager_info,
)
from .player_tools import (
    get_key_players,
    get_injuries_impact,
)
from .match_tools import (
    get_last_match_summary,
    get_h2h,
    get_matchup_analysis,
)
from .context_tools import (
    get_psychological_state,
    search_news,
    search_press_conference,
    get_odds,
    build_game_state_tree,
    odds_to_probability,
    calculate_value,
)

__all__ = [
    # Base utilities
    "ToolResponse",
    "TEAM_ALIASES",
    "resolve_team",
    "get_team_name",
    "get_current_round",
    # Team tools
    "get_team_state",
    "get_team_form", 
    "get_team_profile",
    "get_formation_history",
    # Manager tools
    "get_manager_info",
    # Player tools
    "get_key_players",
    "get_injuries_impact",
    # Match tools
    "get_last_match_summary",
    "get_h2h",
    "get_matchup_analysis",
    # Context tools
    "get_psychological_state",
    "search_news",
    "search_press_conference",
    "get_odds",
    "build_game_state_tree",
    # Odds helpers
    "odds_to_probability",
    "calculate_value",
]
