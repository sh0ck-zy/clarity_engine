"""
Temporal Knowledge Graph Schema

For each round, for each team, we capture a KG snapshot that answers
deterministic questions across 8 intelligence layers.

This enables:
- Week-to-week comparison of team state
- Detection of emerging behaviors
- Feature attribution (what's driving changes)

Architecture:
    Round 1 → TeamSnapshot(Liverpool) → 8 layers answered
    Round 2 → TeamSnapshot(Liverpool) → 8 layers answered
    ...
    Compare → Diff → Emerging patterns → Trace to features

Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


# ============================================================
# THE 8 INTELLIGENCE LAYERS (deterministic questions)
# ============================================================

class IntelligenceLayer(Enum):
    """The 8 layers of deterministic questions per team per round."""
    
    # 1. IDENTITY - Who are they?
    IDENTITY = "identity"
    
    # 2. POSITION - Where are they in the table?
    POSITION = "position"
    
    # 3. FORM - How are they performing recently?
    FORM = "form"
    
    # 4. STYLE - How do they play?
    STYLE = "style"
    
    # 5. PERSONNEL - Who's available and in form?
    PERSONNEL = "personnel"
    
    # 6. ATTACK - How do they create and finish chances?
    ATTACK = "attack"
    
    # 7. DEFENSE - How do they prevent chances?
    DEFENSE = "defense"
    
    # 8. MOMENTUM - What's their trajectory?
    MOMENTUM = "momentum"


# ============================================================
# LAYER 1: IDENTITY
# ============================================================

@dataclass
class IdentityLayer:
    """
    Layer 1: IDENTITY - Who are they?
    
    Questions answered:
    - What's their ID and name?
    - What league/competition?
    - What's their budget tier?
    - What's their historical expectation?
    """
    team_id: int
    team_name: str
    league_id: int
    league_name: str
    season: str
    
    # Classification
    tier: str = ""               # "big_6", "mid_table", "relegation_battle"
    budget_rank: Optional[int] = None
    historical_avg_position: Optional[float] = None
    
    # Identifiers
    fotmob_id: Optional[int] = None
    api_football_id: Optional[int] = None


# ============================================================
# LAYER 2: POSITION
# ============================================================

@dataclass
class PositionLayer:
    """
    Layer 2: POSITION - Where are they in the table?
    
    Questions answered:
    - What's their current position?
    - How many points?
    - What's the gap to positions above/below?
    - Are they over/underperforming expected position?
    """
    # Current standing
    position: int
    points: int
    played: int
    
    # Record
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    
    # Gaps
    points_to_first: int = 0
    points_to_top_4: int = 0
    points_to_relegation: int = 0
    points_to_above: int = 0
    points_to_below: int = 0
    
    # Expected vs actual
    xPoints: Optional[float] = None          # Based on xG
    position_vs_xPoints: Optional[int] = None  # Difference
    
    # Home/Away split
    home_position: Optional[int] = None
    away_position: Optional[int] = None
    home_points: int = 0
    away_points: int = 0


# ============================================================
# LAYER 3: FORM
# ============================================================

@dataclass
class FormLayer:
    """
    Layer 3: FORM - How are they performing recently?
    
    Questions answered:
    - What's their last 5/10 results?
    - What's the xG trend?
    - Are they over/underperforming xG?
    - What's the regression risk?
    """
    # Results form
    last_5_results: str = ""     # "WWDLW"
    last_5_points: int = 0
    last_10_results: str = ""
    last_10_points: int = 0
    
    # Goals form
    goals_scored_last_5: int = 0
    goals_conceded_last_5: int = 0
    clean_sheets_last_5: int = 0
    
    # xG form (more predictive)
    xG_for_last_5: float = 0.0
    xG_against_last_5: float = 0.0
    xG_diff_last_5: float = 0.0
    
    # Performance vs expectation
    goals_vs_xG_last_5: float = 0.0      # Positive = overperforming
    goals_conceded_vs_xGA_last_5: float = 0.0
    
    # Trend
    form_trend: str = ""         # "improving", "stable", "declining"
    xG_trend: str = ""           # "improving", "stable", "declining"
    
    # Risk assessment
    is_overperforming: bool = False
    is_underperforming: bool = False
    regression_probability: float = 0.0


# ============================================================
# LAYER 4: STYLE
# ============================================================

@dataclass
class StyleLayer:
    """
    Layer 4: STYLE - How do they play?
    
    Questions answered:
    - What's their primary formation?
    - What's their playing style?
    - Possession or direct?
    - High press or low block?
    """
    # Formation
    primary_formation: str = ""
    formation_variants: List[str] = field(default_factory=list)
    formation_consistency: float = 0.0   # How often same formation
    
    # Style classification
    primary_style: str = ""      # "possession", "counter", "direct", "pressing"
    secondary_style: str = ""
    style_confidence: float = 0.0
    
    # Possession
    avg_possession: float = 0.0
    possession_in_wins: float = 0.0
    possession_in_losses: float = 0.0
    possession_dependency: float = 0.0   # Do they need possession to win?
    
    # Build-up
    passes_per_game: float = 0.0
    pass_accuracy: float = 0.0
    progressive_passes: float = 0.0
    build_up_speed: str = ""     # "slow", "balanced", "fast"
    
    # Pressing
    ppda: Optional[float] = None         # Passes per defensive action
    high_press_intensity: float = 0.0
    counter_press_success: float = 0.0
    
    # Width
    attacks_left_pct: float = 0.0
    attacks_center_pct: float = 0.0
    attacks_right_pct: float = 0.0


# ============================================================
# LAYER 5: PERSONNEL
# ============================================================

@dataclass
class PlayerStatus:
    """Individual player status."""
    player_id: int
    player_name: str
    position: str
    
    # Availability
    is_available: bool = True
    injury: Optional[str] = None
    suspension: Optional[str] = None
    
    # Form
    minutes_last_5: int = 0
    avg_rating_last_5: Optional[float] = None
    goals_last_5: int = 0
    assists_last_5: int = 0
    
    # Importance
    importance_score: float = 0.0  # 0-10


@dataclass
class PersonnelLayer:
    """
    Layer 5: PERSONNEL - Who's available and in form?
    
    Questions answered:
    - Who's injured/suspended?
    - Who's in form?
    - What's the squad depth?
    - What's the impact of absences?
    """
    # Squad status
    total_squad_size: int = 0
    available_players: int = 0
    injured_players: int = 0
    suspended_players: int = 0
    
    # Key players
    key_players: List[PlayerStatus] = field(default_factory=list)
    key_players_available: int = 0
    key_players_missing: int = 0
    
    # Top performers (last 5)
    top_scorer: Optional[PlayerStatus] = None
    top_assister: Optional[PlayerStatus] = None
    top_rated: Optional[PlayerStatus] = None
    
    # Impact assessment
    missing_importance_total: float = 0.0  # Sum of importance of missing
    squad_strength_pct: float = 100.0      # % of full strength
    
    # Fatigue
    avg_minutes_last_3_weeks: float = 0.0
    rotation_level: str = ""     # "high", "medium", "low"


# ============================================================
# LAYER 6: ATTACK
# ============================================================

@dataclass
class AttackLayer:
    """
    Layer 6: ATTACK - How do they create and finish chances?
    
    Questions answered:
    - How many shots/chances per game?
    - What's their xG per game?
    - Where do shots come from?
    - How clinical are they?
    """
    # Volume
    shots_per_game: float = 0.0
    shots_on_target_per_game: float = 0.0
    big_chances_per_game: float = 0.0
    
    # Quality
    xG_per_game: float = 0.0
    xG_per_shot: float = 0.0     # Shot quality
    
    # Location
    shots_inside_box_pct: float = 0.0
    shots_outside_box_pct: float = 0.0
    
    # Conversion
    goals_per_game: float = 0.0
    conversion_rate: float = 0.0
    big_chance_conversion: float = 0.0
    
    # xG performance
    goals_minus_xG: float = 0.0  # Positive = clinical
    is_clinical: bool = False
    is_wasteful: bool = False
    
    # Set pieces
    set_piece_goals: int = 0
    set_piece_xG_pct: float = 0.0
    corners_per_game: float = 0.0
    
    # Danger periods
    most_dangerous_period: str = ""  # "0-15", "75-90", etc.
    late_goals_scored: int = 0


# ============================================================
# LAYER 7: DEFENSE
# ============================================================

@dataclass
class DefenseLayer:
    """
    Layer 7: DEFENSE - How do they prevent chances?
    
    Questions answered:
    - How many shots/chances conceded?
    - What's their xGA per game?
    - Where do they concede from?
    - Clean sheet rate?
    """
    # Volume conceded
    shots_against_per_game: float = 0.0
    shots_on_target_against: float = 0.0
    big_chances_against: float = 0.0
    
    # Quality conceded
    xG_against_per_game: float = 0.0
    xG_per_shot_against: float = 0.0
    
    # Actual goals
    goals_against_per_game: float = 0.0
    clean_sheets: int = 0
    clean_sheet_rate: float = 0.0
    
    # xGA performance
    goals_conceded_minus_xGA: float = 0.0
    is_solid: bool = False       # Conceding less than expected
    is_leaky: bool = False       # Conceding more than expected
    
    # Vulnerability areas
    goals_from_set_pieces: int = 0
    goals_from_counters: int = 0
    goals_from_crosses: int = 0
    
    # Danger periods
    most_vulnerable_period: str = ""
    late_goals_conceded: int = 0
    
    # Recovery
    goals_conceded_after_conceding: int = 0  # Collapse indicator


# ============================================================
# LAYER 8: MOMENTUM
# ============================================================

@dataclass
class MomentumLayer:
    """
    Layer 8: MOMENTUM - What's their trajectory?
    
    Questions answered:
    - Are they improving or declining?
    - What's the confidence level?
    - Home vs away trajectory?
    - Next match context?
    """
    # Overall trajectory
    trajectory: str = ""         # "ascending", "stable", "descending"
    trajectory_strength: float = 0.0  # How strong is the trend
    
    # Results trajectory
    points_last_5_vs_prev_5: int = 0
    position_change_last_5: int = 0
    
    # Performance trajectory
    xG_diff_trend: str = ""      # "improving", "stable", "declining"
    rating_trend: str = ""
    
    # Confidence
    team_confidence: str = ""    # "high", "medium", "low"
    confidence_factors: List[str] = field(default_factory=list)
    
    # Home/Away split
    home_trajectory: str = ""
    away_trajectory: str = ""
    
    # Context
    fixture_difficulty_next_5: float = 0.0
    is_in_cup_competitions: bool = False
    matches_in_next_14_days: int = 0
    
    # Pressure
    is_under_pressure: bool = False
    pressure_type: str = ""      # "relegation", "top_4", "title", "manager"


# ============================================================
# TEAM KG SNAPSHOT (per round)
# ============================================================

@dataclass
class TeamKGSnapshot:
    """
    Complete Knowledge Graph snapshot for a team at a specific round.
    
    This captures the state of all 8 layers at a point in time,
    enabling week-to-week comparison and trend analysis.
    """
    # Identity
    team_id: int
    team_name: str
    
    # Temporal
    season: str
    round_number: int
    snapshot_date: date
    
    # THE 8 LAYERS
    identity: IdentityLayer
    position: PositionLayer
    form: FormLayer
    style: StyleLayer
    personnel: PersonnelLayer
    attack: AttackLayer
    defense: DefenseLayer
    momentum: MomentumLayer
    
    # Completeness
    layers_complete: int = 0     # Out of 8
    data_sources: List[str] = field(default_factory=list)
    missing_data: List[str] = field(default_factory=list)
    
    # Meta
    built_at: datetime = field(default_factory=datetime.now)
    version: str = "1.0.0"


# ============================================================
# SNAPSHOT COMPARISON (week-to-week diff)
# ============================================================

@dataclass
class LayerDiff:
    """Difference in a single layer between two snapshots."""
    layer: IntelligenceLayer
    
    # Changes
    changed_fields: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)  # field -> (old, new)
    change_magnitude: float = 0.0  # 0-1, how significant
    
    # Direction
    direction: str = ""          # "improved", "declined", "stable"
    
    # Key insight
    summary: str = ""


@dataclass 
class SnapshotDiff:
    """
    Comparison between two TeamKGSnapshots (week-to-week).
    
    This enables:
    - Detecting what changed
    - Identifying emerging behaviors
    - Tracing changes to specific features
    """
    team_id: int
    team_name: str
    
    # Snapshots being compared
    from_round: int
    to_round: int
    from_date: date
    to_date: date
    
    # Layer-by-layer diffs
    layer_diffs: Dict[IntelligenceLayer, LayerDiff] = field(default_factory=dict)
    
    # Overall assessment
    overall_direction: str = ""  # "improving", "stable", "declining"
    change_magnitude: float = 0.0
    
    # Key changes
    biggest_improvement: Optional[IntelligenceLayer] = None
    biggest_decline: Optional[IntelligenceLayer] = None
    
    # Emerging behaviors
    emerging_patterns: List[str] = field(default_factory=list)
    
    # Feature attribution
    driving_features: List[str] = field(default_factory=list)  # What's causing changes
    
    # Alerts
    alerts: List[str] = field(default_factory=list)


# ============================================================
# MATCHUP SNAPSHOT (two teams + comparison for a fixture)
# ============================================================

@dataclass
class MatchupKGSnapshot:
    """
    Complete KG snapshot for a matchup (fixture).
    
    Contains both team snapshots plus the comparison/matchup analysis.
    """
    # Fixture
    fixture_id: int
    round_number: int
    match_date: date
    
    # Team snapshots at this round
    home_snapshot: TeamKGSnapshot
    away_snapshot: TeamKGSnapshot
    
    # Layer-by-layer matchup
    matchup_by_layer: Dict[IntelligenceLayer, Dict[str, Any]] = field(default_factory=dict)
    
    # Overall matchup
    home_advantage_score: float = 0.0  # -1 to 1 (negative = away advantage)
    key_battles: List[str] = field(default_factory=list)
    
    # Predictions (derived from KG comparison)
    predicted_winner: str = ""   # "home", "away", "draw"
    predicted_total_goals: float = 0.0
    confidence: float = 0.0
    
    # Meta
    built_at: datetime = field(default_factory=datetime.now)


# ============================================================
# SEASON EVOLUTION (full trajectory)
# ============================================================

@dataclass
class TeamSeasonEvolution:
    """
    Complete evolution of a team's KG across the season.
    
    Enables:
    - Full trajectory analysis
    - Pattern identification
    - Feature importance over time
    """
    team_id: int
    team_name: str
    season: str
    
    # All snapshots
    snapshots: List[TeamKGSnapshot] = field(default_factory=list)
    
    # Round-to-round diffs
    diffs: List[SnapshotDiff] = field(default_factory=list)
    
    # Aggregated insights
    overall_trajectory: str = ""
    peak_round: Optional[int] = None
    low_round: Optional[int] = None
    
    # Layer evolution
    layer_trajectories: Dict[IntelligenceLayer, str] = field(default_factory=dict)
    
    # Emerging patterns across season
    season_patterns: List[str] = field(default_factory=list)
    
    # Feature importance
    most_predictive_features: List[str] = field(default_factory=list)


# ============================================================
# DETERMINISTIC QUESTIONS PER LAYER
# ============================================================

LAYER_QUESTIONS = {
    IntelligenceLayer.IDENTITY: [
        "What's the team ID and name?",
        "What league/competition?",
        "What's their tier (big 6, mid-table, etc.)?",
        "What's the historical expectation?",
    ],
    IntelligenceLayer.POSITION: [
        "What's their current position?",
        "How many points?",
        "What's the gap to key positions?",
        "Are they over/under xPoints?",
    ],
    IntelligenceLayer.FORM: [
        "What's their last 5/10 results?",
        "What's the xG trend?",
        "Over/underperforming xG?",
        "What's the regression risk?",
    ],
    IntelligenceLayer.STYLE: [
        "What's their primary formation?",
        "What's their playing style?",
        "Possession or direct?",
        "High press or low block?",
    ],
    IntelligenceLayer.PERSONNEL: [
        "Who's injured/suspended?",
        "Who's in form?",
        "What's the squad depth impact?",
        "What's the fatigue level?",
    ],
    IntelligenceLayer.ATTACK: [
        "How many shots/chances per game?",
        "What's their xG per game?",
        "Where do shots come from?",
        "How clinical are they?",
    ],
    IntelligenceLayer.DEFENSE: [
        "How many shots/chances conceded?",
        "What's their xGA per game?",
        "Where do they concede from?",
        "Clean sheet rate?",
    ],
    IntelligenceLayer.MOMENTUM: [
        "Are they improving or declining?",
        "What's the confidence level?",
        "Home vs away trajectory?",
        "What's the fixture difficulty ahead?",
    ],
}


def get_layer_questions(layer: IntelligenceLayer) -> List[str]:
    """Get the deterministic questions for a layer."""
    return LAYER_QUESTIONS.get(layer, [])


def get_all_questions() -> Dict[str, List[str]]:
    """Get all questions organized by layer."""
    return {layer.value: questions for layer, questions in LAYER_QUESTIONS.items()}
