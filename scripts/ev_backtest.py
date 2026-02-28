#!/usr/bin/env python3
"""
EV Backtest: Answer "Do we have edge?"

Runs walk-forward predictions with frozen model config,
joins each prediction with bookmaker odds from football-data.co.uk CSV,
and computes:
  1. EV per match per outcome per bookmaker
  2. Flat-stake P&L at various EV thresholds
  3. Closing Line Value (CLV)
  4. Subset analysis (by outcome, confidence, round)
  5. Bootstrap confidence intervals

Usage:
    python scripts/ev_backtest.py
    python scripts/ev_backtest.py --output output/ev/ev_backtest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_PATH = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from models import config as model_config
from models.ev_calculator import (
    OUTCOMES,
    _BOOKMAKER_COLS,
    bootstrap_yield,
    compute_clv,
    compute_ev,
    compute_match_ev,
    fractional_kelly,
    simulate_flat_stake,
)
from models.feature_builder import build_feature_dataset
from models.probabilistic import walk_forward_evaluate

# ──────────────────────────────────────────────
#  Odds loading
# ──────────────────────────────────────────────

# Football-data.co.uk -> FotMob team name mapping (same as feature_builder)
_CSV_TO_FOTMOB = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Bournemouth": "AFC Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton & Hove Albion",
    "Burnley": "Burnley",
    "Chelsea": "Chelsea",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Leeds": "Leeds United",
    "Leicester": "Leicester City",
    "Liverpool": "Liverpool",
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Newcastle": "Newcastle United",
    "Nott'm Forest": "Nottingham Forest",
    "Southampton": "Southampton",
    "Sunderland": "Sunderland",
    "Spurs": "Tottenham Hotspur",
    "Tottenham": "Tottenham Hotspur",
    "West Ham": "West Ham United",
    "Wolves": "Wolverhampton Wanderers",
    "Ipswich": "Ipswich Town",
    "Luton": "Luton Town",
}


def load_odds_dataframe(csv_path: Optional[Path] = None) -> pd.DataFrame:
    """Load full odds CSV with all bookmaker columns preserved."""
    if csv_path is None:
        csv_path = _PROJECT_ROOT / "data" / "football_data" / "odds" / "E0_2526.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Odds CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)

    # Map team names to FotMob format for joining
    df["home_fotmob"] = df["HomeTeam"].map(
        lambda x: _CSV_TO_FOTMOB.get(str(x), str(x))
    )
    df["away_fotmob"] = df["AwayTeam"].map(
        lambda x: _CSV_TO_FOTMOB.get(str(x), str(x))
    )

    return df


def join_predictions_with_odds(
    predictions: List[Dict],
    odds_df: pd.DataFrame,
) -> List[Dict]:
    """
    Join walk-forward predictions with odds data.

    Match key: (home_team, away_team) using FotMob names.
    Returns enriched predictions with odds and EV data.
    """
    # Build odds lookup: (home, away) -> row index
    odds_lookup: Dict[tuple, int] = {}
    for idx, row in odds_df.iterrows():
        key = (row["home_fotmob"], row["away_fotmob"])
        odds_lookup[key] = idx

    enriched = []
    matched = 0
    unmatched = 0

    for pred in predictions:
        key = (pred["home_team"], pred["away_team"])
        odds_idx = odds_lookup.get(key)

        if odds_idx is None:
            unmatched += 1
            continue

        matched += 1
        odds_row = odds_df.iloc[odds_idx]

        model_probs = {
            "H": pred["prob_H"],
            "D": pred["prob_D"],
            "A": pred["prob_A"],
        }

        # Compute EV across all bookmakers
        ev_data = compute_match_ev(model_probs, odds_row)

        # Compute CLV for the best value outcome
        clv = None
        if ev_data.get("best_outcome"):
            clv = compute_clv(
                model_probs, odds_row, ev_data["best_outcome"], bookmaker="pinnacle"
            )
            # Also try B365 if Pinnacle CLV unavailable
            if clv is None:
                clv = compute_clv(
                    model_probs, odds_row, ev_data["best_outcome"], bookmaker="b365"
                )

        # Merge prediction + EV data
        enriched_pred = {**pred, **ev_data, "clv": clv}

        # Add raw odds for the actual result (for P&L computation)
        actual = pred.get("actual_result")
        if actual and actual in OUTCOMES:
            max_col = f"Max{actual}"
            b365_col = f"B365{actual}"
            enriched_pred["actual_odds_max"] = _safe_float(odds_row.get(max_col))
            enriched_pred["actual_odds_b365"] = _safe_float(odds_row.get(b365_col))

        enriched.append(enriched_pred)

    print(f"Odds matching: {matched} matched, {unmatched} unmatched")
    return enriched


# ──────────────────────────────────────────────
#  P&L Analysis
# ──────────────────────────────────────────────


def analyze_ev_thresholds(
    predictions: List[Dict],
    thresholds: List[float] = [0.0, 0.03, 0.05, 0.10, 0.15],
) -> List[Dict]:
    """
    Flat-stake P&L at various EV thresholds.

    For each threshold: filter to bets with best_ev > threshold,
    simulate flat 1u stake on the best_outcome at max odds.
    """
    results = []

    for threshold in thresholds:
        bets = []
        for pred in predictions:
            if pred.get("best_ev") is None:
                continue
            if pred["best_ev"] <= threshold:
                continue
            if pred.get("actual_result") is None:
                continue

            # Use max market odds for the value outcome
            outcome = pred["best_outcome"]
            odds_key = f"odds_{outcome}_max"
            odds = pred.get(odds_key) or pred.get("best_odds", 0)
            if not odds or odds <= 1.0:
                continue

            bets.append({
                "outcome": outcome,
                "odds": odds,
                "actual_result": pred["actual_result"],
                "home_team": pred["home_team"],
                "away_team": pred["away_team"],
                "model_prob": pred[f"prob_{outcome}"],
                "ev": pred["best_ev"],
            })

        pnl = simulate_flat_stake(bets)
        pnl["ev_threshold"] = threshold

        # Add CLV stats for this subset
        clvs = [p["clv"] for p in predictions
                 if p.get("best_ev") is not None
                 and p["best_ev"] > threshold
                 and p.get("clv") is not None]
        if clvs:
            pnl["avg_clv"] = round(np.mean(clvs) * 100, 2)
            pnl["pct_positive_clv"] = round(
                sum(1 for c in clvs if c > 0) / len(clvs) * 100, 1
            )
        else:
            pnl["avg_clv"] = None
            pnl["pct_positive_clv"] = None

        # Bootstrap CI (only if enough bets)
        if len(bets) >= 10:
            bootstrap = bootstrap_yield(bets)
            pnl["bootstrap_ci_lower"] = bootstrap["ci_lower"]
            pnl["bootstrap_ci_upper"] = bootstrap["ci_upper"]
            pnl["bootstrap_p_value"] = bootstrap["p_value"]
        else:
            pnl["bootstrap_ci_lower"] = None
            pnl["bootstrap_ci_upper"] = None
            pnl["bootstrap_p_value"] = None

        results.append(pnl)

    return results


def analyze_by_outcome(predictions: List[Dict]) -> Dict[str, Dict]:
    """P&L sliced by value bet outcome type (H/D/A)."""
    results = {}

    for outcome in OUTCOMES:
        bets = []
        for pred in predictions:
            if pred.get("best_ev") is None or pred["best_ev"] <= 0:
                continue
            if pred["best_outcome"] != outcome:
                continue
            if pred.get("actual_result") is None:
                continue

            odds_key = f"odds_{outcome}_max"
            odds = pred.get(odds_key) or pred.get("best_odds", 0)
            if not odds or odds <= 1.0:
                continue

            bets.append({
                "outcome": outcome,
                "odds": odds,
                "actual_result": pred["actual_result"],
            })

        pnl = simulate_flat_stake(bets)
        label = {"H": "Home Win", "D": "Draw", "A": "Away Win"}[outcome]
        results[label] = pnl

    return results


def analyze_by_confidence(predictions: List[Dict]) -> Dict[str, Dict]:
    """P&L sliced by prediction confidence (high/medium/low)."""
    results = {}

    for level in ["high", "medium", "low"]:
        bets = []
        for pred in predictions:
            if pred.get("best_ev") is None or pred["best_ev"] <= 0:
                continue
            if pred.get("actual_result") is None:
                continue

            # Classify confidence (same logic as probabilistic.py)
            entropy = pred.get("entropy_norm", 1.0)
            margin = pred.get("margin_top2", 0.0)
            if entropy < 0.85 and margin > 0.15:
                conf = "high"
            elif entropy < 0.95 and margin > 0.08:
                conf = "medium"
            else:
                conf = "low"

            if conf != level:
                continue

            outcome = pred["best_outcome"]
            odds_key = f"odds_{outcome}_max"
            odds = pred.get(odds_key) or pred.get("best_odds", 0)
            if not odds or odds <= 1.0:
                continue

            bets.append({
                "outcome": outcome,
                "odds": odds,
                "actual_result": pred["actual_result"],
            })

        results[level] = simulate_flat_stake(bets)

    return results


def analyze_by_round(predictions: List[Dict]) -> List[Dict]:
    """P&L per round (time series of edge)."""
    rounds = sorted(set(p["round_number"] for p in predictions))
    results = []

    for rnd in rounds:
        bets = []
        for pred in predictions:
            if pred["round_number"] != rnd:
                continue
            if pred.get("best_ev") is None or pred["best_ev"] <= 0:
                continue
            if pred.get("actual_result") is None:
                continue

            outcome = pred["best_outcome"]
            odds_key = f"odds_{outcome}_max"
            odds = pred.get(odds_key) or pred.get("best_odds", 0)
            if not odds or odds <= 1.0:
                continue

            bets.append({
                "outcome": outcome,
                "odds": odds,
                "actual_result": pred["actual_result"],
            })

        pnl = simulate_flat_stake(bets)
        pnl["round_number"] = rnd
        results.append(pnl)

    return results


# ──────────────────────────────────────────────
#  Reporting
# ──────────────────────────────────────────────


def print_report(
    predictions: List[Dict],
    threshold_results: List[Dict],
    outcome_results: Dict[str, Dict],
    confidence_results: Dict[str, Dict],
    round_results: List[Dict],
) -> None:
    """Print formatted EV backtest report."""
    total = len(predictions)
    with_ev = sum(1 for p in predictions if p.get("best_ev") is not None)
    value_bets = sum(1 for p in predictions if p.get("is_value"))

    print("\n" + "=" * 72)
    print("  EV BACKTEST REPORT")
    print(f"  Model: {model_config.MODEL_VERSION} | {total} predictions | {value_bets} value bets")
    print("=" * 72)

    # ── EV Threshold Table ──
    print("\n┌─── P&L BY EV THRESHOLD (flat 1u stake, max market odds) ───┐")
    print(f"{'Threshold':>10} {'Bets':>6} {'Hit%':>7} {'Yield':>8} {'P&L':>8} {'Avg CLV':>9} {'95% CI':>18}")
    print("─" * 72)
    for r in threshold_results:
        threshold_str = f"> {r['ev_threshold']*100:.0f}%"
        ci_str = ""
        if r.get("bootstrap_ci_lower") is not None:
            ci_str = f"[{r['bootstrap_ci_lower']:+.1f}%, {r['bootstrap_ci_upper']:+.1f}%]"
        clv_str = f"{r['avg_clv']:+.1f}%" if r.get("avg_clv") is not None else "n/a"
        hit_str = f"{r['hit_rate']:.1f}%" if r["n_bets"] > 0 else "n/a"
        yield_str = f"{r['yield_pct']:+.1f}%" if r["n_bets"] > 0 else "n/a"
        pnl_str = f"{r['pnl']:+.2f}u" if r["n_bets"] > 0 else "n/a"

        print(f"{threshold_str:>10} {r['n_bets']:>6} {hit_str:>7} {yield_str:>8} {pnl_str:>8} {clv_str:>9} {ci_str:>18}")
    print()

    # ── By Outcome ──
    print("┌─── P&L BY OUTCOME TYPE (EV > 0 only) ───┐")
    print(f"{'Outcome':>12} {'Bets':>6} {'Hit%':>7} {'Yield':>8} {'P&L':>8} {'Avg Odds':>10}")
    print("─" * 55)
    for label, r in outcome_results.items():
        if r["n_bets"] == 0:
            print(f"{label:>12} {0:>6}     —")
            continue
        print(
            f"{label:>12} {r['n_bets']:>6} {r['hit_rate']:.1f}% "
            f"{r['yield_pct']:+8.1f}% {r['pnl']:+8.2f}u {r['avg_odds']:>10.3f}"
        )
    print()

    # ── By Confidence ──
    print("┌─── P&L BY CONFIDENCE LEVEL (EV > 0 only) ───┐")
    print(f"{'Confidence':>12} {'Bets':>6} {'Hit%':>7} {'Yield':>8} {'P&L':>8}")
    print("─" * 45)
    for level in ["high", "medium", "low"]:
        r = confidence_results.get(level, {"n_bets": 0})
        if r["n_bets"] == 0:
            print(f"{level:>12} {0:>6}     —")
            continue
        print(
            f"{level:>12} {r['n_bets']:>6} {r['hit_rate']:.1f}% "
            f"{r['yield_pct']:+8.1f}% {r['pnl']:+8.2f}u"
        )
    print()

    # ── By Round (cumulative P&L) ──
    print("┌─── CUMULATIVE P&L BY ROUND ───┐")
    cum_pnl = 0.0
    cum_bets = 0
    for r in round_results:
        cum_pnl += r["pnl"]
        cum_bets += r["n_bets"]
        bar = "█" * max(0, int(cum_pnl + 10))  # simple visual
        if r["n_bets"] > 0:
            print(f"  R{r['round_number']:>2}  bets={r['n_bets']:>2}  round={r['pnl']:+.2f}u  cum={cum_pnl:+.2f}u  {bar}")
    print(f"\n  Total: {cum_bets} bets, {cum_pnl:+.2f}u P&L")
    print()

    # ── CLV Summary ──
    clvs = [p["clv"] for p in predictions if p.get("clv") is not None and p.get("is_value")]
    if clvs:
        print("┌─── CLOSING LINE VALUE (value bets only) ───┐")
        print(f"  Avg CLV:          {np.mean(clvs)*100:+.2f}%")
        print(f"  Positive CLV:     {sum(1 for c in clvs if c > 0)}/{len(clvs)} ({sum(1 for c in clvs if c > 0)/len(clvs)*100:.0f}%)")
        print(f"  Median CLV:       {np.median(clvs)*100:+.2f}%")
        print()
        print("  CLV > 0 consistently = REAL EDGE (regardless of short-term P&L)")
        print("  CLV < 0 consistently = NO EDGE (short-term profit is luck)")
        print()

    # ── Verdict ──
    print("=" * 72)
    print("  VERDICT")
    print("=" * 72)

    # Simple heuristics for verdict
    ev0 = next((r for r in threshold_results if r["ev_threshold"] == 0.0), None)
    ev5 = next((r for r in threshold_results if r["ev_threshold"] == 0.05), None)

    if ev0 and ev0["n_bets"] > 0:
        if ev0["yield_pct"] > 0 and clvs and np.mean(clvs) > 0:
            print("  ✓ PROMISING — Positive yield AND positive CLV.")
            print("    But sample is small. Need 500+ bets to confirm.")
        elif ev0["yield_pct"] > 0:
            print("  ⚠ MAYBE — Positive yield but CLV data insufficient.")
            print("    Could be variance. Need more data (more leagues).")
        elif clvs and np.mean(clvs) > 0:
            print("  ⚠ INTERESTING — Negative P&L but positive CLV.")
            print("    Edge may exist but variance hiding it. Need more bets.")
        else:
            print("  ✗ NO EDGE FOUND — Negative yield and no CLV signal.")
            print("    Model needs improvement or more data before betting.")
    else:
        print("  ✗ NO VALUE BETS — Model never disagrees enough with market.")
        print("    Need better features or different markets (softer leagues).")

    print()
    print(f"  Next step: Add Portuguese + Brazilian leagues for 3-5x more data")
    print("=" * 72)


# ──────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return f if np.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="EV Backtest")
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="output/ev/ev_backtest.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--odds-csv",
        type=str,
        default=None,
        help="Path to odds CSV (default: data/football_data/odds/E0_2526.csv)",
    )
    args = parser.parse_args()

    print("=" * 72)
    print("  EV BACKTEST — Do we have edge?")
    print(f"  Model: {model_config.MODEL_VERSION}")
    print("=" * 72)

    # Step 1: Load features and run walk-forward
    print("\n[1/4] Running walk-forward predictions...")
    df = build_feature_dataset()
    feature_cols = model_config.FEATURE_COLS
    C = model_config.C
    class_weight = model_config.MODEL_SPEC.get("class_weight")

    predictions, eval_results = walk_forward_evaluate(
        df,
        min_train_rounds=6,
        C=C,
        class_weight=class_weight,
        feature_cols=feature_cols,
        quiet=True,
    )
    print(f"  {len(predictions)} predictions (R{predictions[0]['round_number']}-R{predictions[-1]['round_number']})")
    print(f"  Log loss: {eval_results.log_loss_val:.4f} | Accuracy: {eval_results.accuracy:.1%}")

    # Step 2: Load odds and join
    print("\n[2/4] Loading odds and joining with predictions...")
    odds_csv = Path(args.odds_csv) if args.odds_csv else None
    odds_df = load_odds_dataframe(odds_csv)
    enriched = join_predictions_with_odds(predictions, odds_df)
    print(f"  {len(enriched)} predictions with odds data")

    # Step 3: Compute P&L at various thresholds
    print("\n[3/4] Computing EV analysis...")
    threshold_results = analyze_ev_thresholds(enriched)
    outcome_results = analyze_by_outcome(enriched)
    confidence_results = analyze_by_confidence(enriched)
    round_results = analyze_by_round(enriched)

    # Step 4: Print report
    print("\n[4/4] Generating report...")
    print_report(enriched, threshold_results, outcome_results, confidence_results, round_results)

    # Save JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "meta": {
            "model_version": model_config.MODEL_VERSION,
            "n_predictions": len(predictions),
            "n_matched_odds": len(enriched),
            "generated_at": datetime.now().isoformat(),
        },
        "ev_thresholds": threshold_results,
        "by_outcome": outcome_results,
        "by_confidence": confidence_results,
        "by_round": round_results,
        "predictions": enriched,
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
