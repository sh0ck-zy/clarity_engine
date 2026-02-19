"""
Clarity Engine Backtest System.

Compare Coded Agent vs OpenClaw Agent against historical results.
"""

from .runner import BacktestRunner
from .fixtures import get_round_fixtures
from .reality import get_match_reality
from .evaluator import evaluate_predictions

__all__ = [
    "BacktestRunner",
    "get_round_fixtures",
    "get_match_reality",
    "evaluate_predictions",
]
