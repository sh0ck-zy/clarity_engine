"""
Match Context V3 — Based on Reverse Engineering of Real Match Analysis

The 6 Essential Pillars that actually explain match outcomes:
1. Tactical Profile — HOW does this team play?
2. Known Vulnerabilities — What can be exploited?
3. Decisive Players — Who decides big games?
4. Absence Context — Who's missing and is team adapted?
5. Narratives — What's the story/motivation?
6. Current State — Form, confidence, fatigue

Each field answers a specific QUESTION about the match.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date
from enum import Enum


# ============================================================
# ENUMS
# ============================================================

class PlayingStyle(Enum):
    POSSESSION = "possession"           # Build up, control
    COUNTER_ATTACK = "counter_attack"   # Defend, hit on break
    DIRECT = "direct"                   # Long balls, physical
    HIGH_PRESS = "high_press"           # Win ball high, transition
    LOW_BLOCK = "low_block"             # Deep defend, compact


class DefensiveLine(Enum):
    HIGH = "high"       # Offside trap, vulnerable to balls behind
    MEDIUM = "medium"   # Balanced
    LOW = "low"         # Deep, hard to break down


class FormTrend(Enum):
    IMPROVING = "improving"     # Getting better
    STABLE = "stable"           # Consistent
    DECLINING = "declining"     # Getting worse
    VOLATILE = "volatile"       # Up and down


# ============================================================
# PILLAR 1: TACTICAL PROFILE
# Question: HOW does this team play?
# ============================================================

@dataclass
class TacticalProfile:
    """How the team sets up and plays."""
    
    # Formation
    primary_formation: str              # e.g., "4-3-3", "3-5-2"
    formation_variants: List[str]       # Alternative setups used
    
    # Style
    playing_style: PlayingStyle         # Primary approach
    defensive_line: DefensiveLine       # High/medium/low
    
    # Metrics that reveal style
    avg_possession: float               # % possession typically
    ppda: float                         # Pressing intensity (lower = more pressing)
    field_tilt: float                   # % of play in opponent's third
    
    # Tendencies
    build_up_through: str               # "central", "wide_left", "wide_right", "long"
    chance_creation: str                # "crosses", "through_balls", "set_pieces", "individual"
    
    # Source & confidence
    source: str                         # "api_football", "agent_search", "manual"
    confidence: float                   # 0-1, how reliable is this profile


# ============================================================
# PILLAR 2: KNOWN VULNERABILITIES
# Question: What can be exploited?
# ============================================================

@dataclass
class Vulnerability:
    """A specific weakness that can be exploited."""
    
    description: str                    # e.g., "High line vulnerable to balls behind"
    how_to_exploit: str                 # e.g., "Fast forwards making runs"
    times_exploited_this_season: int    # How often it's been punished
    example_match: Optional[str]        # e.g., "Lost 3-0 to Liverpool, 2 goals from through balls"


@dataclass
class TeamVulnerabilities:
    """Collection of known weaknesses."""
    
    defensive: List[Vulnerability]      # Defensive weaknesses
    offensive: List[Vulnerability]      # Attacking limitations
    mental: List[Vulnerability]         # Psychological weaknesses (e.g., "collapse when behind")
    
    # Set piece specific
    weak_at_defending_corners: bool
    weak_at_defending_direct_free_kicks: bool


# ============================================================
# PILLAR 3: DECISIVE PLAYERS
# Question: Who decides big games?
# ============================================================

@dataclass
class DecisivePlayer:
    """A player who makes the difference in key moments."""
    
    name: str
    position: str
    
    # What makes them decisive
    role: str                           # e.g., "goal_scorer", "creator", "playmaker", "leader"
    big_game_goals: int                 # Goals vs top 6 / in crucial games
    big_game_assists: int               # Assists in big games
    clutch_rating: float                # 0-10, how often they deliver when it matters
    
    # Current form
    goals_last_5: int
    assists_last_5: int
    minutes_last_5: int
    
    # Threat description
    threat_description: str             # e.g., "Lethal in 1v1, takes penalties, set piece specialist"


# ============================================================
# PILLAR 4: ABSENCE CONTEXT
# Question: Who's missing AND is the team adapted?
# ============================================================

@dataclass
class AbsenceWithContext:
    """A missing player with adaptation context."""
    
    player_name: str
    position: str
    
    # Absence details
    reason: str                         # "injury", "suspension", "other"
    injury_type: Optional[str]          # e.g., "hamstring", "knee"
    out_since: date                     # When they got injured/suspended
    expected_return: Optional[date]
    
    # Adaptation context - THIS IS KEY
    games_missed: int                   # How many games missed
    team_record_without: str            # e.g., "2W-1D-2L"
    team_adapted: bool                  # True if games_missed >= 3
    
    # Impact assessment
    base_impact: float                  # 0-10, how important is this player normally
    real_impact: float                  # Adjusted for adaptation (lower if team adapted)
    
    # Replacement info
    likely_replacement: str             # Who plays instead
    replacement_quality: float          # 0-10, how good is the replacement


@dataclass
class AbsencesSummary:
    """Summary of all absences with context."""
    
    players: List[AbsenceWithContext]
    
    # Aggregated impact
    total_missing: int
    total_real_impact: float            # Sum of real_impact (not base_impact)
    
    # Key flags
    missing_key_scorer: bool
    missing_key_creator: bool
    missing_goalkeeper: bool
    missing_captain: bool
    
    # Adaptation summary
    fully_adapted_absences: int         # Players out long enough that team adapted
    fresh_absences: int                 # Recent absences, team still adjusting


# ============================================================
# PILLAR 5: NARRATIVES & MOTIVATION
# Question: What's the story behind this match?
# ============================================================

@dataclass
class MatchNarrative:
    """A storyline that adds context/motivation."""
    
    narrative_type: str                 # "revenge", "ex_player", "relegation_battle", "title_race", "historic"
    description: str                    # The actual story
    affects_team: str                   # "home", "away", "both"
    motivation_boost: float             # 0-10, how much extra motivation does this give


@dataclass
class MatchNarratives:
    """All narratives for this match."""
    
    storylines: List[MatchNarrative]
    
    # Specific flags
    is_derby: bool
    is_rivalry: bool
    is_six_pointer: bool                # Relegation/European spot battle
    is_title_decider: bool
    
    # Stakes
    home_team_stakes: str               # e.g., "Must win to avoid relegation zone"
    away_team_stakes: str               # e.g., "Win would secure top 4"
    
    # Manager context
    manager_h2h_record: str             # e.g., "Slot 2W-1D-0L vs Guardiola"
    manager_pressure: str               # "home_under_pressure", "away_under_pressure", "both", "neither"


# ============================================================
# PILLAR 6: CURRENT STATE
# Question: What's the team's current condition?
# ============================================================

@dataclass
class CurrentState:
    """The team's current form and condition."""
    
    # Form
    last_5_results: str                 # e.g., "W-W-D-L-W"
    last_5_points: int
    form_trend: FormTrend               # Improving, stable, declining, volatile
    
    # Performance metrics
    last_5_xg: float                    # xG created
    last_5_xga: float                   # xG conceded
    last_5_goals_for: int
    last_5_goals_against: int
    
    # Quality of opposition faced
    avg_opponent_elo_last_5: int
    
    # Physical state
    days_since_last_match: int
    matches_last_14_days: int
    is_fatigued: bool
    
    # Psychological state (inferred)
    confidence_level: str               # "high", "medium", "low"
    recent_momentum: str                # "positive", "neutral", "negative"


