#!/usr/bin/env python3
"""
Benchmark matrix: regularization (C) x feature subsets.

Tests all combinations of C values and feature subsets using walk-forward
evaluation to find the best configuration for the probabilistic model.

Usage:
    python scripts/benchmark_probabilistic.py
    python scripts/benchmark_probabilistic.py --allow-missing-elo
    python scripts/benchmark_probabilistic.py --output-dir output/backtest
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from models.feature_builder import build_feature_dataset, FEATURE_COLS
from models.probabilistic import (
    walk_forward_evaluate,
    load_market_baseline,
)

# ---------------------------------------------------------------------------
# Feature subsets
# ---------------------------------------------------------------------------

FEATURE_SUBSETS: Dict[str, List[str]] = {
    "FULL_V1": FEATURE_COLS,  # 11 features
    "COMPACT_CORE": [
        "xg_diff_last5_delta",
        "form_points_delta",
        "goal_diff_season_delta",
        "position_delta",
        "elo_delta",
        "home_venue_points",
        "away_venue_points",
    ],  # 7 — drops xg components, rest, home_strength
    "NO_XG_COMPONENTS": [
        "xg_diff_last5_delta",
        "form_points_delta",
        "goal_diff_season_delta",
        "position_delta",
        "home_strength_delta",
        "league_rest_days_delta",
        "elo_delta",
        "home_venue_points",
        "away_venue_points",
    ],  # 9 — drops xg_for and xg_against (collinear with xg_diff)
    "STRENGTH_CONTEXT": [
        "xg_diff_last5_delta",
        "form_points_delta",
        "goal_diff_season_delta",
        "position_delta",
        "home_strength_delta",
        "elo_delta",
        "home_venue_points",
        "away_venue_points",
    ],  # 8 — drops rest_days and xg components
    "MINIMAL": [
        "xg_diff_last5_delta",
        "form_points_delta",
        "elo_delta",
        "home_venue_points",
        "away_venue_points",
    ],  # 5 — minimal signal
}

# C values: log-spaced from strong to weak regularization
C_VALUES = [0.01, 0.03, 0.1, 0.3, 1.0, 3.0]


def run_benchmark(
    df,
    market_ll: float | None,
    min_train_rounds: int = 6,
) -> List[Dict]:
    """Run all (subset, C) combinations and collect results."""
    total = len(FEATURE_SUBSETS) * len(C_VALUES)
    results = []
    i = 0

    for subset_name, feature_cols in FEATURE_SUBSETS.items():
        for C in C_VALUES:
            i += 1
            label = f"{subset_name} C={C}"
            print(f"\n[{i}/{total}] {label} ({len(feature_cols)} features)")

            predictions, eval_res = walk_forward_evaluate(
                df,
                min_train_rounds=min_train_rounds,
                C=C,
                feature_cols=feature_cols,
                quiet=True,
            )

            # Top 3 best and worst rounds by log_loss
            rounds_sorted = sorted(eval_res.per_round, key=lambda r: r["log_loss"])
            best_3 = rounds_sorted[:3]
            worst_3 = rounds_sorted[-3:]

            row = {
                "subset": subset_name,
                "n_features": len(feature_cols),
                "C": C,
                "log_loss": round(eval_res.log_loss_val, 4),
                "accuracy": round(eval_res.accuracy, 4),
                "draw_recall": round(eval_res.draw_recall, 4),
                "pct_home": round(eval_res.pct_home_predicted, 4),
                "pct_draw": round(eval_res.pct_draw_predicted, 4),
                "pct_away": round(eval_res.pct_away_predicted, 4),
                "uniform_ll": round(eval_res.uniform_log_loss, 4),
                "marginal_ll": round(eval_res.marginal_log_loss, 4),
                "market_ll": round(market_ll, 4) if market_ll else None,
                "n_predictions": eval_res.total_predictions,
                "best_rounds": [
                    {"round": r["round_number"], "ll": round(r["log_loss"], 4)}
                    for r in best_3
                ],
                "worst_rounds": [
                    {"round": r["round_number"], "ll": round(r["log_loss"], 4)}
                    for r in worst_3
                ],
                "features": feature_cols,
            }
            results.append(row)

            # Progress indicator
            beats_uniform = "OK" if eval_res.log_loss_val < eval_res.uniform_log_loss else "FAIL"
            print(f"  log_loss={eval_res.log_loss_val:.4f} acc={eval_res.accuracy:.1%} "
                  f"draw_recall={eval_res.draw_recall:.1%} [{beats_uniform}]")

    return results


def print_results_table(results: List[Dict]) -> None:
    """Print formatted comparison table."""
    print("\n" + "=" * 100)
    print("BENCHMARK MATRIX: C x Feature Subsets")
    print("=" * 100)

    # Header
    print(f"\n{'Subset':<20} {'#F':>3} {'C':>6} {'LogLoss':>8} {'Acc':>7} "
          f"{'DrawR':>7} {'%H':>6} {'%D':>6} {'%A':>6} {'vs Uni':>8}")
    print("-" * 100)

    # Sort by log_loss ascending
    sorted_results = sorted(results, key=lambda r: r["log_loss"])

    for r in sorted_results:
        delta_uni = r["log_loss"] - r["uniform_ll"]
        marker = " *" if delta_uni < 0 else ""
        print(
            f"{r['subset']:<20} {r['n_features']:>3} {r['C']:>6.2f} "
            f"{r['log_loss']:>8.4f} {r['accuracy']:>6.1%} "
            f"{r['draw_recall']:>6.1%} {r['pct_home']:>5.1%} "
            f"{r['pct_draw']:>5.1%} {r['pct_away']:>5.1%} "
            f"{delta_uni:>+7.4f}{marker}"
        )

    # Best configuration
    best = sorted_results[0]
    print(f"\n{'='*100}")
    print(f"BEST: {best['subset']} C={best['C']} → log_loss={best['log_loss']:.4f} "
          f"(vs uniform {best['uniform_ll']:.4f}, delta {best['log_loss'] - best['uniform_ll']:+.4f})")

    if best["market_ll"]:
        print(f"  vs market {best['market_ll']:.4f} (delta {best['log_loss'] - best['market_ll']:+.4f})")

    # Top 3 / worst 3 rounds for best config
    print(f"\n  Best rounds:  {', '.join(f'R{r['round']}={r['ll']:.4f}' for r in best['best_rounds'])}")
    print(f"  Worst rounds: {', '.join(f'R{r['round']}={r['ll']:.4f}' for r in best['worst_rounds'])}")

    # Degenerate check
    degenerate = [r for r in results if r["pct_draw"] == 0]
    if degenerate:
        print(f"\n  WARNING: {len(degenerate)} configs predict zero draws (degenerate)")

    print("=" * 100)


def save_results(
    results: List[Dict],
    output_dir: Path,
) -> None:
    """Save benchmark results as JSON and CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON (full detail)
    json_path = output_dir / "probabilistic_benchmark.json"
    output = {
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "c_values": C_VALUES,
            "feature_subsets": {k: v for k, v in FEATURE_SUBSETS.items()},
            "n_combinations": len(results),
        },
        "results": sorted(results, key=lambda r: r["log_loss"]),
    }
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nJSON saved: {json_path}")

    # CSV (flat, for quick analysis)
    csv_path = output_dir / "probabilistic_benchmark.csv"
    csv_cols = [
        "subset", "n_features", "C", "log_loss", "accuracy",
        "draw_recall", "pct_home", "pct_draw", "pct_away",
        "uniform_ll", "marginal_ll", "market_ll", "n_predictions",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_cols, extrasaction="ignore")
        writer.writeheader()
        for r in sorted(results, key=lambda r: r["log_loss"]):
            writer.writerow(r)
    print(f"CSV saved: {csv_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark matrix: C x feature subsets for probabilistic model."
    )
    parser.add_argument(
        "--allow-missing-elo",
        action="store_true",
        help="Allow ELO missing rate > 5%%",
    )
    parser.add_argument(
        "--min-rounds",
        type=int,
        default=6,
        help="Minimum training rounds (default: 6, predict from R8)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "output" / "backtest",
        help="Output directory for benchmark results",
    )

    args = parser.parse_args()

    # Build dataset once
    print("Building feature dataset...")
    df = build_feature_dataset(allow_missing_elo=args.allow_missing_elo)

    # Market baseline (computed once)
    market_ll = load_market_baseline(df=df)

    # Run benchmark
    results = run_benchmark(df, market_ll, min_train_rounds=args.min_rounds)

    # Print and save
    print_results_table(results)
    save_results(results, args.output_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
