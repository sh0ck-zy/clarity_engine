from __future__ import annotations

from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Outcome(Enum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"


@dataclass(frozen=True)
class NarrativeMetrics:
    avg_word_count: float
    factual_consistency_score: float
    clarity_score: float


@dataclass(frozen=True)
class OutcomeMetrics:
    wins: int
    draws: int
    losses: int
    total: int
    accuracy: float


@dataclass(frozen=True)
class CalibrationStats:
    brier_score: float
    expected_calibration_error: float


@dataclass(frozen=True)
class BettingMetrics:
    total_actions: int
    total_bets: int
    bet_rate: float
    avg_odds: Optional[float]
    win_rate: Optional[float]
    roi: Optional[float]
    max_drawdown: Optional[float]
    unpriced_bets: int


@dataclass(frozen=True)
class PromptVersionReport:
    prompt_version: str
    narrative_metrics: NarrativeMetrics
    outcome_metrics: OutcomeMetrics
    calibration_stats: CalibrationStats
    betting_metrics: Optional[BettingMetrics]
    baselines: Optional[BaselineMetrics] = None


@dataclass(frozen=True)
class BaselineMetrics:
    random_baseline_accuracy: Optional[float] = None
    majority_class_accuracy: Optional[float] = None
    bookmaker_accuracy: Optional[float] = None
    bookmaker_expected_roi: Optional[float] = None
    bookmaker_avg_odds: Optional[float] = None


@dataclass(frozen=True)
class ValidationReport:
    season: str
    league: str
    round_range: str
    leaderboard: List[PromptVersionReport]
    baselines: Optional[BaselineMetrics] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def report_schema() -> Dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ValidationReport",
        "type": "object",
        "required": ["season", "league", "round_range", "leaderboard"],
        "properties": {
            "season": {"type": "string"},
            "league": {"type": "string"},
            "round_range": {"type": "string"},
            "leaderboard": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "prompt_version",
                        "narrative_metrics",
                        "outcome_metrics",
                        "calibration_stats",
                    ],
                    "properties": {
                        "prompt_version": {"type": "string"},
                        "narrative_metrics": {
                            "type": "object",
                            "required": [
                                "avg_word_count",
                                "factual_consistency_score",
                                "clarity_score",
                            ],
                            "properties": {
                                "avg_word_count": {"type": "number"},
                                "factual_consistency_score": {"type": "number"},
                                "clarity_score": {"type": "number"},
                            },
                            "additionalProperties": False,
                        },
                        "outcome_metrics": {
                            "type": "object",
                            "required": ["wins", "draws", "losses", "total", "accuracy"],
                            "properties": {
                                "wins": {"type": "integer"},
                                "draws": {"type": "integer"},
                                "losses": {"type": "integer"},
                                "total": {"type": "integer"},
                                "accuracy": {"type": "number"},
                            },
                            "additionalProperties": False,
                        },
                        "calibration_stats": {
                            "type": "object",
                            "required": ["brier_score", "expected_calibration_error"],
                            "properties": {
                                "brier_score": {"type": "number"},
                                "expected_calibration_error": {"type": "number"},
                            },
                            "additionalProperties": False,
                        },
                        "betting_metrics": {
                            "type": ["object", "null"],
                            "required": [
                                "total_actions",
                                "total_bets",
                                "bet_rate",
                                "avg_odds",
                                "win_rate",
                                "roi",
                                "max_drawdown",
                                "unpriced_bets",
                            ],
                            "properties": {
                                "total_actions": {"type": "integer"},
                                "total_bets": {"type": "integer"},
                                "bet_rate": {"type": "number"},
                                "avg_odds": {"type": ["number", "null"]},
                                "win_rate": {"type": ["number", "null"]},
                                "roi": {"type": ["number", "null"]},
                                "max_drawdown": {"type": ["number", "null"]},
                                "unpriced_bets": {"type": "integer"},
                            },
                            "additionalProperties": False,
                        },
                        "baselines": {
                            "type": ["object", "null"],
                            "properties": {
                                "random_baseline_accuracy": {"type": ["number", "null"]},
                                "majority_class_accuracy": {"type": ["number", "null"]},
                                "bookmaker_accuracy": {"type": ["number", "null"]},
                                "bookmaker_expected_roi": {"type": ["number", "null"]},
                                "bookmaker_avg_odds": {"type": ["number", "null"]},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "additionalProperties": False,
                },
            },
            "baselines": {
                "type": ["object", "null"],
                "properties": {
                    "random_baseline_accuracy": {"type": ["number", "null"]},
                    "majority_class_accuracy": {"type": ["number", "null"]},
                    "bookmaker_accuracy": {"type": ["number", "null"]},
                    "bookmaker_expected_roi": {"type": ["number", "null"]},
                    "bookmaker_avg_odds": {"type": ["number", "null"]},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }
