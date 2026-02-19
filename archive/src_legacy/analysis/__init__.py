"""
Analysis Module - Phase 1 Match Intelligence

This module provides:
- Context building (deterministic facts layer)
- Narrative generation and validation
- Post-match evaluation
- Data coverage diagnostics
- Time-travel safety guards
- Regression alerting

Usage:
    from src.analysis import (
        ContextBuilderV2,
        validate_context,
        validate_narrative,
        CoverageAnalyzer,
        TimeTravelGuard,
        RegressionMonitor,
        ValidationEngine
    )
"""

# Context Schema (P1-001)
from src.analysis.context_schema import (
    MatchContext,
    TeamContext,
    TeamIdentity,
    TeamForm,
    TeamAbsences,
    PlayerAbsence,
    HeadToHead,
    MarketOdds,
    ScheduleContext,
    LeaguePosition,
    validate_context,
    calculate_coverage_score,
    context_to_dict,
    context_to_json,
)

# Context Builder (P1-003)
from src.analysis.context_builder_v2 import (
    ContextBuilderV2,
    build_match_context,
    validate_and_build,
)

# Data Coverage (P1-002, P1-004)
from src.analysis.data_coverage import (
    CoverageAnalyzer,
    CoverageReport,
    DataSourceStatus,
    FixtureCoverage,
    SeasonCoverage,
    run_coverage_diagnostics,
    save_coverage_report,
)

# Narrative Schema (P1-006)
from src.analysis.narrative_schema import (
    NarrativeOutput,
    ScorePrediction,
    KeyDriver,
    SwingFactor,
    RiskFlag,
    GameFlow,
    TacticalDynamic,
    MarketVerdict,
    GlassBoxLogic,
    validate_narrative,
    parse_narrative,
    validate_no_external_facts,
)

# Time-Travel Guard (P1-008)
from src.analysis.time_travel_guard import (
    TimeTravelGuard,
    TimeTravelViolation,
    validate_context_time_safety,
    run_time_travel_audit,
)

# Regression Alerts (P1-012)
from src.analysis.regression_alerts import (
    RegressionMonitor,
    RegressionAlert,
    AlertThresholds,
    check_for_regressions,
    get_alert_summary,
)

# Validation Engine (existing)
from src.analysis.validation import (
    ValidationEngine,
    run_validation,
    compare_all_prompts,
)

# Legacy Builder (for backward compatibility)
from src.analysis.builder import MatchContextBuilder

# Predictor (existing)
from src.analysis.predictor import ClarityEngine

# Evaluator (existing)
from src.analysis.evaluator import AnalysisEvaluator

# Reality (existing)
from src.analysis.reality import RealitySeeker


__all__ = [
    # Context Schema
    "MatchContext",
    "TeamContext",
    "TeamIdentity",
    "TeamForm",
    "TeamAbsences",
    "PlayerAbsence",
    "HeadToHead",
    "MarketOdds",
    "ScheduleContext",
    "LeaguePosition",
    "validate_context",
    "calculate_coverage_score",
    "context_to_dict",
    "context_to_json",
    # Context Builder
    "ContextBuilderV2",
    "build_match_context",
    "validate_and_build",
    "MatchContextBuilder",  # Legacy
    # Data Coverage
    "CoverageAnalyzer",
    "CoverageReport",
    "DataSourceStatus",
    "FixtureCoverage",
    "SeasonCoverage",
    "run_coverage_diagnostics",
    "save_coverage_report",
    # Narrative Schema
    "NarrativeOutput",
    "ScorePrediction",
    "KeyDriver",
    "SwingFactor",
    "RiskFlag",
    "GameFlow",
    "TacticalDynamic",
    "MarketVerdict",
    "GlassBoxLogic",
    "validate_narrative",
    "parse_narrative",
    "validate_no_external_facts",
    # Time-Travel Guard
    "TimeTravelGuard",
    "TimeTravelViolation",
    "validate_context_time_safety",
    "run_time_travel_audit",
    # Regression Alerts
    "RegressionMonitor",
    "RegressionAlert",
    "AlertThresholds",
    "check_for_regressions",
    "get_alert_summary",
    # Validation
    "ValidationEngine",
    "run_validation",
    "compare_all_prompts",
    # Core Engines
    "ClarityEngine",
    "AnalysisEvaluator",
    "RealitySeeker",
]
