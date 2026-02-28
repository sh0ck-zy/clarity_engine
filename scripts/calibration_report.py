#!/usr/bin/env python3
"""
Calibration report for the probabilistic motor.

Answers: "When we say 60%, does it actually happen 60% of the time?"

Outputs:
  - Reliability diagram (predicted vs actual frequency per bin)
  - Per-class calibration (H/D/A separately)
  - Expected Calibration Error (ECE)
  - Summary verdict for launch readiness

Usage:
    python scripts/calibration_report.py
    python scripts/calibration_report.py --allow-missing-elo
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from models import config as model_config
from models.feature_builder import build_feature_dataset
from models.probabilistic import walk_forward_evaluate


def compute_calibration(
    predictions: List[Dict],
    n_bins: int = 10,
) -> Dict:
    """
    Compute calibration metrics from walk-forward predictions.

    Returns dict with:
      - overall: reliability diagram bins, ECE, Brier score
      - per_class: calibration per result type (H/D/A)
    """
    # Collect all (predicted_prob, actual_binary) pairs per class
    classes = ["H", "D", "A"]
    prob_keys = {"H": "prob_H", "D": "prob_D", "A": "prob_A"}

    # Overall calibration (pooled across all classes)
    all_predicted = []
    all_actual = []

    per_class_data = {c: {"predicted": [], "actual": []} for c in classes}

    for pred in predictions:
        actual = pred["actual_result"]
        for cls in classes:
            prob = pred[prob_keys[cls]]
            is_correct = 1 if actual == cls else 0

            all_predicted.append(prob)
            all_actual.append(is_correct)

            per_class_data[cls]["predicted"].append(prob)
            per_class_data[cls]["actual"].append(is_correct)

    # Compute binned calibration
    overall_bins = _bin_calibration(all_predicted, all_actual, n_bins)
    overall_ece = _compute_ece(overall_bins)

    # Per-class calibration
    per_class = {}
    for cls in classes:
        bins = _bin_calibration(
            per_class_data[cls]["predicted"],
            per_class_data[cls]["actual"],
            n_bins,
        )
        per_class[cls] = {
            "bins": bins,
            "ece": _compute_ece(bins),
        }

    # Brier score (mean squared error of probability estimates)
    all_predicted_arr = np.array(all_predicted)
    all_actual_arr = np.array(all_actual)
    brier = float(np.mean((all_predicted_arr - all_actual_arr) ** 2))

    return {
        "overall": {
            "bins": overall_bins,
            "ece": overall_ece,
            "brier_score": brier,
            "n_predictions": len(predictions),
            "n_probability_pairs": len(all_predicted),
        },
        "per_class": per_class,
    }


def _bin_calibration(
    predicted: List[float],
    actual: List[int],
    n_bins: int,
) -> List[Dict]:
    """Bin predictions and compute mean predicted vs actual frequency."""
    predicted_arr = np.array(predicted)
    actual_arr = np.array(actual)

    bins = []
    bin_edges = np.linspace(0, 1, n_bins + 1)

    for i in range(n_bins):
        lo = bin_edges[i]
        hi = bin_edges[i + 1]

        if i == n_bins - 1:
            mask = (predicted_arr >= lo) & (predicted_arr <= hi)
        else:
            mask = (predicted_arr >= lo) & (predicted_arr < hi)

        count = int(mask.sum())
        if count == 0:
            bins.append({
                "bin": f"{lo:.0%}-{hi:.0%}",
                "mean_predicted": None,
                "mean_actual": None,
                "count": 0,
                "gap": None,
            })
            continue

        mean_pred = float(predicted_arr[mask].mean())
        mean_actual = float(actual_arr[mask].mean())
        gap = abs(mean_pred - mean_actual)

        bins.append({
            "bin": f"{lo:.0%}-{hi:.0%}",
            "mean_predicted": round(mean_pred, 4),
            "mean_actual": round(mean_actual, 4),
            "count": count,
            "gap": round(gap, 4),
        })

    return bins


def _compute_ece(bins: List[Dict]) -> float:
    """Compute Expected Calibration Error (weighted average of bin gaps)."""
    total_count = sum(b["count"] for b in bins)
    if total_count == 0:
        return 0.0

    ece = 0.0
    for b in bins:
        if b["count"] > 0 and b["gap"] is not None:
            ece += (b["count"] / total_count) * b["gap"]

    return round(ece, 4)


def print_calibration_report(cal: Dict) -> None:
    """Print formatted calibration report."""
    overall = cal["overall"]

    print("\n" + "=" * 70)
    print(f"CALIBRATION REPORT — Model {model_config.MODEL_VERSION}")
    print("=" * 70)

    print(f"\nPredictions: {overall['n_predictions']} matches")
    print(f"Probability pairs: {overall['n_probability_pairs']} (3 per match)")

    # Overall reliability diagram
    print(f"\n{'Bin':<12} {'Predicted':>10} {'Actual':>10} {'Gap':>8} {'Count':>7}")
    print("-" * 50)

    for b in overall["bins"]:
        if b["count"] == 0:
            print(f"{b['bin']:<12} {'—':>10} {'—':>10} {'—':>8} {b['count']:>7}")
        else:
            ok = "✓" if b["gap"] < 0.05 else "✗"
            print(
                f"{b['bin']:<12} {b['mean_predicted']:>9.1%} "
                f"{b['mean_actual']:>9.1%} {b['gap']:>7.3f} {b['count']:>6} {ok}"
            )

    print(f"\nExpected Calibration Error (ECE): {overall['ece']:.4f}")
    print(f"Brier Score: {overall['brier_score']:.4f}")

    ece_verdict = "PASS ✓" if overall["ece"] < 0.05 else "FAIL ✗"
    print(f"ECE < 0.05: {ece_verdict}")

    # Per-class calibration
    print(f"\n{'─' * 70}")
    print("PER-CLASS CALIBRATION")
    print(f"{'─' * 70}")

    for cls in ["H", "D", "A"]:
        cls_data = cal["per_class"][cls]
        cls_name = {"H": "Home Win", "D": "Draw", "A": "Away Win"}[cls]
        ece = cls_data["ece"]
        verdict = "✓" if ece < 0.05 else "✗"
        print(f"\n  {cls_name}: ECE = {ece:.4f} {verdict}")

        # Show non-empty bins
        for b in cls_data["bins"]:
            if b["count"] > 0 and b["mean_predicted"] is not None:
                print(
                    f"    {b['bin']:<12} pred={b['mean_predicted']:.1%} "
                    f"actual={b['mean_actual']:.1%} gap={b['gap']:.3f} n={b['count']}"
                )

    # Launch readiness verdict
    print(f"\n{'=' * 70}")
    all_ece = [cal["per_class"][c]["ece"] for c in ["H", "D", "A"]]
    max_ece = max(all_ece)
    if max_ece < 0.05:
        print("LAUNCH VERDICT: CALIBRATED ✓ — All per-class ECE < 0.05")
    elif max_ece < 0.10:
        print(f"LAUNCH VERDICT: ACCEPTABLE — Max per-class ECE = {max_ece:.4f} (< 0.10)")
    else:
        print(f"LAUNCH VERDICT: NEEDS WORK — Max per-class ECE = {max_ece:.4f}")
    print("=" * 70)


def save_calibration_report(cal: Dict, output_dir: Path) -> None:
    """Save calibration report as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"calibration_{model_config.MODEL_VERSION}.json"

    output = {
        "model_version": model_config.MODEL_VERSION,
        "created_at": datetime.now().isoformat(),
        "config": {
            "C": model_config.C,
            "class_weight": model_config.MODEL_SPEC.get("class_weight"),
            "features": model_config.FEATURE_COLS,
        },
        **cal,
    }

    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nCalibration report saved: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibration report for probabilistic model."
    )
    parser.add_argument(
        "--allow-missing-elo",
        action="store_true",
        help="Allow ELO missing rate > 5%%",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "output" / "calibration",
        help="Output directory",
    )

    args = parser.parse_args()

    # Build dataset
    print("Building feature dataset...")
    df = build_feature_dataset(allow_missing_elo=args.allow_missing_elo)

    # Run walk-forward with frozen config
    print(f"\nRunning walk-forward with {model_config.MODEL_VERSION} config...")
    predictions, eval_res = walk_forward_evaluate(
        df,
        min_train_rounds=model_config.MIN_TRAIN_ROUNDS,
        C=model_config.C,
        class_weight=model_config.MODEL_SPEC.get("class_weight"),
        feature_cols=model_config.FEATURE_COLS,
        quiet=True,
    )

    print(f"  {len(predictions)} predictions (R{predictions[0]['round_number']}-R{predictions[-1]['round_number']})")
    print(f"  Log loss: {eval_res.log_loss_val:.4f}, Accuracy: {eval_res.accuracy:.1%}")
    print(f"  Draw recall: {eval_res.draw_recall:.1%}")

    # Compute calibration
    cal = compute_calibration(predictions)

    # Print and save
    print_calibration_report(cal)
    save_calibration_report(cal, args.output_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
