"""
Data Source Comparison Utilities

Tools to compare depth, overlaps, and gaps between:
- FotMob data (rich match detail, player stats, shotmaps, momentum)
- API-Football data (structured endpoints, predictions, odds, xG)

Use this to:
1. Identify what each source provides uniquely
2. Find overlapping data for cross-validation
3. Discover gaps that need alternative sources
4. Plan the intelligence layer architecture

Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from enum import Enum


class DataLayer(Enum):
    """Intelligence layers for match analysis."""
    FIXTURE_INFO = "fixture_info"           # Basic match data
    STANDINGS = "standings"                  # League position
    FORM = "form"                           # Recent performance
    H2H = "h2h"                             # Head to head
    PREDICTIONS = "predictions"              # Market/API predictions
    ODDS = "odds"                           # Betting odds
    INJURIES = "injuries"                   # Player availability
    LINEUPS = "lineups"                     # Formations, XI
    PLAYER_STATS = "player_stats"           # Individual stats
    TEAM_STATS = "team_stats"               # Team match stats
    XG = "xg"                               # Expected goals
    EVENTS = "events"                       # Goals, cards, subs
    SHOTMAP = "shotmap"                     # Shot locations/quality
    MOMENTUM = "momentum"                   # Match flow
    MATCH_FACTS = "match_facts"             # Insights, MOTM
    COMMENTARY = "commentary"               # Minute-by-minute


# ============================================================
# DATA AVAILABILITY MATRIX
# ============================================================

FOTMOB_COVERAGE = {
    # Pre-match
    DataLayer.FIXTURE_INFO: {
        "available": True,
        "depth": "high",
        "fields": ["venue", "attendance", "referee", "round", "season"],
        "notes": "Complete fixture metadata"
    },
    DataLayer.STANDINGS: {
        "available": False,
        "depth": "none",
        "fields": [],
        "notes": "Not available in match detail API"
    },
    DataLayer.FORM: {
        "available": True,
        "depth": "medium",
        "fields": ["team_form in match_facts"],
        "notes": "Team form available in match facts"
    },
    DataLayer.H2H: {
        "available": False,
        "depth": "none",
        "fields": [],
        "notes": "Not in match detail, might be separate endpoint"
    },
    DataLayer.PREDICTIONS: {
        "available": False,
        "depth": "none",
        "fields": [],
        "notes": "FotMob doesn't provide predictions"
    },
    DataLayer.ODDS: {
        "available": False,
        "depth": "none",
        "fields": [],
        "notes": "FotMob doesn't provide odds"
    },
    DataLayer.INJURIES: {
        "available": True,
        "depth": "high",
        "fields": ["unavailable players in lineup"],
        "notes": "Injuries embedded in lineup data"
    },
    
    # Match data
    DataLayer.LINEUPS: {
        "available": True,
        "depth": "very_high",
        "fields": [
            "formation", "starters", "subs", "positions", "ratings",
            "coach", "avg_rating", "player_events", "market_value"
        ],
        "notes": "Most complete lineup data with ratings"
    },
    DataLayer.PLAYER_STATS: {
        "available": True,
        "depth": "very_high",
        "fields": [
            "minutes", "goals", "assists", "xG", "xGOT", "xA",
            "shots", "shots_on_target", "passes", "passes_accurate",
            "chances_created", "tackles", "interceptions", "rating",
            "fantasy_score", "defensive_actions"
        ],
        "notes": "Extremely detailed per-player stats"
    },
    DataLayer.TEAM_STATS: {
        "available": True,
        "depth": "very_high",
        "fields": [
            "possession", "shots", "shots_on_target", "xG",
            "passes", "pass_accuracy", "big_chances", "corners",
            "fouls", "yellow_cards", "red_cards"
        ],
        "notes": "Full team-level stats by period (All/1H/2H)"
    },
    DataLayer.XG: {
        "available": True,
        "depth": "very_high",
        "fields": ["team_xg", "player_xg", "xgot", "xA", "per_shot_xg"],
        "notes": "xG at team and player level + shot-level xG"
    },
    DataLayer.EVENTS: {
        "available": True,
        "depth": "high",
        "fields": ["goals", "cards", "subs", "penalties", "var"],
        "notes": "Full event timeline"
    },
    DataLayer.SHOTMAP: {
        "available": True,
        "depth": "very_high",
        "fields": ["x", "y", "xG", "event_type", "is_on_target", "player"],
        "notes": "Shot-by-shot with coordinates and xG"
    },
    DataLayer.MOMENTUM: {
        "available": True,
        "depth": "high",
        "fields": ["minute-by-minute momentum values"],
        "notes": "Match flow visualization data"
    },
    DataLayer.MATCH_FACTS: {
        "available": True,
        "depth": "high",
        "fields": ["motm", "top_players", "insights", "info_box"],
        "notes": "Match insights and key facts"
    },
    DataLayer.COMMENTARY: {
        "available": True,
        "depth": "high",
        "fields": ["minute-by-minute text commentary"],
        "notes": "Full match commentary available"
    },
}

API_FOOTBALL_COVERAGE = {
    # Pre-match
    DataLayer.FIXTURE_INFO: {
        "available": True,
        "depth": "high",
        "fields": ["venue", "referee", "status", "periods", "round"],
        "notes": "Complete fixture data"
    },
    DataLayer.STANDINGS: {
        "available": True,
        "depth": "very_high",
        "fields": [
            "rank", "points", "goals_diff", "form",
            "home_record", "away_record", "all_record"
        ],
        "notes": "Full league table with home/away breakdown"
    },
    DataLayer.FORM: {
        "available": True,
        "depth": "very_high",
        "fields": ["form_string", "last_5_analysis", "att/def ratings"],
        "notes": "Detailed form analysis in predictions"
    },
    DataLayer.H2H: {
        "available": True,
        "depth": "very_high",
        "fields": ["historical_matches", "results", "venues", "leagues"],
        "notes": "Full H2H history in predictions endpoint"
    },
    DataLayer.PREDICTIONS: {
        "available": True,
        "depth": "very_high",
        "fields": [
            "winner", "win_or_draw", "under_over", "advice",
            "percentages", "team_comparison", "poisson"
        ],
        "notes": "API-native predictions with reasoning"
    },
    DataLayer.ODDS: {
        "available": True,
        "depth": "very_high",
        "fields": [
            "1X2", "over_under", "btts", "asian_handicap",
            "bookmaker_ids", "timestamps", "all_markets"
        ],
        "notes": "Multi-bookmaker odds with history"
    },
    DataLayer.INJURIES: {
        "available": True,
        "depth": "high",
        "fields": ["player", "team", "type", "reason", "fixture"],
        "notes": "Dedicated injuries endpoint"
    },
    
    # Match data
    DataLayer.LINEUPS: {
        "available": True,
        "depth": "high",
        "fields": ["formation", "starting_xi", "subs", "coach", "grid"],
        "notes": "Full lineup with grid positions"
    },
    DataLayer.PLAYER_STATS: {
        "available": True,
        "depth": "very_high",
        "fields": [
            "minutes", "rating", "goals", "assists", "shots",
            "passes", "dribbles", "tackles", "duels", "cards",
            "offsides", "fouls"
        ],
        "notes": "Comprehensive player match stats"
    },
    DataLayer.TEAM_STATS: {
        "available": True,
        "depth": "very_high",
        "fields": [
            "xG", "shots", "possession", "passes",
            "corners", "fouls", "cards", "offsides"
        ],
        "notes": "Full team statistics"
    },
    DataLayer.XG: {
        "available": True,
        "depth": "high",
        "fields": ["team_xg"],
        "notes": "Team-level xG only (no per-shot)"
    },
    DataLayer.EVENTS: {
        "available": True,
        "depth": "high",
        "fields": ["goals", "cards", "subs", "var"],
        "notes": "Full event timeline"
    },
    DataLayer.SHOTMAP: {
        "available": False,
        "depth": "none",
        "fields": [],
        "notes": "No shot coordinates available"
    },
    DataLayer.MOMENTUM: {
        "available": False,
        "depth": "none",
        "fields": [],
        "notes": "No momentum data"
    },
    DataLayer.MATCH_FACTS: {
        "available": False,
        "depth": "none",
        "fields": [],
        "notes": "No match insights/facts"
    },
    DataLayer.COMMENTARY: {
        "available": False,
        "depth": "none",
        "fields": [],
        "notes": "No commentary available"
    },
}


# ============================================================
# COMPARISON ANALYSIS
# ============================================================

@dataclass
class LayerComparison:
    """Comparison of a single data layer between sources."""
    layer: DataLayer
    
    fotmob_available: bool
    fotmob_depth: str
    fotmob_fields: List[str]
    
    api_football_available: bool
    api_football_depth: str
    api_football_fields: List[str]
    
    # Analysis
    overlap: List[str] = field(default_factory=list)
    only_fotmob: List[str] = field(default_factory=list)
    only_api_football: List[str] = field(default_factory=list)
    
    winner: str = "tie"  # "fotmob", "api_football", "tie", "neither"
    recommendation: str = ""


@dataclass
class FullComparison:
    """Complete comparison between FotMob and API-Football."""
    
    layers: List[LayerComparison] = field(default_factory=list)
    
    # Summary
    fotmob_unique_strengths: List[str] = field(default_factory=list)
    api_football_unique_strengths: List[str] = field(default_factory=list)
    
    # Recommendations
    use_fotmob_for: List[DataLayer] = field(default_factory=list)
    use_api_football_for: List[DataLayer] = field(default_factory=list)
    use_both_for: List[DataLayer] = field(default_factory=list)
    gaps_need_other_source: List[DataLayer] = field(default_factory=list)
    
    analyzed_at: datetime = field(default_factory=datetime.now)


def compare_sources() -> FullComparison:
    """Generate full comparison between FotMob and API-Football."""
    
    comparison = FullComparison()
    
    for layer in DataLayer:
        fotmob = FOTMOB_COVERAGE.get(layer, {})
        api_fb = API_FOOTBALL_COVERAGE.get(layer, {})
        
        layer_cmp = LayerComparison(
            layer=layer,
            fotmob_available=fotmob.get("available", False),
            fotmob_depth=fotmob.get("depth", "none"),
            fotmob_fields=fotmob.get("fields", []),
            api_football_available=api_fb.get("available", False),
            api_football_depth=api_fb.get("depth", "none"),
            api_football_fields=api_fb.get("fields", []),
        )
        
        # Determine winner
        if layer_cmp.fotmob_available and not layer_cmp.api_football_available:
            layer_cmp.winner = "fotmob"
            comparison.use_fotmob_for.append(layer)
        elif layer_cmp.api_football_available and not layer_cmp.fotmob_available:
            layer_cmp.winner = "api_football"
            comparison.use_api_football_for.append(layer)
        elif layer_cmp.fotmob_available and layer_cmp.api_football_available:
            # Both available - compare depth
            depth_order = ["none", "low", "medium", "high", "very_high"]
            fm_depth = depth_order.index(layer_cmp.fotmob_depth) if layer_cmp.fotmob_depth in depth_order else 0
            af_depth = depth_order.index(layer_cmp.api_football_depth) if layer_cmp.api_football_depth in depth_order else 0
            
            if fm_depth > af_depth:
                layer_cmp.winner = "fotmob"
            elif af_depth > fm_depth:
                layer_cmp.winner = "api_football"
            else:
                layer_cmp.winner = "tie"
            
            comparison.use_both_for.append(layer)
        else:
            layer_cmp.winner = "neither"
            comparison.gaps_need_other_source.append(layer)
        
        comparison.layers.append(layer_cmp)
    
    # Summary strengths
    comparison.fotmob_unique_strengths = [
        "Shotmap with per-shot xG coordinates",
        "Momentum/match flow data",
        "Match facts and insights",
        "Player ratings with fantasy scores",
        "Commentary timeline",
        "Unavailable players in lineup",
    ]
    
    comparison.api_football_unique_strengths = [
        "League standings with full breakdown",
        "Predictions with comparison metrics",
        "Multi-bookmaker odds with history",
        "H2H historical matches",
        "Dedicated injuries endpoint",
        "Structured team season statistics",
    ]
    
    return comparison


def print_comparison_report(comparison: FullComparison) -> str:
    """Generate a human-readable comparison report."""
    
    lines = [
        "=" * 70,
        "DATA SOURCE COMPARISON: FotMob vs API-Football",
        "=" * 70,
        "",
        "## LAYER BY LAYER ANALYSIS",
        "",
    ]
    
    for lc in comparison.layers:
        emoji = {
            "fotmob": "🟢",
            "api_football": "🔵",
            "tie": "⚖️",
            "neither": "❌"
        }.get(lc.winner, "?")
        
        lines.append(f"### {lc.layer.value.upper()}")
        lines.append(f"  Winner: {emoji} {lc.winner}")
        lines.append(f"  FotMob: {'✅' if lc.fotmob_available else '❌'} ({lc.fotmob_depth})")
        lines.append(f"  API-FB: {'✅' if lc.api_football_available else '❌'} ({lc.api_football_depth})")
        lines.append("")
    
    lines.extend([
        "=" * 70,
        "## RECOMMENDATIONS",
        "",
        "### Use FotMob for:",
    ])
    for layer in comparison.use_fotmob_for:
        lines.append(f"  - {layer.value}")
    
    lines.extend([
        "",
        "### Use API-Football for:",
    ])
    for layer in comparison.use_api_football_for:
        lines.append(f"  - {layer.value}")
    
    lines.extend([
        "",
        "### Use BOTH (cross-validate):",
    ])
    for layer in comparison.use_both_for:
        lines.append(f"  - {layer.value}")
    
    lines.extend([
        "",
        "### Gaps (need other source):",
    ])
    for layer in comparison.gaps_need_other_source:
        lines.append(f"  - {layer.value}")
    
    lines.extend([
        "",
        "=" * 70,
        "## UNIQUE STRENGTHS",
        "",
        "### FotMob Exclusive:",
    ])
    for s in comparison.fotmob_unique_strengths:
        lines.append(f"  ✨ {s}")
    
    lines.extend([
        "",
        "### API-Football Exclusive:",
    ])
    for s in comparison.api_football_unique_strengths:
        lines.append(f"  ✨ {s}")
    
    return "\n".join(lines)


# ============================================================
# CUSTOM METRICS POTENTIAL
# ============================================================

@dataclass
class CustomMetricPotential:
    """Identifies what custom metrics can be calculated from combined data."""
    
    name: str
    description: str
    required_layers: List[DataLayer]
    sources_needed: List[str]  # "fotmob", "api_football", or "both"
    formula_hint: str
    use_case: str


CUSTOM_METRICS = [
    CustomMetricPotential(
        name="xG_outperformance",
        description="Goals scored minus xG over time",
        required_layers=[DataLayer.XG, DataLayer.EVENTS],
        sources_needed=["fotmob"],
        formula_hint="actual_goals - sum(shot_xg)",
        use_case="Identify lucky/unlucky teams, regression candidates"
    ),
    CustomMetricPotential(
        name="market_vs_model_divergence",
        description="Difference between odds-implied prob and API predictions",
        required_layers=[DataLayer.ODDS, DataLayer.PREDICTIONS],
        sources_needed=["api_football"],
        formula_hint="abs(implied_prob - prediction_percent)",
        use_case="Find value bets where market disagrees with model"
    ),
    CustomMetricPotential(
        name="form_momentum_score",
        description="Combined form + standings trajectory + momentum",
        required_layers=[DataLayer.FORM, DataLayer.STANDINGS, DataLayer.MOMENTUM],
        sources_needed=["both"],
        formula_hint="weighted(form_points, position_change, avg_momentum)",
        use_case="Overall team confidence/trajectory metric"
    ),
    CustomMetricPotential(
        name="injury_impact_score",
        description="Impact of missing players on team strength",
        required_layers=[DataLayer.INJURIES, DataLayer.PLAYER_STATS],
        sources_needed=["both"],
        formula_hint="sum(missing_player_rating * minutes_share)",
        use_case="Adjust predictions for key absences"
    ),
    CustomMetricPotential(
        name="shot_quality_differential",
        description="Difference in average xG per shot between teams",
        required_layers=[DataLayer.SHOTMAP, DataLayer.XG],
        sources_needed=["fotmob"],
        formula_hint="(home_xg/home_shots) - (away_xg/away_shots)",
        use_case="Measure chance creation quality"
    ),
    CustomMetricPotential(
        name="h2h_venue_adjusted_score",
        description="H2H performance adjusted for venue advantage",
        required_layers=[DataLayer.H2H, DataLayer.STANDINGS],
        sources_needed=["api_football"],
        formula_hint="h2h_win_rate * venue_factor * form_factor",
        use_case="Historical matchup predictor"
    ),
]


def get_metrics_by_source(source: str) -> List[CustomMetricPotential]:
    """Get metrics that can be calculated with a given source."""
    return [m for m in CUSTOM_METRICS if source in m.sources_needed or "both" in m.sources_needed]


def get_metrics_needing_both() -> List[CustomMetricPotential]:
    """Get metrics that require both sources."""
    return [m for m in CUSTOM_METRICS if "both" in m.sources_needed]


# ============================================================
# CORRECTED DATA FLOW
# ============================================================
"""
KEY INSIGHT: Pre-match intelligence is built FROM post-match data!

    ┌─────────────────────────────────────────────────────────────────┐
    │                    THE REAL DATA FLOW                            │
    ├─────────────────────────────────────────────────────────────────┤
    │                                                                  │
    │  HISTORICAL POST-MATCH DATA (FotMob)                            │
    │  ┌──────────────────────────────────────────────────────────┐   │
    │  │ Last 10 Home Team matches:                                │   │
    │  │   - Shotmaps → shot patterns, xG quality                  │   │
    │  │   - Momentum → when they're strong/weak                   │   │
    │  │   - Player stats → form, key performers                   │   │
    │  │   - Lineups → tactical flexibility                        │   │
    │  │                                                           │   │
    │  │ Last 10 Away Team matches:                                │   │
    │  │   - Same analysis...                                      │   │
    │  │                                                           │   │
    │  │ Historical H2H matches:                                   │   │
    │  │   - Pattern between these specific teams                  │   │
    │  └──────────────────────────────────────────────────────────┘   │
    │                           │                                      │
    │                           ▼                                      │
    │  MATCHUP INTELLIGENCE (derived pre-match context)               │
    │  ┌──────────────────────────────────────────────────────────┐   │
    │  │ - Team tactical profiles (from historical analysis)       │   │
    │  │ - Form trajectories (xG trends, momentum patterns)        │   │
    │  │ - Key player matchups (historical performances)           │   │
    │  │ - Style matchup prediction (how they'll interact)         │   │
    │  │ - Predicted xG, possession, patterns                      │   │
    │  └──────────────────────────────────────────────────────────┘   │
    │                           │                                      │
    │                           ▼                                      │
    │  MARKET CONTEXT (API-Football - validation layer)               │
    │  ┌──────────────────────────────────────────────────────────┐   │
    │  │ - Odds → what the market thinks                           │   │
    │  │ - Predictions → API model probabilities                   │   │
    │  │ - Compare with our derived intelligence                   │   │
    │  │ - Find divergences → potential value                      │   │
    │  └──────────────────────────────────────────────────────────┘   │
    │                                                                  │
    └─────────────────────────────────────────────────────────────────┘

FotMob is PRIMARY for both pre-match (via history) AND post-match!
API-Football is SECONDARY (market validation + gaps like standings).
"""


# ============================================================
# INTELLIGENCE LAYER ARCHITECTURE
# ============================================================

@dataclass
class IntelligenceLayer:
    """
    Defines an intelligence layer for match analysis.
    
    Each layer combines data from sources to produce insights.
    """
    name: str
    description: str
    
    # Data requirements
    pre_match_layers: List[DataLayer]
    post_match_layers: List[DataLayer]
    
    # Source mapping
    primary_source: str  # "fotmob", "api_football", or "both"
    
    # Output
    output_type: str  # "score", "probability", "category", "narrative"
    
    # Optional fields (must come after required fields)
    fallback_source: Optional[str] = None
    output_fields: List[str] = field(default_factory=list)


INTELLIGENCE_ARCHITECTURE = [
    # ============================================================
    # PRE-MATCH INTELLIGENCE (built from historical post-match data)
    # ============================================================
    IntelligenceLayer(
        name="team_tactical_profile",
        description="Tactical profile from last N matches (formations, style, patterns)",
        pre_match_layers=[DataLayer.LINEUPS, DataLayer.TEAM_STATS, DataLayer.SHOTMAP, DataLayer.MOMENTUM],
        post_match_layers=[],  # Built FROM post-match data of PAST matches
        primary_source="fotmob",
        output_type="profile",
        fallback_source=None,
        output_fields=["formation", "playing_style", "shot_profile", "momentum_profile", "key_players"]
    ),
    IntelligenceLayer(
        name="form_trajectory",
        description="Recent form with xG trends (more predictive than results)",
        pre_match_layers=[DataLayer.TEAM_STATS, DataLayer.XG, DataLayer.EVENTS],
        post_match_layers=[],  # Built FROM post-match data of PAST matches
        primary_source="fotmob",
        output_type="score",
        fallback_source=None,
        output_fields=["form_trend", "xG_trend", "regression_risk", "overperformance"]
    ),
    IntelligenceLayer(
        name="h2h_intelligence",
        description="Head-to-head patterns and historical context",
        pre_match_layers=[DataLayer.EVENTS, DataLayer.TEAM_STATS, DataLayer.XG],
        post_match_layers=[],  # Built FROM post-match data of H2H matches
        primary_source="fotmob",
        output_type="analysis",
        fallback_source="api_football",  # API-Football has H2H endpoint too
        output_fields=["h2h_record", "patterns", "venue_impact", "scoring_trends"]
    ),
    IntelligenceLayer(
        name="player_matchups",
        description="Key player vs player/system matchups",
        pre_match_layers=[DataLayer.PLAYER_STATS, DataLayer.LINEUPS],
        post_match_layers=[],  # Built FROM historical player performances
        primary_source="fotmob",
        output_type="matchups",
        fallback_source=None,
        output_fields=["key_battles", "advantage", "impact_prediction"]
    ),
    IntelligenceLayer(
        name="availability_impact",
        description="Impact of missing players on team strength",
        pre_match_layers=[DataLayer.INJURIES, DataLayer.PLAYER_STATS],
        post_match_layers=[],
        primary_source="both",
        output_type="score",
        fallback_source=None,
        output_fields=["home_impact", "away_impact", "key_absences", "replacement_quality"]
    ),
    IntelligenceLayer(
        name="matchup_prediction",
        description="Derived predictions from tactical analysis",
        pre_match_layers=[],  # Built from other intelligence layers
        post_match_layers=[],
        primary_source="fotmob",  # Primary source for underlying data
        output_type="prediction",
        fallback_source=None,
        output_fields=["predicted_xG", "style_matchup", "key_factors", "confidence"]
    ),
    
    # ============================================================
    # MARKET VALIDATION (API-Football - secondary/validation)
    # ============================================================
    IntelligenceLayer(
        name="market_context",
        description="Odds and market predictions (validation layer)",
        pre_match_layers=[DataLayer.ODDS, DataLayer.PREDICTIONS, DataLayer.STANDINGS],
        post_match_layers=[],
        primary_source="api_football",
        output_type="market",
        fallback_source=None,
        output_fields=["implied_probs", "market_advice", "standings_context"]
    ),
    IntelligenceLayer(
        name="value_detection",
        description="Compare model predictions vs market odds",
        pre_match_layers=[DataLayer.ODDS],
        post_match_layers=[],
        primary_source="derived",  # Combines fotmob analysis + api_football odds
        output_type="value",
        fallback_source=None,
        output_fields=["divergences", "value_bets", "confidence"]
    ),
    
    # ============================================================
    # POST-MATCH ANALYSIS (for next iteration of intelligence)
    # ============================================================
    IntelligenceLayer(
        name="match_reality",
        description="What actually happened (feeds future predictions)",
        pre_match_layers=[],
        post_match_layers=[DataLayer.EVENTS, DataLayer.TEAM_STATS, DataLayer.PLAYER_STATS],
        primary_source="fotmob",
        output_type="reality",
        fallback_source="api_football",
        output_fields=["result", "xG_actual", "key_moments", "ratings"]
    ),
    IntelligenceLayer(
        name="shot_analysis",
        description="Shot-by-shot breakdown with xG",
        pre_match_layers=[],
        post_match_layers=[DataLayer.SHOTMAP, DataLayer.XG],
        primary_source="fotmob",
        output_type="analysis",
        fallback_source=None,
        output_fields=["shots", "xG_per_shot", "conversion", "patterns"]
    ),
    IntelligenceLayer(
        name="momentum_flow",
        description="Match flow and turning points",
        pre_match_layers=[],
        post_match_layers=[DataLayer.MOMENTUM, DataLayer.EVENTS],
        primary_source="fotmob",
        output_type="narrative",
        fallback_source=None,
        output_fields=["dominant_periods", "turning_points", "late_game_pattern"]
    ),
]


if __name__ == "__main__":
    # Generate and print comparison report
    comparison = compare_sources()
    report = print_comparison_report(comparison)
    print(report)
    
    print("\n" + "=" * 70)
    print("## CUSTOM METRICS POTENTIAL")
    print("=" * 70 + "\n")
    
    for metric in CUSTOM_METRICS:
        print(f"### {metric.name}")
        print(f"  {metric.description}")
        print(f"  Sources: {', '.join(metric.sources_needed)}")
        print(f"  Use case: {metric.use_case}")
        print()
