"""Thin lookup layer for match odds. Loads parquet or falls back to CSV."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_cache: Dict[str, pd.DataFrame] = {}


def _cache_key(league_id: int, season: str) -> str:
    return f"{league_id}_{season}"


def _load_df(league_id: int, season: str) -> Optional[pd.DataFrame]:
    """Load odds DataFrame from parquet (preferred) or CSV fallback."""
    key = _cache_key(league_id, season)
    if key in _cache:
        return _cache[key]

    # Try parquet first
    parquet_path = _PROJECT_ROOT / "data" / "odds_clean" / f"{league_id}_{season}.parquet"
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
        _cache[key] = df
        return df

    # Fall back to raw CSV via importer
    from odds.importer import LEAGUE_CONFIG, parse_csv

    config = LEAGUE_CONFIG.get(league_id)
    if not config:
        return None

    code = config["code"]
    csv_path = _PROJECT_ROOT / "data" / "football_data" / "odds" / f"{code}_{season}.csv"
    if not csv_path.exists():
        return None

    logger.info("No parquet found, parsing CSV: %s", csv_path)
    df = parse_csv(csv_path, league_id, season)
    _cache[key] = df
    return df


def get_odds_lookup(
    league_id: int = 47,
    season: str = "2526",
    snapshot_type: str = "opening",
) -> Dict[Tuple[str, str], Tuple[float, ...]]:
    """Drop-in replacement for feature_builder._load_market_odds().

    Returns {(home, away): (prob_H, prob_D, prob_A, odds_H, odds_D, odds_A)}

    snapshot_type: "opening" (default, backward compat) or "closing".
    """
    df = _load_df(league_id, season)
    if df is None:
        return {}

    if snapshot_type == "closing":
        prob_cols = ("prob_H_close", "prob_D_close", "prob_A_close")
        odds_cols = ("odds_H_close", "odds_D_close", "odds_A_close")
    else:
        prob_cols = ("prob_H_open", "prob_D_open", "prob_A_open")
        odds_cols = ("odds_H_open", "odds_D_open", "odds_A_open")

    lookup: Dict[Tuple[str, str], Tuple[float, ...]] = {}
    for _, row in df.iterrows():
        # Skip rows with missing odds
        odds_vals = [row.get(c) for c in odds_cols]
        if any(pd.isna(v) for v in odds_vals):
            continue

        prob_vals = [row.get(c) for c in prob_cols]
        if any(pd.isna(v) for v in prob_vals):
            continue

        key = (row["home_team"], row["away_team"])
        lookup[key] = (
            float(prob_vals[0]),
            float(prob_vals[1]),
            float(prob_vals[2]),
            float(odds_vals[0]),
            float(odds_vals[1]),
            float(odds_vals[2]),
        )

    return lookup


def get_match_odds(
    home_team: str,
    away_team: str,
    league_id: int = 47,
    season: str = "2526",
    snapshot_type: str = "opening",
) -> Optional[Dict[str, float]]:
    """Return odds dict for a single match, or None if not found."""
    lookup = get_odds_lookup(league_id, season, snapshot_type)
    entry = lookup.get((home_team, away_team))
    if entry is None:
        return None

    prob_h, prob_d, prob_a, odds_h, odds_d, odds_a = entry
    return {
        "odds_H": odds_h,
        "odds_D": odds_d,
        "odds_A": odds_a,
        "prob_H": prob_h,
        "prob_D": prob_d,
        "prob_A": prob_a,
        "source": "Bet365",
        "snapshot_type": snapshot_type,
    }


def clear_cache() -> None:
    """Clear the module-level cache (useful for testing)."""
    _cache.clear()
