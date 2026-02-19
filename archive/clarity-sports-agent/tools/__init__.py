"""
Tools for the Clarity Sports Agent.

These are the functions the agent uses to query data and build intelligence.
"""

from .team_tools import (
    get_team_state,
    get_team_form,
    get_team_profile,
    get_psychological_state,
    get_last_match_summary,
)

from .player_tools import (
    get_player_state,
    get_key_players,
    get_injuries_impact,
)

from .matchup_tools import (
    get_h2h,
    get_matchup_analysis,
)

from .market_tools import (
    get_odds,
)

from .external_tools import (
    search_news,
)

from .reasoning_tools import (
    build_game_state_tree,
)

__all__ = [
    # Team tools
    "get_team_state",
    "get_team_form", 
    "get_team_profile",
    "get_psychological_state",
    "get_last_match_summary",
    # Player tools
    "get_player_state",
    "get_key_players",
    "get_injuries_impact",
    # Matchup tools
    "get_h2h",
    "get_matchup_analysis",
    # Market tools
    "get_odds",
    # External tools
    "search_news",
    # Reasoning tools
    "build_game_state_tree",
]
