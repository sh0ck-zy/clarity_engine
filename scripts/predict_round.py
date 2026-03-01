#!/usr/bin/env python3
"""
Predict a Premier League round using the frozen probabilistic motor v1.1.

Usage:
    python scripts/predict_round.py 27                    # predict R27
    python scripts/predict_round.py 12 --backtest         # backtest R12 (show actual vs predicted)
    python scripts/predict_round.py 8 26 --walk-forward   # walk-forward R8-R26, save all reports
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from models import config as model_config
from models.feature_builder import build_feature_dataset
from models.probabilistic import predict_round, walk_forward_evaluate, build_match_report, _compute_drivers
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import numpy as np


def print_report(report: dict, show_actual: bool = False) -> None:
    """Print a single match report."""
    f = report["fixture"]
    p = report["probabilities"]
    pred = report["prediction"]

    result_str = ""
    if show_actual and report.get("actual_result"):
        correct = "OK" if report.get("result_correct") else "MISS"
        result_str = f" | actual={report['actual_result']} [{correct}]"

    print(f"  {f['home_team']:25s} vs {f['away_team']:25s}")
    print(f"    H={p['home_win']:.1%}  D={p['draw']:.1%}  A={p['away_win']:.1%}")
    print(f"    pick={pred['predicted_result']}  conf={pred['confidence']}  "
          f"margin={pred['margin_top2']:.3f}  entropy={pred['entropy_norm']:.3f}"
          f"{result_str}")

    if report.get("risk_flags"):
        print(f"    flags: {', '.join(report['risk_flags'])}")

    drivers = report.get("drivers", [])
    if drivers:
        top = drivers[:3]
        parts = [f"{d['feature']}={d['value']:+.2f}({d['direction']})" for d in top]
        print(f"    drivers: {', '.join(parts)}")


def save_output(
    reports: List[dict],
    output_dir: Path,
    label: str,
) -> None:
    """Save reports as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"predictions_{label}.json"

    output = {
        "metadata": {
            "model_version": model_config.MODEL_VERSION,
            "C": model_config.C,
            "feature_subset": model_config.FEATURE_COLS,
            "n_features": len(model_config.FEATURE_COLS),
            "created_at": datetime.now().isoformat(),
            "n_predictions": len(reports),
        },
        "reports": reports,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved: {output_path}")


def run_walk_forward_reports(
    df,
    start_round: int,
    end_round: int,
    output_dir: Path,
) -> List[dict]:
    """Run walk-forward and produce match reports with drivers for each prediction."""
    feature_cols = model_config.FEATURE_COLS
    C = model_config.C

    all_rounds = sorted(df["round_number"].unique())
    target_rounds = [r for r in all_rounds if start_round <= r <= end_round]

    all_reports = []
    for target_round in target_rounds:
        reports = predict_round(target_round, df=df)
        all_reports.extend(reports)

        n_correct = sum(1 for r in reports if r.get("result_correct"))
        print(f"  R{target_round}: {len(reports)} matches, {n_correct}/{len(reports)} correct")

    return all_reports


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Predict round using probabilistic motor {model_config.MODEL_VERSION}"
    )
    parser.add_argument(
        "round",
        type=int,
        help="Round number to predict (or start round with --walk-forward)",
    )
    parser.add_argument(
        "end_round",
        type=int,
        nargs="?",
        default=None,
        help="End round (only with --walk-forward)",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Show actual results alongside predictions",
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run walk-forward from round to end_round, save all reports",
    )
    parser.add_argument(
        "--allow-missing-elo",
        action="store_true",
        help="Allow ELO missing rate > 5%%",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "output" / "predictions",
        help="Output directory",
    )

    args = parser.parse_args()

    # Build dataset
    print(f"Model: {model_config.MODEL_VERSION} | C={model_config.C} | "
          f"Features: {len(model_config.FEATURE_COLS)}")
    print("Building feature dataset...")
    df = build_feature_dataset(allow_missing_elo=args.allow_missing_elo)

    if args.walk_forward:
        end_round = args.end_round or max(df["round_number"].unique())
        print(f"\nWalk-forward R{args.round}-R{end_round}")
        print("-" * 60)

        reports = run_walk_forward_reports(df, args.round, end_round, args.output_dir)

        # Summary
        with_actual = [r for r in reports if r.get("actual_result")]
        if with_actual:
            correct = sum(1 for r in with_actual if r.get("result_correct"))
            print(f"\nTotal: {len(with_actual)} predictions, "
                  f"{correct}/{len(with_actual)} correct ({correct/len(with_actual):.1%})")

        label = f"wf_R{args.round}_{end_round}_{model_config.MODEL_VERSION}"
        save_output(reports, args.output_dir, label)

    else:
        print(f"\nPredicting Round {args.round}")
        print("=" * 60)

        reports = predict_round(args.round, df=df)

        for report in reports:
            print_report(report, show_actual=args.backtest)
            print()

        # Summary
        if args.backtest:
            with_actual = [r for r in reports if r.get("actual_result")]
            if with_actual:
                correct = sum(1 for r in with_actual if r.get("result_correct"))
                print(f"Round {args.round}: {correct}/{len(with_actual)} correct "
                      f"({correct/len(with_actual):.1%})")

        label = f"R{args.round}_{model_config.MODEL_VERSION}"
        save_output(reports, args.output_dir, label)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
