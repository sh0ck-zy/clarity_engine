"""
Frozen model configuration for probabilistic motor v1.1.

DO NOT CHANGE without bumping MODEL_VERSION and re-running benchmarks.
Frozen from benchmark results: COMPACT_CORE + C=0.01 = log_loss 1.0517.
"""

from __future__ import annotations

MODEL_VERSION = "v1.1"

# Regularization
C = 0.01

# Feature subset: COMPACT_CORE (7 features)
# Drops xg_for/xg_against (collinear with xg_diff), rest_days, home_strength
FEATURE_COLS = [
    "xg_diff_last5_delta",
    "form_points_delta",
    "goal_diff_season_delta",
    "position_delta",
    "elo_delta",
    "home_venue_points",
    "away_venue_points",
]

# Walk-forward settings
MIN_TRAIN_ROUNDS = 6  # predict from R8 (60 training matches minimum)
RANDOM_STATE = 42

# Model specification
MODEL_SPEC = {
    "algorithm": "logistic_regression_multinomial",
    "solver": "lbfgs",
    "C": C,
    "max_iter": 1000,
    "random_state": RANDOM_STATE,
    "class_weight": None,
}

# Benchmark reference (from benchmark run 2026-02-23)
BENCHMARK_REF = {
    "log_loss": 1.0517,
    "accuracy": 0.468,
    "uniform_log_loss": 1.0986,
    "delta_vs_uniform": -0.0469,
    "market_log_loss": 1.0118,
    "n_predictions": 190,
    "predict_rounds": list(range(8, 27)),
}
