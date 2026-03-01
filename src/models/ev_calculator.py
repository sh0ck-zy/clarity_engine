"""
Expected Value (EV) calculator for football match predictions.

Computes EV, Kelly fraction, and Closing Line Value (CLV) by comparing
model probabilities against bookmaker odds.

EV = (model_probability × decimal_odds) - 1.0
Kelly = (model_prob × odds - 1) / (odds - 1)
CLV = model_implied_odds / closing_odds - 1
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ──────────────────────────────────────────────
#  Core EV functions
# ──────────────────────────────────────────────


def compute_ev(model_prob: float, decimal_odds: float) -> float:
    """
    Expected Value of a bet.

    EV = (model_prob × decimal_odds) - 1.0

    Returns:
        Positive = profitable bet (e.g., +0.05 = +5% edge)
        Negative = losing bet
    """
    return (model_prob * decimal_odds) - 1.0


def kelly_fraction(model_prob: float, decimal_odds: float) -> float:
    """
    Full Kelly criterion: optimal fraction of bankroll to stake.

    f* = (p × b - q) / b
    where b = odds - 1, p = model_prob, q = 1 - p

    Returns 0.0 if bet has negative EV (never bet negative Kelly).
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - model_prob
    f = (model_prob * b - q) / b
    return max(f, 0.0)


def fractional_kelly(
    model_prob: float, decimal_odds: float, fraction: float = 0.25
) -> float:
    """
    Quarter-Kelly (default). Safer for noisy probability estimates.

    Most practitioners use 1/4 Kelly because:
    - Full Kelly assumes perfect probability estimates
    - Our model has log loss 1.057 vs market 1.012 → probabilities are noisy
    - Quarter Kelly has ~75% of Full Kelly growth with much less variance
    """
    return fraction * kelly_fraction(model_prob, decimal_odds)


# ──────────────────────────────────────────────
#  Match-level EV computation
# ──────────────────────────────────────────────

# Columns in football-data.co.uk CSV for each bookmaker
_BOOKMAKER_COLS = {
    "b365": ("B365H", "B365D", "B365A"),
    "pinnacle": ("PSH", "PSD", "PSA"),
    "max_market": ("MaxH", "MaxD", "MaxA"),
    "betfair": ("BFEH", "BFED", "BFEA"),
    "avg_market": ("AvgH", "AvgD", "AvgA"),
}

# Closing odds columns (prefixed with C)
_CLOSING_COLS = {
    "b365": ("B365CH", "B365CD", "B365CA"),
    "pinnacle": ("PSCH", "PSCD", "PSCA"),
    "max_market": ("MaxCH", "MaxCD", "MaxCA"),
    "avg_market": ("AvgCH", "AvgCD", "AvgCA"),
}

OUTCOMES = ["H", "D", "A"]


def compute_match_ev(
    model_probs: Dict[str, float],
    odds_row: pd.Series,
) -> Dict[str, Any]:
    """
    Compute EV for all 3 outcomes across multiple bookmakers for one match.

    Args:
        model_probs: {"H": 0.55, "D": 0.25, "A": 0.20}
        odds_row: Row from football-data.co.uk CSV with odds columns

    Returns:
        Dict with EV per outcome per bookmaker, best EV, Kelly fractions, etc.
    """
    result: Dict[str, Any] = {}

    best_ev = -999.0
    best_outcome = ""
    best_bookmaker = ""
    best_odds = 0.0

    for bk_name, (col_h, col_d, col_a) in _BOOKMAKER_COLS.items():
        odds_map = {}
        for outcome, col in zip(OUTCOMES, [col_h, col_d, col_a]):
            odds_val = _safe_float(odds_row.get(col))
            if odds_val is None or odds_val <= 1.0:
                continue
            odds_map[outcome] = odds_val

        if not odds_map:
            continue

        for outcome, odds_val in odds_map.items():
            ev = compute_ev(model_probs[outcome], odds_val)
            result[f"ev_{outcome}_{bk_name}"] = round(ev, 4)
            result[f"odds_{outcome}_{bk_name}"] = round(odds_val, 3)

            if ev > best_ev:
                best_ev = ev
                best_outcome = outcome
                best_bookmaker = bk_name
                best_odds = odds_val

    # Best opportunity across all bookmakers and outcomes
    if best_ev > -999.0:
        result["best_ev"] = round(best_ev, 4)
        result["best_outcome"] = best_outcome
        result["best_bookmaker"] = best_bookmaker
        result["best_odds"] = round(best_odds, 3)
        result["is_value"] = best_ev > 0.0
        result["kelly_full"] = round(
            kelly_fraction(model_probs[best_outcome], best_odds), 4
        )
        result["kelly_quarter"] = round(
            fractional_kelly(model_probs[best_outcome], best_odds, 0.25), 4
        )
    else:
        result["best_ev"] = None
        result["best_outcome"] = None
        result["best_bookmaker"] = None
        result["best_odds"] = None
        result["is_value"] = False
        result["kelly_full"] = 0.0
        result["kelly_quarter"] = 0.0

    # Max market EV per outcome (what you could actually get shopping around)
    for outcome in OUTCOMES:
        max_col = f"Max{outcome}"
        max_odds = _safe_float(odds_row.get(max_col))
        if max_odds and max_odds > 1.0:
            result[f"ev_{outcome}_max"] = round(
                compute_ev(model_probs[outcome], max_odds), 4
            )
            result[f"odds_{outcome}_max"] = round(max_odds, 3)

    return result


# ──────────────────────────────────────────────
#  Closing Line Value (CLV)
# ──────────────────────────────────────────────


def compute_clv(
    model_probs: Dict[str, float],
    odds_row: pd.Series,
    value_outcome: str,
    bookmaker: str = "pinnacle",
) -> Optional[float]:
    """
    Closing Line Value: did the line move in our direction?

    CLV = (closing_odds / opening_odds) - 1

    Positive CLV = line moved towards us (market confirmed our view)
    Negative CLV = line moved away (we were wrong about the edge)

    Using Pinnacle closing vs opening by default (sharpest bookmaker).
    """
    open_cols = _BOOKMAKER_COLS.get(bookmaker)
    close_cols = _CLOSING_COLS.get(bookmaker)
    if not open_cols or not close_cols:
        return None

    outcome_idx = {"H": 0, "D": 1, "A": 2}
    idx = outcome_idx.get(value_outcome)
    if idx is None:
        return None

    open_odds = _safe_float(odds_row.get(open_cols[idx]))
    close_odds = _safe_float(odds_row.get(close_cols[idx]))

    if not open_odds or not close_odds or open_odds <= 1.0 or close_odds <= 1.0:
        return None

    # If we backed at opening odds and closing odds are lower,
    # that means the market moved our way → positive CLV
    return round((open_odds / close_odds) - 1.0, 4)


def compute_implied_prob(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability (no vig removal)."""
    if decimal_odds <= 1.0:
        return 0.0
    return 1.0 / decimal_odds


# ──────────────────────────────────────────────
#  Profit/Loss simulation
# ──────────────────────────────────────────────


def simulate_flat_stake(
    bets: List[Dict],
    stake: float = 1.0,
) -> Dict[str, Any]:
    """
    Simulate flat-stake betting on a list of value bets.

    Each bet dict must have:
        - "outcome": "H", "D", or "A" (what we bet on)
        - "odds": decimal odds we got
        - "actual_result": "H", "D", or "A" (what happened)

    Returns summary: total bets, wins, losses, P&L, yield, etc.
    """
    if not bets:
        return {
            "n_bets": 0, "wins": 0, "losses": 0,
            "pnl": 0.0, "yield_pct": 0.0, "total_staked": 0.0,
        }

    wins = 0
    pnl = 0.0
    total_staked = len(bets) * stake

    for bet in bets:
        if bet["actual_result"] == bet["outcome"]:
            pnl += (bet["odds"] - 1.0) * stake
            wins += 1
        else:
            pnl -= stake

    losses = len(bets) - wins
    yield_pct = (pnl / total_staked) * 100.0 if total_staked > 0 else 0.0

    return {
        "n_bets": len(bets),
        "wins": wins,
        "losses": losses,
        "hit_rate": round(wins / len(bets) * 100.0, 1),
        "pnl": round(pnl, 2),
        "total_staked": round(total_staked, 2),
        "yield_pct": round(yield_pct, 2),
        "avg_odds": round(np.mean([b["odds"] for b in bets]), 3),
    }


def bootstrap_yield(
    bets: List[Dict],
    n_bootstrap: int = 10000,
    stake: float = 1.0,
) -> Dict[str, Any]:
    """
    Bootstrap confidence interval for yield.

    Resamples bets with replacement n_bootstrap times.
    Returns mean yield, 95% CI, and approximate p-value for yield > 0.
    """
    if len(bets) < 5:
        return {
            "mean_yield": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "p_value": 1.0,
            "n_bets": len(bets),
            "note": "Too few bets for meaningful bootstrap",
        }

    rng = np.random.default_rng(42)
    yields = []

    for _ in range(n_bootstrap):
        sample = rng.choice(bets, size=len(bets), replace=True)
        result = simulate_flat_stake(list(sample), stake=stake)
        yields.append(result["yield_pct"])

    yields_arr = np.array(yields)
    ci_lower = float(np.percentile(yields_arr, 2.5))
    ci_upper = float(np.percentile(yields_arr, 97.5))
    mean_yield = float(np.mean(yields_arr))
    p_value = float(np.mean(yields_arr <= 0.0))  # fraction of samples with yield ≤ 0

    return {
        "mean_yield": round(mean_yield, 2),
        "ci_lower": round(ci_lower, 2),
        "ci_upper": round(ci_upper, 2),
        "p_value": round(p_value, 4),
        "n_bets": len(bets),
        "n_bootstrap": n_bootstrap,
    }


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────


def _safe_float(val: Any) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        f = float(val)
        return f if np.isfinite(f) else None
    except (ValueError, TypeError):
        return None
