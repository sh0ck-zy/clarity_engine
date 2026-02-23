#!/usr/bin/env python3
"""
Run probabilistic model walk-forward evaluation.

Usage:
    python scripts/run_probabilistic.py                          # walk-forward R8-R26
    python scripts/run_probabilistic.py --min-rounds 7           # start earlier
    python scripts/run_probabilistic.py --save-dataset           # save Parquet + metadata
    python scripts/run_probabilistic.py --allow-missing-elo      # if ELO coverage < 95%
    python scripts/run_probabilistic.py --debug-match 4012345    # sanity check a match
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from models.feature_builder import (
    build_feature_dataset,
    compute_dataset_hash,
    save_dataset_artifact,
    FEATURE_COLS,
)
from models.probabilistic import (
    walk_forward_evaluate,
    load_market_baseline,
    ProbabilisticEvalResults,
)


def print_results(
    results: ProbabilisticEvalResults,
    market_ll: float | None,
) -> None:
    """Print formatted evaluation results."""
    print("\n" + "=" * 70)
    print("WALK-FORWARD EVALUATION: Probabilistic Model v1")
    print("=" * 70)

    print(f"\nPredictions: {results.total_predictions} matches (R{results.predict_rounds[0]}-R{results.predict_rounds[-1]})")

    print(f"\n{'Metric':<30} {'Model':>10} {'Uniform':>10} {'Marginal':>10} {'Market':>10}")
    print("-" * 70)
    print(f"{'Log Loss':<30} {results.log_loss_val:>10.4f} {results.uniform_log_loss:>10.4f} {results.marginal_log_loss:>10.4f} {(f'{market_ll:.4f}' if market_ll else 'N/A'):>10}")
    print(f"{'Accuracy':<30} {results.accuracy:>10.1%} {'33.3%':>10} {'~':>10} {'~':>10}")

    print(f"\nBy result type:")
    print(f"  Home wins precision:  {results.home_win_accuracy:.1%}")
    print(f"  Draw precision:       {results.draw_accuracy:.1%}")
    print(f"  Away wins precision:  {results.away_win_accuracy:.1%}")
    print(f"  Draw recall:          {results.draw_recall:.1%}")

    print(f"\nPredicted distribution:")
    print(f"  Home: {results.pct_home_predicted:.1%}  Draw: {results.pct_draw_predicted:.1%}  Away: {results.pct_away_predicted:.1%}")

    # Distribution guard
    if results.pct_home_predicted == 0 or results.pct_draw_predicted == 0 or results.pct_away_predicted == 0:
        print("\n  WARNING: Degenerate distribution! One class is never predicted.")

    print(f"\nPer-round breakdown:")
    print(f"  {'Round':>5} {'N':>4} {'Correct':>8} {'Accuracy':>10} {'LogLoss':>10} {'TrainN':>8}")
    print(f"  {'-'*50}")
    for r in results.per_round:
        print(
            f"  R{r['round_number']:>3} {r['n_matches']:>4} "
            f"{r['correct']:>8} {r['accuracy']:>10.1%} "
            f"{r['log_loss']:>10.4f} {r['train_size']:>8}"
        )

    print("\n" + "=" * 70)


def save_results(
    predictions: list[dict],
    results: ProbabilisticEvalResults,
    market_ll: float | None,
    dataset_hash: str,
    output_dir: Path,
) -> None:
    """Save evaluation results as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "probabilistic_evaluation.json"

    output = {
        "metadata": {
            "feature_version": "v1",
            "model": "logistic_regression_multinomial",
            "min_train_rounds": results.predict_rounds[0] - 2 if results.predict_rounds else 6,
            "predict_rounds": results.predict_rounds,
            "total_predictions": results.total_predictions,
            "dataset_hash": dataset_hash,
            "created_at": datetime.now().isoformat(),
        },
        "baselines": {
            "uniform_log_loss": round(results.uniform_log_loss, 4),
            "marginal_log_loss": round(results.marginal_log_loss, 4),
            "market_log_loss": round(market_ll, 4) if market_ll else None,
        },
        "summary": {
            "log_loss": round(results.log_loss_val, 4),
            "accuracy": round(results.accuracy, 4),
            "draw_recall": round(results.draw_recall, 4),
            "pct_home_predicted": round(results.pct_home_predicted, 4),
            "pct_draw_predicted": round(results.pct_draw_predicted, 4),
            "pct_away_predicted": round(results.pct_away_predicted, 4),
        },
        "per_round": [
            {k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()}
            for r in results.per_round
        ],
        "predictions": predictions,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nResults saved: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run probabilistic model walk-forward evaluation."
    )
    parser.add_argument(
        "--min-rounds",
        type=int,
        default=6,
        help="Minimum training rounds before first prediction (default: 6, predicts from R8)",
    )
    parser.add_argument(
        "--save-dataset",
        action="store_true",
        help="Save feature dataset as Parquet + metadata JSON",
    )
    parser.add_argument(
        "--allow-missing-elo",
        action="store_true",
        help="Allow ELO missing rate > 5%%",
    )
    parser.add_argument(
        "--debug-match",
        type=str,
        default=None,
        help="Print detailed debug info for a specific match ID",
    )
    parser.add_argument(
        "--C",
        type=float,
        default=1.0,
        help="Regularization parameter for LogisticRegression (default: 1.0)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "output" / "backtest",
        help="Output directory for evaluation JSON",
    )

    args = parser.parse_args()

    # Build dataset
    print("Building feature dataset...")
    df = build_feature_dataset(allow_missing_elo=args.allow_missing_elo)

    dataset_hash = compute_dataset_hash(df)
    print(f"Dataset hash: {dataset_hash}")

    if args.save_dataset:
        save_dataset_artifact(df)

    # Run walk-forward evaluation
    predictions, results = walk_forward_evaluate(
        df,
        min_train_rounds=args.min_rounds,
        C=args.C,
        debug_match_id=args.debug_match,
    )

    # Market baseline
    market_ll = load_market_baseline(df=df)
    if market_ll is not None:
        results.market_log_loss = market_ll

    # Print results
    print_results(results, market_ll)

    # Save results
    save_results(predictions, results, market_ll, dataset_hash, args.output_dir)

    # Final guards
    if results.pct_draw_predicted == 0:
        print("\nFAIL: No draws predicted. Model is degenerate.")
        return 1

    if results.log_loss_val >= results.uniform_log_loss:
        print(f"\nWARNING: Model log_loss ({results.log_loss_val:.4f}) >= uniform ({results.uniform_log_loss:.4f})")
        print("Model is not learning better than random.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
