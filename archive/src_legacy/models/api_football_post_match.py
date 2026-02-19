"""
API-Football Post-Match Schema

Complete post-match data structure from API-Football endpoints.
All fields are present (with Optional/None defaults) to identify data gaps.

Endpoints used:
- /fixtures?id={id} - Match result, scores
- /fixtures/statistics - Team match statistics (xG, shots, possession)
- /fixtures/lineups - Formations, starting XI, substitutes
- /fixtures/events - Goals, cards, substitutions
- /fixtures/players - Player-level statistics

Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum


# ============================================================
# ENUMS
# ============================================================

class EventType(Enum):
    """Match event types."""
    GOAL = "Goal"
    CARD = "Card"
    SUBST = "subst"
    VAR = "Var"
    PENALTY_MISSED = "Penalty Missed"


class CardType(Enum):
    """Card types."""
    YELLOW = "Yellow Card"
    RED = "Red Card"
    YELLOW_RED = "Yellow Red"


class GoalType(Enum):
    """Goal types."""
    NORMAL = "Normal Goal"
    PENALTY = "Penalty"
    OWN_GOAL = "Own Goal"
    MISSED_PENALTY = "Missed Penalty"


# ============================================================
# FIXTURE RESULT (from /fixtures?id={id})
# ============================================================

@dataclass
class APIFootballScore:
    """Score at different points."""
    home: Optional[int] = None
    away: Optional[int] = None


@dataclass
class APIFootballFixtureResult:
    """
    Fixture result information.
    
    Source: /fixtures?id={id}
    """
    fixture_id: int
    
    # Status
    status_long: Optional[str] = None
    status_short: Optional[str] = None
    status_elapsed: Optional[int] = None
    
    # Scores
    goals_home: Optional[int] = None
    goals_away: Optional[int] = None
    
    halftime: Optional[APIFootballScore] = None
    fulltime: Optional[APIFootballScore] = None
    extratime: Optional[APIFootballScore] = None
    penalty: Optional[APIFootballScore] = None
    
    # Match info
    referee: Optional[str] = None
    date: Optional[datetime] = None
    venue_name: Optional[str] = None
    venue_city: Optional[str] = None
    
    # League context
    league_id: Optional[int] = None
    league_name: Optional[str] = None
    league_round: Optional[str] = None
    
    # Teams
    home_team_id: Optional[int] = None
    home_team_name: Optional[str] = None
    home_team_logo: Optional[str] = None
    home_team_winner: Optional[bool] = None
    
    away_team_id: Optional[int] = None
    away_team_name: Optional[str] = None
    away_team_logo: Optional[str] = None
    away_team_winner: Optional[bool] = None


# ============================================================
# MATCH EVENTS (from /fixtures/events)
# ============================================================

@dataclass
class APIFootballEvent:
    """
    Single match event (goal, card, substitution).
    
    Source: /fixtures/events?fixture={id}
    """
    # Time
    time_elapsed: Optional[int] = None
    time_extra: Optional[int] = None     # Added time
    
    # Team
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    team_logo: Optional[str] = None
    
    # Player
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    
    # Assist/Secondary player
    assist_id: Optional[int] = None
    assist_name: Optional[str] = None
    
    # Event type
    event_type: Optional[str] = None     # "Goal", "Card", "subst", "Var"
    detail: Optional[str] = None         # "Normal Goal", "Yellow Card", etc.
    comments: Optional[str] = None       # Additional context


@dataclass
class APIFootballGoal:
    """Structured goal event."""
    minute: int
    added_time: Optional[int] = None
    
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    
    scorer_id: Optional[int] = None
    scorer_name: Optional[str] = None
    
    assist_id: Optional[int] = None
    assist_name: Optional[str] = None
    
    goal_type: Optional[str] = None      # "Normal Goal", "Penalty", "Own Goal"
    is_penalty: bool = False
    is_own_goal: bool = False
    
    # Score at time of goal
    score_home: Optional[int] = None
    score_away: Optional[int] = None


@dataclass
class APIFootballCard:
    """Structured card event."""
    minute: int
    added_time: Optional[int] = None
    
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    
    card_type: Optional[str] = None      # "Yellow Card", "Red Card"
    reason: Optional[str] = None


@dataclass
class APIFootballSubstitution:
    """Structured substitution event."""
    minute: int
    added_time: Optional[int] = None
    
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    
    player_out_id: Optional[int] = None
    player_out_name: Optional[str] = None
    
    player_in_id: Optional[int] = None
    player_in_name: Optional[str] = None


# ============================================================
# MATCH STATISTICS (from /fixtures/statistics)
# ============================================================

@dataclass
class APIFootballTeamMatchStats:
    """
    Team statistics for a single match.
    
    Source: /fixtures/statistics?fixture={id}
    """
    team_id: int
    team_name: Optional[str] = None
    team_logo: Optional[str] = None
    
    # Expected Goals (CRITICAL)
    expected_goals: Optional[float] = None       # xG
    
    # Shots
    shots_total: Optional[int] = None
    shots_on_target: Optional[int] = None
    shots_off_target: Optional[int] = None
    shots_blocked: Optional[int] = None
    shots_inside_box: Optional[int] = None
    shots_outside_box: Optional[int] = None
    
    # Possession
    possession: Optional[float] = None           # Percentage
    
    # Passing
    passes_total: Optional[int] = None
    passes_accurate: Optional[int] = None
    passes_accuracy: Optional[float] = None      # Percentage
    passes_key: Optional[int] = None
    
    # Attacking
    attacks_total: Optional[int] = None
    attacks_dangerous: Optional[int] = None
    
    # Discipline
    fouls: Optional[int] = None
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None
    
    # Set pieces
    corners: Optional[int] = None
    offsides: Optional[int] = None
    
    # Goalkeeper
    goalkeeper_saves: Optional[int] = None
    
    # Other
    clearances: Optional[int] = None
    tackles: Optional[int] = None
    interceptions: Optional[int] = None
    duels_total: Optional[int] = None
    duels_won: Optional[int] = None
    aerials_total: Optional[int] = None
    aerials_won: Optional[int] = None


@dataclass
class APIFootballMatchStatistics:
    """Combined match statistics."""
    fixture_id: int
    
    home_stats: Optional[APIFootballTeamMatchStats] = None
    away_stats: Optional[APIFootballTeamMatchStats] = None
    
    # Derived
    total_xg: Optional[float] = None
    xg_difference: Optional[float] = None        # home - away


# ============================================================
# LINEUPS (from /fixtures/lineups)
# ============================================================

@dataclass
class APIFootballLineupPlayer:
    """Player in lineup."""
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    player_number: Optional[int] = None
    player_pos: Optional[str] = None     # "G", "D", "M", "F"
    player_grid: Optional[str] = None    # Position on tactical grid "1:1"
    
    # Additional info (if available from players endpoint)
    rating: Optional[float] = None
    captain: bool = False


@dataclass
class APIFootballCoach:
    """Coach info."""
    coach_id: Optional[int] = None
    coach_name: Optional[str] = None
    coach_photo: Optional[str] = None


@dataclass
class APIFootballTeamLineup:
    """
    Team lineup information.
    
    Source: /fixtures/lineups?fixture={id}
    """
    team_id: int
    team_name: Optional[str] = None
    team_logo: Optional[str] = None
    
    # Formation
    formation: Optional[str] = None      # "4-3-3", "3-5-2", etc.
    
    # Starting XI
    starting_xi: List[APIFootballLineupPlayer] = field(default_factory=list)
    
    # Substitutes
    substitutes: List[APIFootballLineupPlayer] = field(default_factory=list)
    
    # Coach
    coach: Optional[APIFootballCoach] = None


# ============================================================
# PLAYER STATISTICS (from /fixtures/players)
# ============================================================

@dataclass
class APIFootballPlayerMatchStats:
    """
    Player statistics for a single match.
    
    Source: /fixtures/players?fixture={id}
    """
    # Player info
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    player_photo: Optional[str] = None
    
    # Team
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    
    # Position and time
    position: Optional[str] = None       # "G", "D", "M", "F"
    minutes_played: Optional[int] = None
    rating: Optional[float] = None       # 0-10 rating
    captain: bool = False
    substitute: bool = False
    
    # Offensive
    goals_scored: Optional[int] = None
    goals_conceded: Optional[int] = None  # For goalkeepers
    assists: Optional[int] = None
    
    # Shots
    shots_total: Optional[int] = None
    shots_on_target: Optional[int] = None
    
    # Passing
    passes_total: Optional[int] = None
    passes_key: Optional[int] = None
    passes_accuracy: Optional[float] = None
    
    # Dribbles
    dribbles_attempts: Optional[int] = None
    dribbles_success: Optional[int] = None
    dribbles_past: Optional[int] = None  # Times dribbled past (defender)
    
    # Tackles
    tackles_total: Optional[int] = None
    tackles_blocks: Optional[int] = None
    tackles_interceptions: Optional[int] = None
    
    # Duels
    duels_total: Optional[int] = None
    duels_won: Optional[int] = None
    
    # Discipline
    fouls_drawn: Optional[int] = None
    fouls_committed: Optional[int] = None
    yellow_cards: Optional[int] = None
    red_cards: Optional[int] = None
    
    # Goalkeeper specific
    saves: Optional[int] = None
    penalty_saved: Optional[int] = None
    penalty_missed: Optional[int] = None
    penalty_scored: Optional[int] = None
    penalty_won: Optional[int] = None
    penalty_committed: Optional[int] = None
    
    # Other
    offsides: Optional[int] = None


@dataclass
class APIFootballTeamPlayerStats:
    """All player stats for a team."""
    team_id: int
    team_name: Optional[str] = None
    
    players: List[APIFootballPlayerMatchStats] = field(default_factory=list)
    
    # Derived
    average_rating: Optional[float] = None
    player_of_the_match: Optional[APIFootballPlayerMatchStats] = None


# ============================================================
# COMPLETE POST-MATCH CONTEXT
# ============================================================

@dataclass
class APIFootballPostMatchContext:
    """
    Complete post-match data from API-Football.
    
    This schema contains ALL possible fields from the relevant endpoints.
    Fields may be None if data is not available, allowing gap analysis.
    
    Sources:
    - /fixtures?id={id} - Match result
    - /fixtures/statistics - Team statistics (xG, shots, etc.)
    - /fixtures/lineups - Formations, players
    - /fixtures/events - Goals, cards, substitutions
    - /fixtures/players - Player-level statistics
    """
    
    # Match result
    fixture_result: APIFootballFixtureResult
    
    # Statistics
    statistics: Optional[APIFootballMatchStatistics] = None
    
    # Lineups
    home_lineup: Optional[APIFootballTeamLineup] = None
    away_lineup: Optional[APIFootballTeamLineup] = None
    
    # Events (raw)
    events: List[APIFootballEvent] = field(default_factory=list)
    
    # Structured events
    goals: List[APIFootballGoal] = field(default_factory=list)
    cards: List[APIFootballCard] = field(default_factory=list)
    substitutions: List[APIFootballSubstitution] = field(default_factory=list)
    
    # Player statistics
    home_players: Optional[APIFootballTeamPlayerStats] = None
    away_players: Optional[APIFootballTeamPlayerStats] = None
    
    # Meta
    fetched_at: datetime = field(default_factory=datetime.now)
    api_calls_made: int = 0
    coverage_score: float = 0.0
    missing_fields: List[str] = field(default_factory=list)
    
    # Raw responses
    raw_fixture: Optional[Dict[str, Any]] = None
    raw_statistics: Optional[Dict[str, Any]] = None
    raw_lineups: Optional[Dict[str, Any]] = None
    raw_events: Optional[Dict[str, Any]] = None
    raw_players: Optional[Dict[str, Any]] = None
    
    version: str = "1.0.0"
    
    def calculate_coverage(self) -> float:
        """Calculate data coverage score based on available fields."""
        required_fields = [
            self.fixture_result is not None,
            self.statistics is not None,
            self.home_lineup is not None,
            self.away_lineup is not None,
            len(self.events) > 0 or len(self.goals) > 0,
        ]
        
        nice_to_have = [
            self.home_players is not None,
            self.away_players is not None,
            self.statistics and self.statistics.home_stats and self.statistics.home_stats.expected_goals is not None,
            self.statistics and self.statistics.away_stats and self.statistics.away_stats.expected_goals is not None,
            len(self.substitutions) > 0,
        ]
        
        required_score = sum(required_fields) / len(required_fields) * 70
        optional_score = sum(nice_to_have) / len(nice_to_have) * 30
        
        self.coverage_score = required_score + optional_score
        return self.coverage_score
    
    def get_winner(self) -> str:
        """Get match winner."""
        if self.fixture_result.goals_home is None or self.fixture_result.goals_away is None:
            return "unknown"
        
        if self.fixture_result.goals_home > self.fixture_result.goals_away:
            return "home"
        elif self.fixture_result.goals_away > self.fixture_result.goals_home:
            return "away"
        else:
            return "draw"
    
    def get_total_goals(self) -> int:
        """Get total goals in match."""
        home = self.fixture_result.goals_home or 0
        away = self.fixture_result.goals_away or 0
        return home + away


# ============================================================
# COMPARISON SCHEMA (for FotMob vs API-Football)
# ============================================================

@dataclass
class DataSourceComparison:
    """
    Schema for comparing data between sources.
    
    Use this to identify:
    - Overlapping data (both have it)
    - Gaps (one has it, other doesn't)
    - Depth differences (quality/detail level)
    """
    fixture_id: int
    
    # Coverage scores
    api_football_coverage: float = 0.0
    fotmob_coverage: float = 0.0
    
    # Pre-match gaps
    pre_match_only_api_football: List[str] = field(default_factory=list)
    pre_match_only_fotmob: List[str] = field(default_factory=list)
    pre_match_overlap: List[str] = field(default_factory=list)
    
    # Post-match gaps
    post_match_only_api_football: List[str] = field(default_factory=list)
    post_match_only_fotmob: List[str] = field(default_factory=list)
    post_match_overlap: List[str] = field(default_factory=list)
    
    # Depth analysis
    depth_differences: Dict[str, str] = field(default_factory=dict)
    
    # Unique features
    api_football_unique: List[str] = field(default_factory=list)
    fotmob_unique: List[str] = field(default_factory=list)
    
    # Quality notes
    notes: List[str] = field(default_factory=list)
    
    analyzed_at: datetime = field(default_factory=datetime.now)


# ============================================================
# COMBINED MATCH RECORD
# ============================================================

@dataclass
class APIFootballMatchRecord:
    """
    Complete match record with pre and post match data.
    
    This is the full picture from API-Football.
    """
    fixture_id: int
    
    pre_match: Optional[APIFootballPreMatchContext] = None
    post_match: Optional[APIFootballPostMatchContext] = None
    
    # Validation
    pre_match_complete: bool = False
    post_match_complete: bool = False
    
    # Meta
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
