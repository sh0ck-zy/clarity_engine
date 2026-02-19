"""
Match Context Schema - Phase 1 (P1-001)

Defines the strict schema for match context that grounds all narratives.
All fields are deterministic facts - no predictions, no opinions.

Usage:
    from src.analysis.context_schema import MatchContext, validate_context

    context = build_context(fixture_id)
    is_valid, errors = validate_context(context)
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import date, datetime
import json


# ============================================================
# SCHEMA DEFINITIONS
# ============================================================

@dataclass
class TeamIdentity:
    """Season-long team characteristics (stable identity)."""
    name: str
    elo: int  # Current ClubElo rating
    season_xg_per_match: float  # Avg xG
    season_xga_per_match: float  # Avg xGA
    season_xg_diff: float  # xG - xGA per match
    season_ppda: float  # Pressing intensity (lower = more aggressive)
    season_field_tilt: float  # Possession weighted by zone (50 = neutral)


@dataclass
class TeamForm:
    """Recent form (last 5 matches) - must use only pre-match data."""
    results: str  # e.g., "W-W-D-L-W" (most recent first)
    points: int  # Points from last 5 (0-15)
    goals_for: int  # Total goals scored
    goals_against: int  # Total goals conceded
    xg_total: float  # Sum of xG in last 5
    xga_total: float  # Sum of xGA in last 5
    xg_diff: float  # xG - xGA in last 5
    clean_sheets: int  # Number of clean sheets
    failed_to_score: int  # Matches without scoring
    opponent_avg_elo: int  # Average Elo of opponents faced
    days_rest: int  # Days since last match


@dataclass
class PlayerAbsence:
    """Key player absence (injury/suspension)."""
    player_name: str
    position: str  # FW, MF, DF, GK
    reason: str  # "injury" or "suspension"
    injury_type: Optional[str] = None  # "hamstring", "knee", etc.
    impact_rating: Optional[float] = None  # 0-1 importance to team
    xg_per90: Optional[float] = None  # Offensive contribution
    xa_per90: Optional[float] = None  # Creative contribution


@dataclass
class TeamAbsences:
    """All key absences for a team."""
    total_missing: int
    key_attackers_missing: int
    key_defenders_missing: int
    total_offensive_impact: float  # Sum of xG+xA per90 lost
    total_defensive_impact: float  # Sum of tackles+interceptions per90 lost
    players: List[PlayerAbsence] = field(default_factory=list)


@dataclass
class PlayerLineupInfo:
    """Player in a lineup."""
    player_id: str
    player_name: str
    position: str
    shirt_number: Optional[int] = None


@dataclass
class TeamLineup:
    """Expected/confirmed lineup for a team."""
    formation: Optional[str] = None  # e.g., "4-3-3", "4-2-3-1"
    starters: List[PlayerLineupInfo] = field(default_factory=list)
    bench: List[PlayerLineupInfo] = field(default_factory=list)
    source: str = "unknown"  # "transfermarkt", "official", etc.
    is_confirmed: bool = False  # True if post-match confirmed lineup


@dataclass
class HeadToHead:
    """Historical head-to-head record (last 5 meetings)."""
    home_wins: int
    draws: int
    away_wins: int
    avg_total_goals: float
    home_avg_goals: float
    away_avg_goals: float
    matches_played: int


@dataclass
class MarketOdds:
    """Pre-match market odds (1X2)."""
    home_win: Optional[float] = None
    draw: Optional[float] = None
    away_win: Optional[float] = None
    source: str = "unknown"
    captured_at: Optional[datetime] = None


@dataclass
class ScheduleContext:
    """Scheduling and congestion factors."""
    home_rest_days: int
    away_rest_days: int
    home_matches_last_7d: int
    away_matches_last_7d: int
    home_matches_last_14d: int
    away_matches_last_14d: int
    is_home_congested: bool  # >2 matches in 7 days
    is_away_congested: bool


@dataclass
class LeaguePosition:
    """Current league standing before match."""
    home_position: int
    away_position: int
    home_points: int
    away_points: int
    home_goal_diff: int
    away_goal_diff: int


@dataclass
class TeamContext:
    """Complete context for one team."""
    identity: TeamIdentity
    form: TeamForm
    absences: TeamAbsences
    lineup: Optional[TeamLineup] = None  # May not be available pre-match
    is_home: bool = True


@dataclass
class MatchContext:
    """
    Complete match context - the single source of truth for narratives.

    This schema ensures:
    1. All data is pre-match only (time-travel safe)
    2. All fields are deterministic facts
    3. Missing data is explicitly flagged
    """
    # Match identification
    fixture_id: str
    match_date: date
    season: str
    league: str
    round_number: Optional[int]

    # Team contexts
    home: TeamContext
    away: TeamContext

    # Comparative metrics
    head_to_head: HeadToHead
    schedule: ScheduleContext
    league_position: LeaguePosition

    # Market
    odds: MarketOdds

    # Data quality flags
    coverage_score: float  # 0-100, % of fields populated
    missing_fields: List[str] = field(default_factory=list)
    data_warnings: List[str] = field(default_factory=list)

    # Metadata
    context_version: str = "1.0.0"
    built_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================
# REQUIRED FIELDS (Validation will fail if missing)
# ============================================================

REQUIRED_FIELDS = [
    "fixture_id",
    "match_date",
    "home.identity.name",
    "home.identity.elo",
    "home.form.results",
    "home.form.days_rest",
    "away.identity.name",
    "away.identity.elo",
    "away.form.results",
    "away.form.days_rest",
]

IMPORTANT_FIELDS = [
    "home.identity.season_xg_per_match",
    "home.identity.season_xga_per_match",
    "home.identity.season_ppda",
    "home.form.xg_diff",
    "home.form.opponent_avg_elo",
    "away.identity.season_xg_per_match",
    "away.identity.season_xga_per_match",
    "away.identity.season_ppda",
    "away.form.xg_diff",
    "away.form.opponent_avg_elo",
    "head_to_head.matches_played",
    "odds.home_win",
    "league_position.home_position",
    "league_position.away_position",
]


# ============================================================
# VALIDATION FUNCTIONS
# ============================================================

def _get_nested_value(obj: Any, path: str) -> Any:
    """Get nested attribute value using dot notation."""
    parts = path.split('.')
    current = obj
    for part in parts:
        if current is None:
            return None
        if hasattr(current, part):
            current = getattr(current, part)
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def validate_context(context: MatchContext) -> tuple[bool, List[str]]:
    """
    Validate match context against schema requirements.

    Args:
        context: MatchContext to validate

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []

    # Check required fields
    for field_path in REQUIRED_FIELDS:
        value = _get_nested_value(context, field_path)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"Required field missing: {field_path}")

    # Check Elo values are sensible
    if context.home.identity.elo < 1000 or context.home.identity.elo > 2200:
        errors.append(f"Home Elo out of range: {context.home.identity.elo}")
    if context.away.identity.elo < 1000 or context.away.identity.elo > 2200:
        errors.append(f"Away Elo out of range: {context.away.identity.elo}")

    # Check form results format (W-D-L pattern)
    for team, label in [(context.home, "home"), (context.away, "away")]:
        results = team.form.results
        if results:
            valid_chars = set('WDL-')
            if not all(c in valid_chars for c in results):
                errors.append(f"{label} form results invalid format: {results}")

    # Check rest days are positive
    if context.schedule.home_rest_days < 0:
        errors.append("Home rest days cannot be negative")
    if context.schedule.away_rest_days < 0:
        errors.append("Away rest days cannot be negative")

    # Check odds are valid decimals (if provided)
    if context.odds.home_win is not None:
        if context.odds.home_win < 1.01 or context.odds.home_win > 50:
            errors.append(f"Invalid home win odds: {context.odds.home_win}")

    return len(errors) == 0, errors