# ============================================================
# MAIN CONTEXT: ALL 6 PILLARS
# ============================================================

@dataclass
class TeamMatchContext:
    """Complete context for one team in a match."""
    
    # Identity
    name: str
    is_home: bool
    
    # The 6 Pillars
    tactical_profile: TacticalProfile
    vulnerabilities: TeamVulnerabilities
    decisive_players: List[DecisivePlayer]
    absences: AbsencesSummary
    current_state: CurrentState
    
    # Basic stats (for reference)
    elo: int
    league_position: int
    points: int
    goal_difference: int


@dataclass
class MatchContextV3:
    """Complete match context with all 6 pillars for both teams."""
    
    # Match info
    fixture_id: str
    match_date: date
    competition: str
    round_number: str
    
    # Teams
    home: TeamMatchContext
    away: TeamMatchContext
    
    # Match-level context
    narratives: MatchNarratives
    
    # Head to head
    h2h_last_5: str                     # e.g., "Home: 2W-2D-1L"
    h2h_avg_goals: float
    h2h_pattern: str                    # e.g., "Home team usually wins", "High-scoring affairs"
    
    # Tactical matchup analysis
    tactical_matchup: str               # e.g., "High press vs low block - expect transition game"
    key_battle: str                     # e.g., "Salah vs Robertson's replacement"
    
    # Meta
    coverage_score: float               # 0-100, how complete is this context
    data_sources: List[str]             # ["api_football", "transfermarkt", "agent_search"]
    built_at: str
    version: str = "3.0.0"
