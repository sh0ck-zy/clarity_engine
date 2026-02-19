"""
Pre-Match Context Schema

All data we know BEFORE the match kicks off.
Used for analysis and predictions.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional
from enum import Enum


# ============================================================
# ENUMS
# ============================================================

class FormTrend(Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    VOLATILE = "volatile"


# ============================================================
# FIXTURE
# ============================================================

@dataclass
class Fixture:
    """Basic match information."""
    fixture_id: str
    competition: str
    competition_id: int
    season: str
    round: str
    match_date: date
    kickoff_time: datetime
    venue: str
    home_team_id: str
    away_team_id: str
    home_team_name: str
    away_team_name: str


# ============================================================
# TEAM SNAPSHOT (point-in-time)
# ============================================================

@dataclass
class TeamSnapshot:
    """Team state at a specific point in time."""
    team_id: str
    name: str
    
    # League position
    league_position: int
    points: int
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    
    # Form
    form_last_5: str              # "WWDLW"
    form_trend: FormTrend
    home_record: str              # "5W-2D-1L"
    away_record: str
    
    # Strength
    elo: int
    elo_attack: Optional[float] = None
    elo_defense: Optional[float] = None


# ============================================================
# TEAM SEASON STATS
# ============================================================

@dataclass
class TeamSeasonStats:
    """Aggregated season statistics."""
    team_id: str
    
    # Expected goals
    xg_for: float
    xg_against: float
    xg_diff: float
    
    # Per game averages
    avg_possession: float
    shots_per_game: float
    shots_against_per_game: float
    shots_on_target_per_game: float
    
    # Set pieces
    corners_per_game: float
    set_piece_goals: int
    set_piece_conceded: int
    
    # Optional advanced
    ppda: Optional[float] = None              # Pressing intensity
    deep_completions: Optional[float] = None  # Passes into box


# ============================================================
# PLAYER AVAILABILITY
# ============================================================

@dataclass
class PlayerAbsence:
    """A player who will miss the match."""
    player_id: str
    player_name: str
    team_id: str
    position: str                 # "GK", "CB", "CM", "ST", etc.
    
    # Absence info
    reason: str                   # "injury" | "suspension" | "other"
    injury_type: Optional[str]    # "hamstring", "knee", etc.
    out_since: Optional[date]
    expected_return: Optional[date]
    
    # Impact
    games_missed: int
    importance: float             # 0-10, how important to the team
    
    # Adaptation context
    team_adapted: bool            # True if games_missed >= 3
    replacement_quality: float    # 0-10


@dataclass
class TeamAvailability:
    """All absences for a team."""
    team_id: str
    absences: List[PlayerAbsence]
    
    # Summary
    total_missing: int
    missing_key_players: int      # importance > 7
    total_importance_lost: float  # Sum of importance
    adapted_absences: int         # Long-term absences team adapted to


# ============================================================
# HEAD TO HEAD
# ============================================================

@dataclass
class HeadToHead:
    """Historical record between two teams."""
    home_team_id: str
    away_team_id: str
    
    # Last N matches
    matches_analyzed: int
    home_wins: int
    draws: int
    away_wins: int
    
    # Goals
    avg_total_goals: float
    avg_home_goals: float
    avg_away_goals: float
    
    # Recent results
    last_5_results: List[str]     # ["2-1", "0-0", "1-3", ...]
    last_5_home_results: List[str]
    
    # Pattern
    pattern: Optional[str]        # "high_scoring", "tight", "home_dominant"


# ============================================================
# ODDS
# ============================================================

@dataclass
class MatchOdds:
    """Betting odds snapshot."""
    fixture_id: str
    captured_at: datetime
    bookmaker: str
    
    # 1X2
    home_win: float
    draw: float
    away_win: float
    
    # Goals
    over_25: Optional[float] = None
    under_25: Optional[float] = None
    btts_yes: Optional[float] = None
    btts_no: Optional[float] = None
    
    # Derived
    implied_prob_home: Optional[float] = None
    implied_prob_draw: Optional[float] = None
    implied_prob_away: Optional[float] = None


# ============================================================
# NARRATIVES (calculated, not agent-based)
# ============================================================

@dataclass
class MatchNarratives:
    """Contextual storylines for the match."""
    fixture_id: str
    
    # Match type
    is_derby: bool
    is_rivalry: bool
    is_six_pointer: bool          # Both teams in similar position/battle
    
    # Stakes
    home_stakes: str              # "Must win to avoid relegation"
    away_stakes: str              # "Win secures top 4"
    
    # Pressure (inferred from results)
    home_under_pressure: bool     # 4+ games without win
    away_under_pressure: bool


# ============================================================
# TACTICAL PROFILE (from agents - can be None)
# ============================================================

@dataclass
class TacticalProfile:
    """How the team plays (populated by agents)."""
    team_id: str
    
    # Formation
    primary_formation: str
    formation_variants: List[str]
    
    # Style
    playing_style: str            # "possession", "counter", "direct", "high_press"
    defensive_line: str           # "high", "medium", "low"
    build_up: str                 # "central", "wide", "long"
    chance_creation: str          # "crosses", "through_balls", "set_pieces"
    
    # Confidence
    source: str                   # "agent", "manual", "inferred"
    confidence: float             # 0-1


# ============================================================
# DECISIVE PLAYERS (partial from API, enriched by agents)
# ============================================================

@dataclass
class KeyPlayer:
    """A player who could decide the match."""
    player_id: str
    name: str
    team_id: str
    position: str
    
    # Stats
    goals_season: int
    assists_season: int
    goals_last_5: int
    minutes_last_5: int
    
    # Roles
    is_penalty_taker: bool
    is_set_piece_taker: bool
    
    # Agent-enriched (optional)
    threat_description: Optional[str] = None
    big_game_record: Optional[str] = None


# ============================================================
# PRE-MATCH CONTEXT (the full picture)
# ============================================================

@dataclass
class PreMatchContext:
    """Complete pre-match context for analysis."""
    
    # Core
    fixture: Fixture
    
    # Teams (point-in-time snapshots)
    home_snapshot: TeamSnapshot
    away_snapshot: TeamSnapshot
    
    # Season stats
    home_stats: TeamSeasonStats
    away_stats: TeamSeasonStats
    
    # Availability
    home_availability: TeamAvailability
    away_availability: TeamAvailability
    
    # H2H
    head_to_head: HeadToHead
    
    # Market
    odds: Optional[MatchOdds]
    
    # Context
    narratives: MatchNarratives
    
    # Tactical (optional - from agents)
    home_tactical: Optional[TacticalProfile] = None
    away_tactical: Optional[TacticalProfile] = None
    
    # Key players
    home_key_players: List[KeyPlayer] = field(default_factory=list)
    away_key_players: List[KeyPlayer] = field(default_factory=list)
    
    # Meta
    coverage_score: float = 0.0   # 0-100, completeness
    sources: List[str] = field(default_factory=list)
    built_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"
