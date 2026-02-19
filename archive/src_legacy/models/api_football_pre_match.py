"""
API-Football Pre-Match Schema

Complete pre-match data structure from API-Football endpoints.
All fields are present (with Optional/None defaults) to identify data gaps.

Endpoints used:
- /fixtures - Basic match info, venue, teams
- /predictions - Winner predictions, percentages, H2H, team analysis, comparison
- /odds - Betting odds from bookmakers
- /injuries - Player injuries and suspensions
- /standings - League table position and form

Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from enum import Enum


# ============================================================
# ENUMS
# ============================================================

class FixtureStatus(Enum):
    """API-Football fixture status codes."""
    SCHEDULED = "TBD"       # Time To Be Defined
    TIMED = "NS"           # Not Started
    IN_PLAY_1H = "1H"      # First Half
    HALFTIME = "HT"        # Halftime
    IN_PLAY_2H = "2H"      # Second Half
    EXTRA_TIME = "ET"      # Extra Time
    PENALTIES = "P"        # Penalty In Progress
    FINISHED = "FT"        # Match Finished
    FINISHED_AET = "AET"   # Finished After Extra Time
    FINISHED_PEN = "PEN"   # Finished After Penalties
    BREAK_TIME = "BT"      # Break Time
    SUSPENDED = "SUSP"     # Match Suspended
    INTERRUPTED = "INT"    # Match Interrupted
    POSTPONED = "PST"      # Match Postponed
    CANCELLED = "CANC"     # Match Cancelled
    ABANDONED = "ABD"      # Match Abandoned
    TECHNICAL_LOSS = "AWD" # Technical Loss
    WALKOVER = "WO"        # WalkOver
    LIVE = "LIVE"          # In Progress


class InjuryType(Enum):
    """Types of player absences."""
    INJURY = "injury"
    SUSPENSION = "suspension"
    NATIONAL_TEAM = "national_team"
    PERSONAL = "personal"
    OTHER = "other"


# ============================================================
# FIXTURE INFO (from /fixtures endpoint)
# ============================================================

@dataclass
class APIFootballVenue:
    """Venue information."""
    id: Optional[int] = None
    name: Optional[str] = None
    city: Optional[str] = None
    capacity: Optional[int] = None
    surface: Optional[str] = None
    image: Optional[str] = None


@dataclass
class APIFootballTeamRef:
    """Team reference in fixture."""
    id: int
    name: str
    logo: Optional[str] = None
    winner: Optional[bool] = None


@dataclass
class APIFootballFixture:
    """
    Basic fixture information from /fixtures endpoint.
    
    Source: /fixtures?league={id}&season={year}
    """
    # Core identifiers
    fixture_id: int
    referee: Optional[str] = None
    timezone: Optional[str] = None
    date: Optional[datetime] = None
    timestamp: Optional[int] = None
    
    # Venue
    venue: Optional[APIFootballVenue] = None
    
    # Status
    status_long: Optional[str] = None
    status_short: Optional[str] = None
    status_elapsed: Optional[int] = None
    
    # League context
    league_id: Optional[int] = None
    league_name: Optional[str] = None
    league_country: Optional[str] = None
    league_logo: Optional[str] = None
    league_flag: Optional[str] = None
    league_season: Optional[int] = None
    league_round: Optional[str] = None
    
    # Teams
    home_team: Optional[APIFootballTeamRef] = None
    away_team: Optional[APIFootballTeamRef] = None
    
    # Periods (for live/finished matches)
    periods_first: Optional[int] = None
    periods_second: Optional[int] = None


# ============================================================
# STANDINGS (from /standings endpoint)
# ============================================================

@dataclass
class APIFootballStandingRecord:
    """Home/Away/All record breakdown."""
    played: Optional[int] = None
    win: Optional[int] = None
    draw: Optional[int] = None
    lose: Optional[int] = None
    goals_for: Optional[int] = None
    goals_against: Optional[int] = None


@dataclass
class APIFootballStanding:
    """
    Team standing in the league table.
    
    Source: /standings?league={id}&season={year}
    """
    team_id: int
    team_name: Optional[str] = None
    team_logo: Optional[str] = None
    
    # Position
    rank: Optional[int] = None
    points: Optional[int] = None
    goals_diff: Optional[int] = None
    group: Optional[str] = None
    form: Optional[str] = None           # "WWDLW" last 5
    status: Optional[str] = None         # same, up, down
    description: Optional[str] = None    # "Promotion", "Relegation", etc.
    
    # Records
    all: Optional[APIFootballStandingRecord] = None
    home: Optional[APIFootballStandingRecord] = None
    away: Optional[APIFootballStandingRecord] = None
    
    # Update info
    update: Optional[datetime] = None


# ============================================================
# PREDICTIONS (from /predictions endpoint)
# ============================================================

@dataclass
class APIFootballPredictionWinner:
    """Winner prediction with confidence."""
    winner_id: Optional[int] = None
    winner_name: Optional[str] = None
    comment: Optional[str] = None        # "Win or Draw", "Draw", etc.


@dataclass
class APIFootballPredictionPercent:
    """Percentage predictions."""
    home: Optional[str] = None           # "45%"
    draw: Optional[str] = None           # "25%"
    away: Optional[str] = None           # "30%"


@dataclass
class APIFootballPredictionGoals:
    """Goals prediction."""
    home: Optional[str] = None           # "-1.5" (expected goals)
    away: Optional[str] = None


@dataclass
class APIFootballTeamLast5:
    """
    Team analysis from last 5 matches.
    
    Source: /predictions endpoint teams.{home|away}.last_5
    """
    form: Optional[str] = None           # "WWDLW"
    att: Optional[str] = None            # Attack rating "Good", "Average", etc.
    def_: Optional[str] = None           # Defense rating (def is reserved)
    
    # Goals analysis
    goals_for_total: Optional[int] = None
    goals_for_average: Optional[str] = None
    goals_against_total: Optional[int] = None
    goals_against_average: Optional[str] = None


@dataclass
class APIFootballLeagueStats:
    """
    Team's league statistics.
    
    Source: /predictions endpoint teams.{home|away}.league
    """
    form: Optional[str] = None           # Season form
    
    # Fixtures
    fixtures_played_home: Optional[int] = None
    fixtures_played_away: Optional[int] = None
    fixtures_played_total: Optional[int] = None
    
    fixtures_wins_home: Optional[int] = None
    fixtures_wins_away: Optional[int] = None
    fixtures_wins_total: Optional[int] = None
    
    fixtures_draws_home: Optional[int] = None
    fixtures_draws_away: Optional[int] = None
    fixtures_draws_total: Optional[int] = None
    
    fixtures_loses_home: Optional[int] = None
    fixtures_loses_away: Optional[int] = None
    fixtures_loses_total: Optional[int] = None
    
    # Goals
    goals_for_home_total: Optional[int] = None
    goals_for_home_average: Optional[str] = None
    goals_for_away_total: Optional[int] = None
    goals_for_away_average: Optional[str] = None
    goals_for_total: Optional[int] = None
    goals_for_average: Optional[str] = None
    
    goals_against_home_total: Optional[int] = None
    goals_against_home_average: Optional[str] = None
    goals_against_away_total: Optional[int] = None
    goals_against_away_average: Optional[str] = None
    goals_against_total: Optional[int] = None
    goals_against_average: Optional[str] = None
    
    # Clean sheets and failed to score
    clean_sheet_home: Optional[int] = None
    clean_sheet_away: Optional[int] = None
    clean_sheet_total: Optional[int] = None
    
    failed_to_score_home: Optional[int] = None
    failed_to_score_away: Optional[int] = None
    failed_to_score_total: Optional[int] = None
    
    # Penalty stats
    penalty_scored: Optional[int] = None
    penalty_missed: Optional[int] = None
    penalty_total: Optional[int] = None


@dataclass
class APIFootballTeamPredictionAnalysis:
    """
    Full team analysis from predictions endpoint.
    
    Source: /predictions endpoint teams.{home|away}
    """
    team_id: int
    team_name: Optional[str] = None
    team_logo: Optional[str] = None
    
    last_5: Optional[APIFootballTeamLast5] = None
    league: Optional[APIFootballLeagueStats] = None


@dataclass
class APIFootballComparisonMetric:
    """Single comparison metric between teams."""
    home: Optional[str] = None           # Percentage "45%"
    away: Optional[str] = None


@dataclass
class APIFootballComparison:
    """
    Head-to-head comparison metrics.
    
    Source: /predictions endpoint comparison
    """
    form: Optional[APIFootballComparisonMetric] = None
    att: Optional[APIFootballComparisonMetric] = None
    def_: Optional[APIFootballComparisonMetric] = None
    poisson_distribution: Optional[APIFootballComparisonMetric] = None
    h2h: Optional[APIFootballComparisonMetric] = None
    goals: Optional[APIFootballComparisonMetric] = None
    total: Optional[APIFootballComparisonMetric] = None


@dataclass
class APIFootballH2HMatch:
    """
    Historical head-to-head match.
    
    Source: /predictions endpoint h2h[]
    """
    fixture_id: Optional[int] = None
    date: Optional[datetime] = None
    venue_name: Optional[str] = None
    venue_city: Optional[str] = None
    
    # Teams
    home_team_id: Optional[int] = None
    home_team_name: Optional[str] = None
    home_team_logo: Optional[str] = None
    away_team_id: Optional[int] = None
    away_team_name: Optional[str] = None
    away_team_logo: Optional[str] = None
    
    # Result
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    home_winner: Optional[bool] = None
    away_winner: Optional[bool] = None
    
    # League context
    league_id: Optional[int] = None
    league_name: Optional[str] = None
    league_season: Optional[int] = None


@dataclass
class APIFootballPrediction:
    """
    Complete prediction data.
    
    Source: /predictions?fixture={id}
    """
    fixture_id: int
    
    # Predictions
    winner: Optional[APIFootballPredictionWinner] = None
    win_or_draw: Optional[bool] = None
    under_over: Optional[str] = None     # "+2.5", "-3.5", etc.
    goals: Optional[APIFootballPredictionGoals] = None
    advice: Optional[str] = None         # "Double chance: Home or Draw"
    percent: Optional[APIFootballPredictionPercent] = None
    
    # Team analysis
    home_team_analysis: Optional[APIFootballTeamPredictionAnalysis] = None
    away_team_analysis: Optional[APIFootballTeamPredictionAnalysis] = None
    
    # Comparison
    comparison: Optional[APIFootballComparison] = None
    
    # H2H history
    h2h: List[APIFootballH2HMatch] = field(default_factory=list)


# ============================================================
# ODDS (from /odds endpoint)
# ============================================================

@dataclass
class APIFootballOddValue:
    """Single odd value."""
    value: Optional[str] = None          # "Home", "Draw", "Away", "Over 2.5", etc.
    odd: Optional[str] = None            # "1.85"


@dataclass
class APIFootballBet:
    """Single bet market."""
    bet_id: Optional[int] = None
    bet_name: Optional[str] = None       # "Match Winner", "Goals Over/Under", etc.
    values: List[APIFootballOddValue] = field(default_factory=list)


@dataclass
class APIFootballBookmaker:
    """Bookmaker with its odds."""
    bookmaker_id: Optional[int] = None
    bookmaker_name: Optional[str] = None
    bets: List[APIFootballBet] = field(default_factory=list)


@dataclass
class APIFootballOdds:
    """
    Complete odds data for a fixture.
    
    Source: /odds?fixture={id}
    """
    fixture_id: int
    update_time: Optional[datetime] = None
    
    # All bookmakers
    bookmakers: List[APIFootballBookmaker] = field(default_factory=list)
    
    # Extracted 1X2 odds (convenience)
    home_win: Optional[float] = None
    draw: Optional[float] = None
    away_win: Optional[float] = None
    
    # Extracted goals markets (convenience)
    over_25: Optional[float] = None
    under_25: Optional[float] = None
    btts_yes: Optional[float] = None
    btts_no: Optional[float] = None
    
    # Derived probabilities
    implied_prob_home: Optional[float] = None
    implied_prob_draw: Optional[float] = None
    implied_prob_away: Optional[float] = None
    market_vig: Optional[float] = None


# ============================================================
# INJURIES (from /injuries endpoint)
# ============================================================

@dataclass
class APIFootballInjury:
    """
    Player injury/suspension.
    
    Source: /injuries?fixture={id} or /injuries?league={id}&season={year}
    """
    # Player info
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    player_photo: Optional[str] = None
    
    # Team info
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    team_logo: Optional[str] = None
    
    # Fixture context
    fixture_id: Optional[int] = None
    fixture_date: Optional[datetime] = None
    
    # Injury details
    injury_type: Optional[str] = None    # "Missing Fixture", "Questionable", etc.
    reason: Optional[str] = None         # "Knee Injury", "Suspended", etc.
    
    # League context
    league_id: Optional[int] = None
    league_name: Optional[str] = None
    league_season: Optional[int] = None


@dataclass
class APIFootballTeamInjuries:
    """All injuries for a team before a match."""
    team_id: int
    team_name: Optional[str] = None
    
    injuries: List[APIFootballInjury] = field(default_factory=list)
    
    # Aggregated
    total_missing: Optional[int] = None
    key_players_missing: Optional[int] = None


# ============================================================
# TEAM STATISTICS (from /teams/statistics endpoint)
# ============================================================

@dataclass
class APIFootballTeamStatistics:
    """
    Team season statistics.
    
    Source: /teams/statistics?team={id}&season={year}&league={id}
    """
    team_id: int
    team_name: Optional[str] = None
    team_logo: Optional[str] = None
    
    league_id: Optional[int] = None
    league_name: Optional[str] = None
    season: Optional[int] = None
    
    # Form
    form: Optional[str] = None           # Full season form string
    
    # Fixtures
    fixtures_played_home: Optional[int] = None
    fixtures_played_away: Optional[int] = None
    fixtures_played_total: Optional[int] = None
    
    fixtures_wins_home: Optional[int] = None
    fixtures_wins_away: Optional[int] = None
    fixtures_wins_total: Optional[int] = None
    
    fixtures_draws_home: Optional[int] = None
    fixtures_draws_away: Optional[int] = None
    fixtures_draws_total: Optional[int] = None
    
    fixtures_loses_home: Optional[int] = None
    fixtures_loses_away: Optional[int] = None
    fixtures_loses_total: Optional[int] = None
    
    # Goals
    goals_for_home_total: Optional[int] = None
    goals_for_home_average: Optional[str] = None
    goals_for_away_total: Optional[int] = None
    goals_for_away_average: Optional[str] = None
    goals_for_total: Optional[int] = None
    goals_for_average: Optional[str] = None
    
    goals_against_home_total: Optional[int] = None
    goals_against_home_average: Optional[str] = None
    goals_against_away_total: Optional[int] = None
    goals_against_away_average: Optional[str] = None
    goals_against_total: Optional[int] = None
    goals_against_average: Optional[str] = None
    
    # Goals by minute (breakdown)
    goals_for_0_15: Optional[int] = None
    goals_for_16_30: Optional[int] = None
    goals_for_31_45: Optional[int] = None
    goals_for_46_60: Optional[int] = None
    goals_for_61_75: Optional[int] = None
    goals_for_76_90: Optional[int] = None
    goals_for_91_105: Optional[int] = None
    goals_for_106_120: Optional[int] = None
    
    goals_against_0_15: Optional[int] = None
    goals_against_16_30: Optional[int] = None
    goals_against_31_45: Optional[int] = None
    goals_against_46_60: Optional[int] = None
    goals_against_61_75: Optional[int] = None
    goals_against_76_90: Optional[int] = None
    goals_against_91_105: Optional[int] = None
    goals_against_106_120: Optional[int] = None
    
    # Clean sheets
    clean_sheet_home: Optional[int] = None
    clean_sheet_away: Optional[int] = None
    clean_sheet_total: Optional[int] = None
    
    # Failed to score
    failed_to_score_home: Optional[int] = None
    failed_to_score_away: Optional[int] = None
    failed_to_score_total: Optional[int] = None
    
    # Penalty
    penalty_scored_total: Optional[int] = None
    penalty_scored_percentage: Optional[str] = None
    penalty_missed_total: Optional[int] = None
    penalty_missed_percentage: Optional[str] = None
    
    # Biggest streaks
    biggest_streak_wins: Optional[int] = None
    biggest_streak_draws: Optional[int] = None
    biggest_streak_loses: Optional[int] = None
    
    # Biggest wins/losses
    biggest_win_home: Optional[str] = None    # "5-0"
    biggest_win_away: Optional[str] = None
    biggest_loss_home: Optional[str] = None
    biggest_loss_away: Optional[str] = None
    
    # Cards
    yellow_cards_0_15: Optional[int] = None
    yellow_cards_16_30: Optional[int] = None
    yellow_cards_31_45: Optional[int] = None
    yellow_cards_46_60: Optional[int] = None
    yellow_cards_61_75: Optional[int] = None
    yellow_cards_76_90: Optional[int] = None
    yellow_cards_91_105: Optional[int] = None
    yellow_cards_106_120: Optional[int] = None
    yellow_cards_total: Optional[int] = None
    
    red_cards_0_15: Optional[int] = None
    red_cards_16_30: Optional[int] = None
    red_cards_31_45: Optional[int] = None
    red_cards_46_60: Optional[int] = None
    red_cards_61_75: Optional[int] = None
    red_cards_76_90: Optional[int] = None
    red_cards_91_105: Optional[int] = None
    red_cards_106_120: Optional[int] = None
    red_cards_total: Optional[int] = None
    
    # Lineups
    lineups_formation: Optional[str] = None  # Most used formation
    lineups_played: Optional[int] = None


# ============================================================
# COMPLETE PRE-MATCH CONTEXT
# ============================================================

@dataclass
class APIFootballPreMatchContext:
    """
    Complete pre-match context from API-Football.
    
    This schema contains ALL possible fields from the relevant endpoints.
    Fields may be None if data is not available, allowing gap analysis.
    
    Sources:
    - /fixtures - Basic match info
    - /predictions - Predictions, H2H, team analysis, comparison
    - /odds - Betting odds
    - /injuries - Player availability
    - /standings - League position
    - /teams/statistics - Team season stats
    """
    
    # Core fixture info
    fixture: APIFootballFixture
    
    # Standings (point-in-time)
    home_standing: Optional[APIFootballStanding] = None
    away_standing: Optional[APIFootballStanding] = None
    
    # Team season statistics
    home_team_stats: Optional[APIFootballTeamStatistics] = None
    away_team_stats: Optional[APIFootballTeamStatistics] = None
    
    # Predictions (includes H2H, comparison, team analysis)
    prediction: Optional[APIFootballPrediction] = None
    
    # Odds
    odds: Optional[APIFootballOdds] = None
    
    # Injuries
    home_injuries: Optional[APIFootballTeamInjuries] = None
    away_injuries: Optional[APIFootballTeamInjuries] = None
    
    # Meta
    fetched_at: datetime = field(default_factory=datetime.now)
    api_calls_made: int = 0
    coverage_score: float = 0.0          # 0-100 completeness
    missing_fields: List[str] = field(default_factory=list)
    
    # Raw responses (for debugging/reprocessing)
    raw_fixture: Optional[Dict[str, Any]] = None
    raw_prediction: Optional[Dict[str, Any]] = None
    raw_odds: Optional[Dict[str, Any]] = None
    raw_standings: Optional[Dict[str, Any]] = None
    
    version: str = "1.0.0"
    
    def calculate_coverage(self) -> float:
        """Calculate data coverage score based on available fields."""
        required_fields = [
            self.fixture is not None,
            self.home_standing is not None,
            self.away_standing is not None,
            self.prediction is not None,
            self.odds is not None,
        ]
        
        nice_to_have = [
            self.home_team_stats is not None,
            self.away_team_stats is not None,
            self.home_injuries is not None,
            self.away_injuries is not None,
            self.prediction and len(self.prediction.h2h) > 0,
            self.prediction and self.prediction.comparison is not None,
        ]
        
        required_score = sum(required_fields) / len(required_fields) * 70
        optional_score = sum(nice_to_have) / len(nice_to_have) * 30
        
        self.coverage_score = required_score + optional_score
        return self.coverage_score
