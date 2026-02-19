"""
Matchup Intelligence Schema

Pre-match intelligence derived FROM post-match data of previous matches.
This is the core insight: pre-match analysis = aggregated historical post-match data.

Data Flow:
    Past Matches (FotMob post-match) → Aggregation → Matchup Intelligence → Pre-match Context

Example:
    Liverpool vs Arsenal upcoming:
    - Last 10 Liverpool matches → Liverpool team profile
    - Last 10 Arsenal matches → Arsenal team profile  
    - Last 5 Liverpool vs Arsenal → H2H intelligence
    - Player performances → Key matchup predictions

Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


# ============================================================
# ENUMS
# ============================================================

class PlayingStyle(Enum):
    """Derived from historical data patterns."""
    POSSESSION = "possession"
    COUNTER_ATTACK = "counter_attack"
    DIRECT = "direct"
    HIGH_PRESS = "high_press"
    LOW_BLOCK = "low_block"
    BALANCED = "balanced"


class FormTrend(Enum):
    """Form trajectory derived from results + xG."""
    HOT = "hot"                  # Winning + overperforming xG
    GOOD = "good"                # Winning, in line with xG
    STABLE = "stable"            # Mixed results, stable xG
    COLD = "cold"                # Losing, underperforming xG
    VOLATILE = "volatile"        # Inconsistent


class StrengthLevel(Enum):
    """Relative strength assessment."""
    ELITE = "elite"              # Top tier
    STRONG = "strong"            # Above average
    AVERAGE = "average"          # Mid-table level
    WEAK = "weak"                # Below average
    POOR = "poor"                # Bottom tier


# ============================================================
# AGGREGATED PLAYER PROFILE (from historical performances)
# ============================================================

@dataclass
class PlayerHistoricalProfile:
    """
    Player profile aggregated from recent matches.
    
    Built from: FotMob player stats across last N matches
    """
    player_id: int
    player_name: str
    team_id: int
    
    # Role
    primary_position: str
    positions_played: List[str] = field(default_factory=list)
    
    # Availability
    is_available: bool = True
    injury_status: Optional[str] = None
    suspension_status: Optional[str] = None
    
    # Form (last N matches)
    matches_played: int = 0
    minutes_played: int = 0
    avg_rating: Optional[float] = None
    rating_trend: Optional[str] = None  # "improving", "stable", "declining"
    
    # Offensive output
    goals: int = 0
    assists: int = 0
    xG_total: float = 0.0
    xA_total: float = 0.0
    xG_per_90: Optional[float] = None
    xA_per_90: Optional[float] = None
    
    # Shooting profile
    shots_total: int = 0
    shots_on_target: int = 0
    shot_accuracy: Optional[float] = None
    avg_shot_xG: Optional[float] = None  # Quality of chances
    
    # Chance creation
    chances_created: int = 0
    key_passes: int = 0
    
    # Defensive contribution
    tackles: int = 0
    interceptions: int = 0
    defensive_actions: int = 0
    
    # Big game factor
    goals_vs_top_6: int = 0
    avg_rating_vs_top_6: Optional[float] = None
    
    # Special roles
    is_penalty_taker: bool = False
    is_set_piece_taker: bool = False
    is_captain: bool = False
    
    # Aggregation metadata
    matches_analyzed: int = 0
    period_start: Optional[date] = None
    period_end: Optional[date] = None


# ============================================================
# TEAM TACTICAL PROFILE (from historical matches)
# ============================================================

@dataclass
class FormationUsage:
    """Formation and its effectiveness."""
    formation: str              # "4-3-3"
    times_used: int = 0
    win_rate: Optional[float] = None
    avg_xG_for: Optional[float] = None
    avg_xG_against: Optional[float] = None


@dataclass
class ShotProfile:
    """
    Team shooting patterns from historical shotmaps.
    
    Built from: FotMob shotmap data aggregated
    """
    # Volume
    shots_per_game: float = 0.0
    shots_on_target_per_game: float = 0.0
    
    # Quality
    xG_per_game: float = 0.0
    xG_per_shot: float = 0.0     # Shot quality indicator
    
    # Location patterns
    shots_inside_box_pct: float = 0.0
    shots_outside_box_pct: float = 0.0
    
    # Conversion
    conversion_rate: float = 0.0  # Goals / shots
    xG_overperformance: float = 0.0  # Goals - xG (luck/finishing)
    
    # Set pieces
    set_piece_xG_pct: float = 0.0  # % of xG from set pieces


@dataclass
class DefensiveProfile:
    """
    Team defensive patterns from historical data.
    
    Built from: FotMob stats + shotmap (shots conceded)
    """
    # Conceded
    shots_against_per_game: float = 0.0
    xG_against_per_game: float = 0.0
    
    # Quality of chances conceded
    xG_per_shot_against: float = 0.0
    
    # Clean sheets
    clean_sheet_rate: float = 0.0
    
    # Where they're vulnerable
    goals_conceded_first_half_pct: float = 0.0
    goals_conceded_last_15_pct: float = 0.0
    
    # Set piece vulnerability
    set_piece_goals_conceded: int = 0
    set_piece_xG_conceded_pct: float = 0.0


@dataclass
class MomentumProfile:
    """
    Team momentum patterns from historical data.
    
    Built from: FotMob momentum data aggregated
    """
    # Periods of dominance
    strongest_period: str = ""   # "0-15", "75-90", etc.
    weakest_period: str = ""
    
    # Match phases
    avg_first_half_momentum: float = 0.0
    avg_second_half_momentum: float = 0.0
    
    # Response patterns
    momentum_after_conceding: float = 0.0  # Do they collapse or respond?
    momentum_after_scoring: float = 0.0
    
    # Late game
    late_goal_rate: float = 0.0  # Goals in last 15 min
    late_collapse_rate: float = 0.0  # Conceded in last 15


@dataclass
class TeamTacticalProfile:
    """
    Complete tactical profile from historical matches.
    
    Built from: FotMob post-match data (last N matches)
    """
    team_id: int
    team_name: str
    
    # Playing style (derived)
    primary_style: Optional[PlayingStyle] = None
    secondary_style: Optional[PlayingStyle] = None
    style_confidence: float = 0.0  # How consistent
    
    # Formations
    formations: List[FormationUsage] = field(default_factory=list)
    primary_formation: Optional[str] = None
    formation_flexibility: float = 0.0  # Do they change often?
    
    # Attacking
    shot_profile: Optional[ShotProfile] = None
    
    # Defensive
    defensive_profile: Optional[DefensiveProfile] = None
    
    # Momentum
    momentum_profile: Optional[MomentumProfile] = None
    
    # Possession
    avg_possession: float = 0.0
    possession_in_wins: float = 0.0
    possession_in_losses: float = 0.0
    
    # Build-up
    passes_per_game: float = 0.0
    pass_accuracy: float = 0.0
    progressive_passes_per_game: float = 0.0
    
    # Set pieces
    corners_per_game: float = 0.0
    set_piece_goal_rate: float = 0.0
    
    # Key players (derived from ratings)
    key_players: List[PlayerHistoricalProfile] = field(default_factory=list)
    most_important_player: Optional[PlayerHistoricalProfile] = None
    
    # Aggregation metadata
    matches_analyzed: int = 0
    period_start: Optional[date] = None
    period_end: Optional[date] = None


# ============================================================
# TEAM FORM (recent trajectory)
# ============================================================

@dataclass
class RecentMatch:
    """Single match in form analysis."""
    fixture_id: int
    date: date
    opponent_id: int
    opponent_name: str
    
    is_home: bool
    
    # Result
    goals_for: int
    goals_against: int
    result: str  # "W", "D", "L"
    
    # Performance
    xG_for: float
    xG_against: float
    xG_diff: float
    
    # Control
    possession: float
    shots: int
    shots_against: int
    
    # Rating
    avg_team_rating: Optional[float] = None


@dataclass
class TeamForm:
    """
    Recent form with context.
    
    Built from: Last N FotMob post-match records
    """
    team_id: int
    team_name: str
    
    # Results
    last_5_results: str = ""     # "WWDLW"
    last_5_points: int = 0
    last_10_results: str = ""
    last_10_points: int = 0
    
    # Goals
    goals_scored_last_5: int = 0
    goals_conceded_last_5: int = 0
    
    # xG trend (more predictive than results)
    xG_for_last_5: float = 0.0
    xG_against_last_5: float = 0.0
    xG_diff_last_5: float = 0.0
    
    # Trend
    form_trend: Optional[FormTrend] = None
    xG_trend: str = ""           # "improving", "stable", "declining"
    
    # Home/Away split
    home_form_last_5: str = ""
    away_form_last_5: str = ""
    
    # Recent matches detail
    recent_matches: List[RecentMatch] = field(default_factory=list)
    
    # Confidence
    is_overperforming_xG: bool = False
    is_underperforming_xG: bool = False
    regression_risk: float = 0.0  # How likely to regress


# ============================================================
# HEAD TO HEAD INTELLIGENCE
# ============================================================

@dataclass 
class H2HMatch:
    """Single H2H match with full context."""
    fixture_id: int
    date: date
    venue: str
    
    # Teams (home perspective)
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    
    # Result
    home_goals: int
    away_goals: int
    
    # Performance
    home_xG: Optional[float] = None
    away_xG: Optional[float] = None
    
    # Control
    home_possession: Optional[float] = None
    home_shots: Optional[int] = None
    away_shots: Optional[int] = None
    
    # Key events
    first_goal_team: Optional[str] = None
    first_goal_minute: Optional[int] = None
    red_cards: int = 0
    
    # Narrative
    match_story: Optional[str] = None


@dataclass
class H2HIntelligence:
    """
    Head-to-head analysis between two teams.
    
    Built from: Historical FotMob post-match data for these teams
    """
    team_a_id: int
    team_a_name: str
    team_b_id: int
    team_b_name: str
    
    # Overall record
    total_matches: int = 0
    team_a_wins: int = 0
    draws: int = 0
    team_b_wins: int = 0
    
    # Goals
    team_a_goals_total: int = 0
    team_b_goals_total: int = 0
    avg_total_goals: float = 0.0
    
    # xG (if available historically)
    team_a_xG_total: float = 0.0
    team_b_xG_total: float = 0.0
    
    # Venue impact
    team_a_home_wins: int = 0
    team_a_away_wins: int = 0
    
    # Recent trend (last 5 H2H)
    recent_trend: str = ""       # "team_a_dominant", "team_b_dominant", "balanced"
    last_5_team_a_wins: int = 0
    last_5_draws: int = 0
    
    # Patterns
    btts_rate: float = 0.0       # Both teams scored %
    over_25_rate: float = 0.0    # Over 2.5 goals %
    first_goal_team_a_rate: float = 0.0
    
    # High-scoring fixture?
    is_typically_high_scoring: bool = False
    is_typically_tight: bool = False
    
    # Individual matches
    matches: List[H2HMatch] = field(default_factory=list)
    
    # Last meeting
    last_match: Optional[H2HMatch] = None


# ============================================================
# PLAYER MATCHUPS
# ============================================================

@dataclass
class PlayerMatchup:
    """
    Key player vs player/system matchup.
    
    Built from: Historical performance data
    """
    player_a: PlayerHistoricalProfile
    player_b: Optional[PlayerHistoricalProfile]  # Can be vs formation/style
    
    matchup_type: str  # "player_vs_player", "player_vs_system"
    description: str   # "Salah vs Robertson left side"
    
    # Historical data (if they've faced before)
    times_faced: int = 0
    player_a_goals_in_matchup: int = 0
    player_a_avg_rating_in_matchup: Optional[float] = None
    
    # Advantage
    advantage: str = ""  # "player_a", "player_b", "even"
    advantage_reason: str = ""
    
    # Key factor
    is_key_battle: bool = False
    impact_prediction: str = ""  # "High impact on result"


# ============================================================
# MATCHUP INTELLIGENCE (the main pre-match context)
# ============================================================

@dataclass
class MatchupIntelligence:
    """
    Complete matchup intelligence for an upcoming fixture.
    
    This is the TRUE pre-match context - built entirely from
    historical post-match data (primarily FotMob).
    
    Data Sources:
    - Team profiles: FotMob last 10-15 matches per team
    - Form: FotMob last 5-10 matches per team
    - H2H: FotMob historical matches between teams
    - Player profiles: FotMob player stats aggregated
    - Tactical patterns: FotMob shotmaps, momentum, stats
    
    Supplemented by:
    - API-Football: Standings, odds, predictions (validation)
    - API-Football: Injuries (cross-reference)
    """
    
    # Fixture identification
    fixture_id: int
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    match_date: date
    
    # TEAM PROFILES (from historical post-match data)
    home_profile: Optional[TeamTacticalProfile] = None
    away_profile: Optional[TeamTacticalProfile] = None
    
    # CURRENT FORM (recent trajectory)
    home_form: Optional[TeamForm] = None
    away_form: Optional[TeamForm] = None
    
    # HEAD TO HEAD (historical meetings)
    h2h: Optional[H2HIntelligence] = None
    
    # KEY PLAYERS (who decides this?)
    home_key_players: List[PlayerHistoricalProfile] = field(default_factory=list)
    away_key_players: List[PlayerHistoricalProfile] = field(default_factory=list)
    
    # PLAYER MATCHUPS (tactical battles)
    key_matchups: List[PlayerMatchup] = field(default_factory=list)
    
    # AVAILABILITY (injuries/suspensions)
    home_missing_players: List[PlayerHistoricalProfile] = field(default_factory=list)
    away_missing_players: List[PlayerHistoricalProfile] = field(default_factory=list)
    home_availability_impact: float = 0.0  # 0-1, impact of absences
    away_availability_impact: float = 0.0
    
    # TACTICAL MATCHUP ANALYSIS
    style_matchup: str = ""      # "possession vs counter"
    tactical_advantage: str = ""  # "home", "away", "even"
    tactical_advantage_reason: str = ""
    
    # DERIVED PREDICTIONS (from data, not market)
    predicted_possession_home: float = 0.5
    predicted_xG_home: float = 0.0
    predicted_xG_away: float = 0.0
    predicted_total_goals: float = 0.0
    
    # PATTERNS
    btts_likelihood: float = 0.0
    over_25_likelihood: float = 0.0
    home_clean_sheet_likelihood: float = 0.0
    away_clean_sheet_likelihood: float = 0.0
    
    # NARRATIVES (generated from patterns)
    key_narratives: List[str] = field(default_factory=list)
    
    # MARKET CONTEXT (from API-Football - validation layer)
    market_home_win_prob: Optional[float] = None
    market_draw_prob: Optional[float] = None
    market_away_win_prob: Optional[float] = None
    api_prediction_advice: Optional[str] = None
    
    # VALUE DETECTION (model vs market)
    model_vs_market_divergence: Dict[str, float] = field(default_factory=dict)
    potential_value: List[str] = field(default_factory=list)
    
    # CONFIDENCE
    data_completeness: float = 0.0  # 0-100
    prediction_confidence: float = 0.0
    
    # META
    built_at: datetime = field(default_factory=datetime.now)
    home_matches_analyzed: int = 0
    away_matches_analyzed: int = 0
    h2h_matches_analyzed: int = 0
    
    version: str = "1.0.0"


# ============================================================
# BUILDER INTERFACE
# ============================================================

@dataclass
class MatchupIntelligenceBuilder:
    """
    Builder for creating MatchupIntelligence from historical data.
    
    Usage:
        builder = MatchupIntelligenceBuilder(fixture_id, home_id, away_id, date)
        
        # Add FotMob historical data
        builder.add_home_matches(fotmob_matches)  # List[FotMobMatchDetail]
        builder.add_away_matches(fotmob_matches)
        builder.add_h2h_matches(fotmob_matches)
        
        # Add API-Football market context
        builder.add_market_context(odds, predictions)
        
        # Build
        intelligence = builder.build()
    """
    fixture_id: int
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    match_date: date
    
    # Collected data
    home_historical_matches: List[Any] = field(default_factory=list)
    away_historical_matches: List[Any] = field(default_factory=list)
    h2h_historical_matches: List[Any] = field(default_factory=list)
    
    # Market context
    odds_data: Optional[Any] = None
    predictions_data: Optional[Any] = None
    standings_data: Optional[Any] = None
    injuries_data: Optional[Any] = None
    
    def add_home_matches(self, matches: List[Any]) -> 'MatchupIntelligenceBuilder':
        """Add historical matches for home team."""
        self.home_historical_matches = matches
        return self
    
    def add_away_matches(self, matches: List[Any]) -> 'MatchupIntelligenceBuilder':
        """Add historical matches for away team."""
        self.away_historical_matches = matches
        return self
    
    def add_h2h_matches(self, matches: List[Any]) -> 'MatchupIntelligenceBuilder':
        """Add historical H2H matches."""
        self.h2h_historical_matches = matches
        return self
    
    def add_market_context(
        self,
        odds: Optional[Any] = None,
        predictions: Optional[Any] = None,
        standings: Optional[Any] = None,
        injuries: Optional[Any] = None
    ) -> 'MatchupIntelligenceBuilder':
        """Add API-Football market context."""
        self.odds_data = odds
        self.predictions_data = predictions
        self.standings_data = standings
        self.injuries_data = injuries
        return self
    
    def build(self) -> MatchupIntelligence:
        """
        Build the complete MatchupIntelligence.
        
        TODO: Implement aggregation logic
        """
        # This is where the magic happens:
        # 1. Aggregate home matches → home_profile, home_form
        # 2. Aggregate away matches → away_profile, away_form
        # 3. Analyze H2H matches → h2h intelligence
        # 4. Extract key players from profiles
        # 5. Identify key matchups
        # 6. Calculate predictions from data
        # 7. Compare with market (if available)
        # 8. Generate narratives
        
        intelligence = MatchupIntelligence(
            fixture_id=self.fixture_id,
            home_team_id=self.home_team_id,
            home_team_name=self.home_team_name,
            away_team_id=self.away_team_id,
            away_team_name=self.away_team_name,
            match_date=self.match_date,
            home_matches_analyzed=len(self.home_historical_matches),
            away_matches_analyzed=len(self.away_historical_matches),
            h2h_matches_analyzed=len(self.h2h_historical_matches),
        )
        
        # TODO: Implement aggregation
        
        return intelligence
