from pathlib import Path

from src.validation.action_extractor import Action, ActionType, BetSelection
from src.validation.engine import ValidationEngine, ValidationRecord
from src.validation.report_schema import (
    BaselineMetrics,
    CalibrationStats,
    NarrativeMetrics,
    Outcome,
    OutcomeMetrics,
)


def test_leaderboard_sorted_by_prompt_version():
    engine = ValidationEngine(
        records=[
            ValidationRecord(
                prompt_version="v2",
                narrative_metrics=NarrativeMetrics(120.0, 0.72, 0.81),
                outcome_metrics=OutcomeMetrics(2, 1, 1, 4, 0.5),
                calibration_stats=CalibrationStats(0.2, 0.1),
                outcomes=[Outcome.HOME, Outcome.DRAW],
            ),
            ValidationRecord(
                prompt_version="v1",
                narrative_metrics=NarrativeMetrics(110.0, 0.68, 0.79),
                outcome_metrics=OutcomeMetrics(1, 1, 2, 4, 0.25),
                calibration_stats=CalibrationStats(0.3, 0.15),
                outcomes=[Outcome.AWAY, Outcome.HOME],
            ),
        ]
    )

    leaderboard = engine.build_leaderboard()

    assert [entry.prompt_version for entry in leaderboard] == ["v1", "v2"]
    for entry in leaderboard:
        assert entry.baselines is not None
        assert entry.baselines.random_baseline_accuracy == 1.0 / 3.0
        assert entry.baselines.majority_class_accuracy == 0.5
        assert entry.baselines.bookmaker_accuracy is None
        assert entry.baselines.bookmaker_expected_roi is None
        assert entry.baselines.bookmaker_avg_odds is None


def test_save_report_to_default_path(tmp_path: Path):
    engine = ValidationEngine(
        records=[
            ValidationRecord(
                prompt_version="v1",
                narrative_metrics=NarrativeMetrics(100.0, 0.7, 0.8),
                outcome_metrics=OutcomeMetrics(1, 1, 0, 2, 0.5),
                calibration_stats=CalibrationStats(0.25, 0.12),
            )
        ]
    )
    report = engine.build_report("2025", "EPL", "1-2")
    output_path = tmp_path / "validation_report.json"

    engine.save_report(report, output_path)

    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "\"prompt_version\": \"v1\"" in content


def test_betting_metrics_roi_and_drawdown():
    engine = ValidationEngine(
        records=[
            ValidationRecord(
                prompt_version="v1",
                narrative_metrics=NarrativeMetrics(90.0, 0.6, 0.7),
                outcome_metrics=OutcomeMetrics(1, 0, 1, 2, 0.5),
                calibration_stats=CalibrationStats(0.2, 0.1),
                actions=[
                    Action(
                        action_type=ActionType.BET_1X2,
                        selection=BetSelection.HOME,
                        market_key="1X2",
                        selection_key=BetSelection.HOME.value,
                        fixture_id="fixture-1",
                    ),
                    Action(
                        action_type=ActionType.BET_1X2,
                        selection=BetSelection.AWAY,
                        market_key="1X2",
                        selection_key=BetSelection.AWAY.value,
                        fixture_id="fixture-2",
                    ),
                ],
                odds_snapshots=[
                    {
                        "fixture_id": "fixture-1",
                        "market_key": "1X2",
                        "selection_key": "HOME",
                        "odds_decimal": 2.0,
                    },
                    {
                        "fixture_id": "fixture-2",
                        "market_key": "1X2",
                        "selection_key": "AWAY",
                        "odds_decimal": 3.0,
                    },
                ],
                outcomes=[Outcome.HOME, Outcome.HOME],
            )
        ]
    )

    leaderboard = engine.build_leaderboard()
    metrics = leaderboard[0].betting_metrics
    baselines = leaderboard[0].baselines

    assert metrics is not None
    assert metrics.total_actions == 2
    assert metrics.total_bets == 2
    assert metrics.unpriced_bets == 0
    assert metrics.avg_odds == 2.5
    assert metrics.win_rate == 0.5
    assert metrics.roi == 0.0
    assert metrics.max_drawdown == 1.0
    assert baselines == BaselineMetrics(
        random_baseline_accuracy=1.0 / 3.0,
        majority_class_accuracy=1.0,
        bookmaker_accuracy=0.5,
        bookmaker_expected_roi=0.0,
        bookmaker_avg_odds=2.5,
    )


def test_betting_metrics_with_missing_odds():
    engine = ValidationEngine(
        records=[
            ValidationRecord(
                prompt_version="v1",
                narrative_metrics=NarrativeMetrics(90.0, 0.6, 0.7),
                outcome_metrics=OutcomeMetrics(1, 0, 0, 1, 1.0),
                calibration_stats=CalibrationStats(0.2, 0.1),
                actions=[
                    Action(
                        action_type=ActionType.BET_1X2,
                        selection=BetSelection.HOME,
                        market_key="1X2",
                        selection_key=BetSelection.HOME.value,
                        fixture_id="fixture-1",
                    )
                ],
                odds_snapshots=[],
                outcomes=[Outcome.HOME],
            )
        ]
    )

    leaderboard = engine.build_leaderboard()
    metrics = leaderboard[0].betting_metrics
    baselines = leaderboard[0].baselines

    assert metrics is not None
    assert metrics.total_actions == 1
    assert metrics.total_bets == 1
    assert metrics.unpriced_bets == 1
    assert metrics.roi is None
    assert metrics.win_rate is None
    assert baselines == BaselineMetrics(
        random_baseline_accuracy=1.0 / 3.0,
        majority_class_accuracy=1.0,
        bookmaker_accuracy=None,
        bookmaker_expected_roi=None,
        bookmaker_avg_odds=None,
    )
