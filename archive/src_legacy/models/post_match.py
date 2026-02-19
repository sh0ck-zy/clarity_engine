"""
Post-Match Reality Schema

Ground truth - what actually happened in the match.
Used to validate predictions and train models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from enum import Enum


# ============================================================
# ENUMS
# ============================================================

class GoalType(Enum):
    OPEN_PLAY = "open_play"
    SET_PIECE_CORNER = "corner"
    SET_PIECE_FREE_KICK = "free_kick"
    PENALTY = "penalty"
    OWN_GOAL = "own_goal"
    HEADER = "header"
    COUNTER_ATTACK = "counter"


class CardType(Enum):
    YELLOW = "yellow"
    RED = "red"
    SECOND_YELLOW = "second_yellow"


# ============================================================
# GOALS
# ============================================================

@dataclass
class Goal:
    """A goal scored in the match."""
    minute: int
    added_time: Optional[int]     # e.g., 45+2
    team_id: str
    team_name: str
    
    # Scorer
    scorer_id: str
    scorer_name: str
    
    # Assist
    assist_id: Optional[str]
    assist_name: Optional[str]
    
    # Type
    goal_type: GoalType
    is_penalty: bool
    is_own_goal: bool
    
    # Context
    score_at_time: str            # "1-0", "2-1", etc.
    description: Optional[str]    # "Header from corner"


# ============================================================
# CARDS
# ============================================================

@dataclass
class Card:
    """A card shown in the match."""
    minute: int
    team_id: str
    player_id: str
    player_name: str
    card_type: CardType
    reason: Optional[str]


# ============================================================
# SUBSTITUTIONS
# ============================================================

@dataclass
class Substitution:
    """A substitution made."""
    minute: int
    team_id: str
    player_out_id: str
    player_out_name: str
    player_in_id: str
    player_in_name: str
    
    # Impact (optional, can be filled later)
    tactical_reason: Optional[str]  # "injury", "tactical", "fatigue"


# ============================================================
# LINEUPS
# ============================================================

@dataclass
class PlayerInLineup:
    """A player in the starting XI or bench."""
    player_id: str
    name: str
    position: str
    shirt_number: int
    is_starter: bool
    minutes_played: Optional[int]
    rating: Optional[float]       # Match rating if available


@dataclass
class TeamLineup:
    """Full lineup for a team."""
    team_id: str
    team_name: str
    formation: str                # "4-3-3", "3-5-2", etc.
    
    starting_xi: List[PlayerInLineup]
    substitutes: List[PlayerInLineup]
    
    coach_id: Optional[str]
    coach_name: Optional[str]


# ============================================================
# MATCH STATISTICS
# ============================================================

@dataclass
class TeamMatchStats:
    """Statistics for one team in the match."""
    team_id: str
    
    # Possession
    possession: float             # Percentage
    
    # Shots
    shots_total: int
    shots_on_target: int
    shots_off_target: int
    shots_blocked: int
    shots_inside_box: int
    shots_outside_box: int
    
    # Expected goals
    xg: float
    xg_open_play: Optional[float]
    xg_set_piece: Optional[float]
    xg_penalty: Optional[float]
    
    # Passing
    passes_total: int
    passes_accurate: int
    pass_accuracy: float
    key_passes: int
    
    # Defense
    tackles: int
    interceptions: int
    clearances: int
    blocks: int
    
    # Set pieces
    corners: int
    free_kicks: int
    
    # Discipline
    fouls: int
    yellow_cards: int
    red_cards: int
    
    # Other
    offsides: int
    saves: Optional[int]          # Goalkeeper saves


@dataclass
class MatchStatistics:
    """Combined statistics for both teams."""
    fixture_id: str
    home_stats: TeamMatchStats
    away_stats: TeamMatchStats
    
    # Derived
    total_xg: float
    xg_difference: float          # home_xg - away_xg


# ============================================================
# KEY MOMENTS
# ============================================================

@dataclass
class KeyMoment:
    """A significant moment that affected the match."""
    minute: int
    type: str                     # "goal", "red_card", "penalty_miss", "var", "injury"
    description: str
    impact: str                   # "game_changing", "significant", "minor"
    team_affected: Optional[str]


# ============================================================
# POST-MATCH REALITY (ground truth)
# ============================================================

@dataclass
class PostMatchReality:
    """Complete post-match data - what actually happened."""
    
    # Identity
    fixture_id: str
    
    # Result
    score_home: int
    score_away: int
    score_ht_home: int
    score_ht_away: int
    winner: str                   # "home" | "away" | "draw"
    
    # Goals detail
    goals: List[Goal]
    
    # Lineups
    home_lineup: TeamLineup
    away_lineup: TeamLineup
    
    # Stats
    statistics: MatchStatistics
    
    # Events
    cards: List[Card]
    substitutions: List[Substitution]
    
    # Key moments (curated)
    key_moments: List[KeyMoment] = field(default_factory=list)
    
    # Narrative outcome (optional - from analysis)
    match_story: Optional[str] = None       # "Dominant display from Liverpool"
    key_battles_result: Optional[str] = None
    tactical_notes: Optional[str] = None
    
    # Meta
    sources: List[str] = field(default_factory=list)
    collected_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"


# ============================================================
# MATCH RECORD (Pre + Post combined)
# ============================================================

@dataclass
class MatchRecord:
    """
    Complete match record with both pre-match context and post-match reality.
    This is what we store in the database for each match.
    """
    fixture_id: str
    
    # The full picture
    pre_match: 'PreMatchContext'   # Forward reference
    post_match: PostMatchReality
    
    # Validation
    pre_match_valid: bool
    post_match_valid: bool
    validation_notes: List[str] = field(default_factory=list)
    
    # Meta
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