def calculate_coverage_score(context: MatchContext) -> float:
    """
    Calculate data coverage score (0-100).

    Weights:
    - Required fields: 60% (must all be present for >0 score)
    - Important fields: 30%
    - Nice-to-have fields: 10%
    """
    all_fields = REQUIRED_FIELDS + IMPORTANT_FIELDS

    populated = 0
    for field_path in all_fields:
        value = _get_nested_value(context, field_path)
        if value is not None and value != "" and value != 0:
            populated += 1

    # Base score from field coverage
    if all_fields:
        base_score = (populated / len(all_fields)) * 100
    else:
        base_score = 0

    # Bonus for having injury data
    if context.home.absences.total_missing > 0 or context.away.absences.total_missing > 0:
        base_score = min(100, base_score + 5)

    # Bonus for having odds
    if context.odds.home_win is not None:
        base_score = min(100, base_score + 5)

    return round(base_score, 1)


def context_to_dict(context: MatchContext) -> Dict:
    """Convert MatchContext to dictionary for JSON serialization."""
    return asdict(context)


def context_to_json(context: MatchContext, indent: int = 2) -> str:
    """Convert MatchContext to JSON string."""
    def default_serializer(obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    return json.dumps(context_to_dict(context), default=default_serializer, indent=indent)


# ============================================================
# FACTORY FUNCTIONS (for creating empty/default objects)
# ============================================================

def empty_team_identity(name: str = "Unknown") -> TeamIdentity:
    """Create empty TeamIdentity with defaults."""
    return TeamIdentity(
        name=name,
        elo=1500,
        season_xg_per_match=0.0,
        season_xga_per_match=0.0,
        season_xg_diff=0.0,
        season_ppda=10.0,
        season_field_tilt=50.0
    )


def empty_team_form() -> TeamForm:
    """Create empty TeamForm with defaults."""
    return TeamForm(
        results="",
        points=0,
        goals_for=0,
        goals_against=0,
        xg_total=0.0,
        xga_total=0.0,
        xg_diff=0.0,
        clean_sheets=0,
        failed_to_score=0,
        opponent_avg_elo=1500,
        days_rest=7
    )


def empty_team_absences() -> TeamAbsences:
    """Create empty TeamAbsences."""
    return TeamAbsences(
        total_missing=0,
        key_attackers_missing=0,
        key_defenders_missing=0,
        total_offensive_impact=0.0,
        total_defensive_impact=0.0,
        players=[]
    )


def empty_team_lineup() -> TeamLineup:
    """Create empty TeamLineup."""
    return TeamLineup(
        formation=None,
        starters=[],
        bench=[],
        source="unknown",
        is_confirmed=False
    )


def empty_head_to_head() -> HeadToHead:
    """Create empty HeadToHead with no history."""
    return HeadToHead(
        home_wins=0,
        draws=0,
        away_wins=0,
        avg_total_goals=0.0,
        home_avg_goals=0.0,
        away_avg_goals=0.0,
        matches_played=0
    )


def empty_schedule_context() -> ScheduleContext:
    """Create default ScheduleContext."""
    return ScheduleContext(
        home_rest_days=7,
        away_rest_days=7,
        home_matches_last_7d=1,
        away_matches_last_7d=1,
        home_matches_last_14d=2,
        away_matches_last_14d=2,
        is_home_congested=False,
        is_away_congested=False
    )


def empty_league_position() -> LeaguePosition:
    """Create default LeaguePosition."""
    return LeaguePosition(
        home_position=10,
        away_position=10,
        home_points=0,
        away_points=0,
        home_goal_diff=0,
        away_goal_diff=0
    )


def empty_market_odds() -> MarketOdds:
    """Create empty MarketOdds."""
    return MarketOdds(
        home_win=None,
        draw=None,
        away_win=None,
        source="unknown",
        captured_at=None
    )
