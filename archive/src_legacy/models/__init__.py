"""
Clarity Engine Models

Clean schemas for match data:
- pre_match: Everything we know BEFORE kickoff (generic)
- post_match: Everything that ACTUALLY happened (generic)
- api_football_*: Schemas derived entirely from API-Football
- fotmob: Schemas for FotMob data
- data_comparison: Tools to compare data sources

Version: 2.0.0 (added API-Football schemas for gap analysis)
"""

from .pre_match import (
    # Enums
    FormTrend,
    
    # Core objects
    Fixture,
    TeamSnapshot,
    TeamSeasonStats,
    PlayerAbsence,
    TeamAvailability,
    HeadToHead,
    MatchOdds,
    MatchNarratives,
    TacticalProfile,
    KeyPlayer,
    
    # Main context
    PreMatchContext,
)

from .post_match import (
    # Enums
    GoalType,
    CardType,
    
    # Core objects
    Goal,
    Card,
    Substitution,
    PlayerInLineup,
    TeamLineup,
    TeamMatchStats,
    MatchStatistics,
    KeyMoment,
    
    # Main reality
    PostMatchReality,
    MatchRecord,
)

# API-Football specific schemas (all fields, gap analysis ready)
from .api_football_pre_match import (
    # Enums
    FixtureStatus,
    InjuryType,
    
    # Fixture
    APIFootballVenue,
    APIFootballTeamRef,
    APIFootballFixture,
    
    # Standings
    APIFootballStandingRecord,
    APIFootballStanding,
    
    # Predictions
    APIFootballPredictionWinner,
    APIFootballPredictionPercent,
    APIFootballPredictionGoals,
    APIFootballTeamLast5,
    APIFootballLeagueStats,
    APIFootballTeamPredictionAnalysis,
    APIFootballComparisonMetric,
    APIFootballComparison,
    APIFootballH2HMatch,
    APIFootballPrediction,
    
    # Odds
    APIFootballOddValue,
    APIFootballBet,
    APIFootballBookmaker,
    APIFootballOdds,
    
    # Injuries
    APIFootballInjury,
    APIFootballTeamInjuries,
    
    # Team stats
    APIFootballTeamStatistics,
    
    # Full context
    APIFootballPreMatchContext,
)

from .api_football_post_match import (
    # Enums
    EventType,
    CardType as APIFootballCardType,
    GoalType as APIFootballGoalType,
    
    # Result
    APIFootballScore,
    APIFootballFixtureResult,
    
    # Events
    APIFootballEvent,
    APIFootballGoal,
    APIFootballCard,
    APIFootballSubstitution,
    
    # Statistics
    APIFootballTeamMatchStats,
    APIFootballMatchStatistics,
    
    # Lineups
    APIFootballLineupPlayer,
    APIFootballCoach,
    APIFootballTeamLineup,
    
    # Player stats
    APIFootballPlayerMatchStats,
    APIFootballTeamPlayerStats,
    
    # Full context
    APIFootballPostMatchContext,
    DataSourceComparison,
    APIFootballMatchRecord,
)

# FotMob schemas
from .fotmob import (
    FotMobLeagueMatch,
    FotMobLeagueRound,
    FotMobTeamRef,
    FotMobMatchEvent,
    FotMobStatValue,
    FotMobStatCategory,
    FotMobCoach,
    FotMobPlayer,
    FotMobTeamLineup,
    FotMobPlayerDetailedStats,
    FotMobShot,
    FotMobMomentum,
    FotMobMatchFacts,
    FotMobMatchDetail,
)

# Comparison utilities
from .data_comparison import (
    DataLayer,
    FOTMOB_COVERAGE,
    API_FOOTBALL_COVERAGE,
    LayerComparison,
    FullComparison,
    compare_sources,
    print_comparison_report,
    CustomMetricPotential,
    CUSTOM_METRICS,
    get_metrics_by_source,
    get_metrics_needing_both,
    IntelligenceLayer,
    INTELLIGENCE_ARCHITECTURE,
)

# Intelligence (takes + validation)
from .intelligence import (
    IntelligenceCategory,
    ValidationScore,
    Take,
    ResultTake,
    GoalsTake,
    DominanceTake,
    StyleMatchupTake,
    KeyPlayerTake,
    DangerZonesTake,
    MatchFlowTake,
    TacticalTake,
    MatchIntelligence,
    RoundIntelligence,
    SeasonIntelligenceTracker,
    create_match_intelligence,
)

# Temporal KG (per round, per team snapshots)
from .temporal_kg import (
    # Layer enum
    IntelligenceLayer as KGIntelligenceLayer,
    
    # The 8 layers
    IdentityLayer,
    PositionLayer,
    FormLayer,
    StyleLayer,
    PersonnelLayer,
    PlayerStatus,
    AttackLayer,
    DefenseLayer,
    MomentumLayer,
    
    # Snapshots
    TeamKGSnapshot,
    MatchupKGSnapshot,
    
    # Comparison
    LayerDiff,
    SnapshotDiff,
    TeamSeasonEvolution,
    
    # Questions
    LAYER_QUESTIONS,
    get_layer_questions,
    get_all_questions,
)

