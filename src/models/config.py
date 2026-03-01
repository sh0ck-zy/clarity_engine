"""
Frozen model configuration for probabilistic motor v1.4.

DO NOT CHANGE without bumping MODEL_VERSION and re-running benchmarks.

v1.4 changes from v1.3:
  - Removed market-derived features (draw_signal, home_edge, entropy)
  - Market features were always zero at prediction time (odds CSV has only historical data)
  - Model now uses only features available pre-match: 8 pure-strength features
  - Benchmark TBD (will update after first run with v1.4)

v1.3 changes from v1.2:
  - Added market-derived features (draw_signal, home_edge, entropy)
  - Accuracy improved from 40.7% to 43.7% while maintaining 27.8% draw recall
  - Log loss 1.0568 (vs v1.2's 1.0586)

v1.2 changes from v1.1:
  - Added class_weight="balanced" to fix draw blindness (2% → 28% recall)
  - Switched to STRENGTH_CONTEXT (8 features, adds home_strength_delta)
"""

from __future__ import annotations

MODEL_VERSION = "v1.4"

# Regularization
C = 0.01

# Feature subset: STRENGTH_CONTEXT (8 features)
# Pure pre-match features — no market/odds dependency
FEATURE_COLS = [
    "xg_diff_last5_delta",
    "form_points_delta",
    "goal_diff_season_delta",
    "position_delta",
    "home_strength_delta",
    "elo_delta",
    "home_venue_points",
    "away_venue_points",
]

# Walk-forward settings
MIN_TRAIN_ROUNDS = 6  # predict from R8 (60 training matches minimum)
RANDOM_STATE = 42

# Probability floor: no outcome ever predicted below this threshold
PROB_FLOOR = 0.05

# Model specification
MODEL_SPEC = {
    "algorithm": "logistic_regression_multinomial",
    "solver": "lbfgs",
    "C": C,
    "max_iter": 1000,
    "random_state": RANDOM_STATE,
    "class_weight": "balanced",
}

# Benchmark reference (from benchmark run 2026-02-28)
BENCHMARK_REF = {
    "log_loss": 1.0629,
    "accuracy": 0.406,
    "draw_recall": 0.273,
    "uniform_log_loss": 1.0986,
    "delta_vs_uniform": -0.0357,
    "market_log_loss": 1.0118,
    "n_predictions": 202,
    "predict_rounds": list(range(8, 29)),
}

# Previous version references
V1_3_REF = {
    "log_loss": 1.0568,
    "accuracy": 0.437,
    "draw_recall": 0.278,
    "market_log_loss": 1.0118,
    "n_predictions": 199,
    "note": "STR_PLUS_DERIVED + C=0.01 + balanced (3 market features, always zero at pred time)",
}

V1_2_REF = {
    "log_loss": 1.0586,
    "accuracy": 0.407,
    "draw_recall": 0.278,
    "note": "STRENGTH_CONTEXT + C=0.01 + balanced",
}

V1_1_REF = {
    "log_loss": 1.0517,
    "accuracy": 0.468,
    "draw_recall": 0.019,
    "note": "COMPACT_CORE + C=0.01 + class_weight=None",
}