# Matchup Intelligence (pre-match from historical post-match)
from .matchup_intelligence import (
    # Enums
    PlayingStyle,
    FormTrend as MatchupFormTrend,
    StrengthLevel,
    
    # Player profile
    PlayerHistoricalProfile,
    
    # Team profiles
    FormationUsage,
    ShotProfile,
    DefensiveProfile,
    MomentumProfile,
    TeamTacticalProfile,
    
    # Form
    RecentMatch,
    TeamForm,
    
    # H2H
    H2HMatch,
    H2HIntelligence,
    
    # Matchups
    PlayerMatchup,
    
    # Main intelligence
    MatchupIntelligence,
    MatchupIntelligenceBuilder,
)

__all__ = [
    # Pre-match (generic)
    "FormTrend",
    "Fixture",
    "TeamSnapshot",
    "TeamSeasonStats",
    "PlayerAbsence",
    "TeamAvailability",
    "HeadToHead",
    "MatchOdds",
    "MatchNarratives",
    "TacticalProfile",
    "KeyPlayer",
    "PreMatchContext",
    
    # Post-match (generic)
    "GoalType",
    "CardType",
    "Goal",
    "Card",
    "Substitution",
    "PlayerInLineup",
    "TeamLineup",
    "TeamMatchStats",
    "MatchStatistics",
    "KeyMoment",
    "PostMatchReality",
    "MatchRecord",
    
    # API-Football Pre-match
    "FixtureStatus",
    "InjuryType",
    "APIFootballVenue",
    "APIFootballTeamRef",
    "APIFootballFixture",
    "APIFootballStandingRecord",
    "APIFootballStanding",
    "APIFootballPredictionWinner",
    "APIFootballPredictionPercent",
    "APIFootballPredictionGoals",
    "APIFootballTeamLast5",
    "APIFootballLeagueStats",
    "APIFootballTeamPredictionAnalysis",
    "APIFootballComparisonMetric",
    "APIFootballComparison",
    "APIFootballH2HMatch",
    "APIFootballPrediction",
    "APIFootballOddValue",
    "APIFootballBet",
    "APIFootballBookmaker",
    "APIFootballOdds",
    "APIFootballInjury",
    "APIFootballTeamInjuries",
    "APIFootballTeamStatistics",
    "APIFootballPreMatchContext",
    
    # API-Football Post-match
    "EventType",
    "APIFootballCardType",
    "APIFootballGoalType",
    "APIFootballScore",
    "APIFootballFixtureResult",
    "APIFootballEvent",
    "APIFootballGoal",
    "APIFootballCard",
    "APIFootballSubstitution",
    "APIFootballTeamMatchStats",
    "APIFootballMatchStatistics",
    "APIFootballLineupPlayer",
    "APIFootballCoach",
    "APIFootballTeamLineup",
    "APIFootballPlayerMatchStats",
    "APIFootballTeamPlayerStats",
    "APIFootballPostMatchContext",
    "DataSourceComparison",
    "APIFootballMatchRecord",
    
    # FotMob
    "FotMobLeagueMatch",
    "FotMobLeagueRound",
    "FotMobTeamRef",
    "FotMobMatchEvent",
    "FotMobStatValue",
    "FotMobStatCategory",
    "FotMobCoach",
    "FotMobPlayer",
    "FotMobTeamLineup",
    "FotMobPlayerDetailedStats",
    "FotMobShot",
    "FotMobMomentum",
    "FotMobMatchFacts",
    "FotMobMatchDetail",
    
    # Comparison
    "DataLayer",
    "FOTMOB_COVERAGE",
    "API_FOOTBALL_COVERAGE",
    "LayerComparison",
    "FullComparison",
    "compare_sources",
    "print_comparison_report",
    "CustomMetricPotential",
    "CUSTOM_METRICS",
    "get_metrics_by_source",
    "get_metrics_needing_both",
    "IntelligenceLayer",
    "INTELLIGENCE_ARCHITECTURE",
    
    # Matchup Intelligence
    "PlayingStyle",
    "MatchupFormTrend",
    "StrengthLevel",
    "PlayerHistoricalProfile",
    "FormationUsage",
    "ShotProfile",
    "DefensiveProfile",
    "MomentumProfile",
    "TeamTacticalProfile",
    "RecentMatch",
    "TeamForm",
    "H2HMatch",
    "H2HIntelligence",
    "PlayerMatchup",
    "MatchupIntelligence",
    "MatchupIntelligenceBuilder",
    
    # Intelligence (takes + validation)
    "IntelligenceCategory",
    "ValidationScore",
    "Take",
    "ResultTake",
    "GoalsTake",
    "DominanceTake",
    "StyleMatchupTake",
    "KeyPlayerTake",
    "DangerZonesTake",
    "MatchFlowTake",
    "TacticalTake",
    "MatchIntelligence",
    "RoundIntelligence",
    "SeasonIntelligenceTracker",
    "create_match_intelligence",
    
    # Temporal KG
    "KGIntelligenceLayer",
    "IdentityLayer",
    "PositionLayer",
    "FormLayer",
    "StyleLayer",
    "PersonnelLayer",
    "PlayerStatus",
    "AttackLayer",
    "DefenseLayer",
    "MomentumLayer",
    "TeamKGSnapshot",
    "MatchupKGSnapshot",
    "LayerDiff",
    "SnapshotDiff",
    "TeamSeasonEvolution",
    "LAYER_QUESTIONS",
    "get_layer_questions",
    "get_all_questions",
]
