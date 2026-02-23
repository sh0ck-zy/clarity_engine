"""
Probabilistic prediction model: multinomial logistic regression with walk-forward evaluation.

Produces calibrated P(H/D/A) per match from team_states feature vectors.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.preprocessing import StandardScaler

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from models.feature_builder import FEATURE_COLS


@dataclass
class ProbabilisticEvalResults:
    """Aggregate results from walk-forward evaluation."""

    total_predictions: int = 0
    predict_rounds: List[int] = field(default_factory=list)

    # Primary metrics
    log_loss_val: float = 0.0
    accuracy: float = 0.0

    # By result type
    draw_recall: float = 0.0
    home_win_accuracy: float = 0.0
    draw_accuracy: float = 0.0
    away_win_accuracy: float = 0.0

    # Distribution
    pct_home_predicted: float = 0.0
    pct_draw_predicted: float = 0.0
    pct_away_predicted: float = 0.0

    # Baselines
    uniform_log_loss: float = 0.0
    marginal_log_loss: float = 0.0
    market_log_loss: Optional[float] = None

    # Per-round breakdown
    per_round: List[Dict] = field(default_factory=list)


def _compute_margin_entropy(probas: np.ndarray) -> Tuple[float, float, float]:
    """Compute p_max, margin_top2, and normalized entropy for a probability vector."""
    sorted_p = np.sort(probas)[::-1]
    p_max = float(sorted_p[0])
    margin_top2 = float(sorted_p[0] - sorted_p[1])

    # Normalized entropy: 0 = certain, 1 = uniform
    entropy = -sum(p * math.log(p) if p > 0 else 0.0 for p in probas)
    entropy_norm = entropy / math.log(3)

    return p_max, margin_top2, entropy_norm


def _compute_marginal_baseline(y_train: np.ndarray, y_test: np.ndarray) -> float:
    """Compute log loss for a model that always predicts training class frequencies."""
    classes = ["A", "D", "H"]
    train_counts = {c: 0 for c in classes}
    for label in y_train:
        train_counts[label] = train_counts.get(label, 0) + 1
    total = len(y_train)
    marginal_probs = np.array(
        [[train_counts[c] / total for c in classes]] * len(y_test)
    )

    return float(log_loss(y_test, marginal_probs, labels=classes))


def walk_forward_evaluate(
    df: pd.DataFrame,
    min_train_rounds: int = 6,
    predict_rounds: Optional[List[int]] = None,
    C: float = 1.0,
    debug_match_id: Optional[str] = None,
) -> Tuple[List[Dict], ProbabilisticEvalResults]:
    """
    Walk-forward evaluation: for each round N, train on rounds < N, predict round N.

    Args:
        df: Feature dataset from build_feature_dataset()
        min_train_rounds: Minimum number of rounds for training (default 6 = R2-R7, predict from R8)
        predict_rounds: Specific rounds to predict (default: all eligible)
        C: Regularization parameter for LogisticRegression
        debug_match_id: If set, print detailed debug info for this match

    Returns:
        (predictions_list, eval_results)
    """
    all_rounds = sorted(df["round_number"].unique())
    min_round = min(all_rounds)
    max_round = max(all_rounds)

    # First predict round = min_round + min_train_rounds
    first_predict = min_round + min_train_rounds

    if predict_rounds is None:
        predict_rounds = [r for r in all_rounds if r >= first_predict]
    else:
        predict_rounds = [r for r in predict_rounds if r >= first_predict and r in all_rounds]

    if not predict_rounds:
        raise ValueError(
            f"No rounds to predict. min_train_rounds={min_train_rounds}, "
            f"available rounds: {all_rounds}"
        )

    print(f"\nWalk-forward: predicting rounds {predict_rounds[0]}-{predict_rounds[-1]}")
    print(f"  Training starts at R{min_round}, first prediction at R{first_predict}")
    print(f"  Features: {len(FEATURE_COLS)} columns\n")

    X_all = df[FEATURE_COLS].values.astype(float)
    y_all = df["result"].values

    predictions: List[Dict] = []
    all_y_true = []
    all_y_proba = []
    all_marginal_proba = []

    for predict_round in predict_rounds:
        train_mask = df["round_number"].values < predict_round
        test_mask = df["round_number"].values == predict_round

        X_train = X_all[train_mask]
        y_train = y_all[train_mask]
        X_test = X_all[test_mask]
        y_test = y_all[test_mask]

        if len(X_train) == 0 or len(X_test) == 0:
            continue

        # Fill NaN with 0 for model
        X_train = np.nan_to_num(X_train, nan=0.0)
        X_test = np.nan_to_num(X_test, nan=0.0)

        # Fit scaler on train only
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Train model
        model = LogisticRegression(
            solver="lbfgs",
            C=C,
            max_iter=1000,
            random_state=42,
            class_weight=None,
        )
        model.fit(X_train_scaled, y_train)

        # Predict
        probas = model.predict_proba(X_test_scaled)
        class_idx = {cls: i for i, cls in enumerate(model.classes_)}

        # Train rounds for audit
        train_rounds_list = sorted(df.loc[train_mask, "round_number"].unique().tolist())

        # Marginal baseline for this round
        train_counts = {c: 0 for c in ["A", "D", "H"]}
        for label in y_train:
            train_counts[label] = train_counts.get(label, 0) + 1
        total_train = len(y_train)
        marginal_probs = np.array(
            [[train_counts.get(c, 0) / total_train for c in model.classes_]] * len(y_test)
        )

        test_rows = df[test_mask].reset_index(drop=True)

        for i in range(len(test_rows)):
            row = test_rows.iloc[i]
            prob_H = float(probas[i, class_idx["H"]])
            prob_D = float(probas[i, class_idx["D"]])
            prob_A = float(probas[i, class_idx["A"]])
            predicted = model.classes_[np.argmax(probas[i])]
            actual = str(row["result"])

            p_max, margin_top2, entropy_norm = _compute_margin_entropy(probas[i])

            fixture_id = str(row["fotmob_match_id"])

            pred = {
                "fixture_id": fixture_id,
                "round_number": int(row["round_number"]),
                "match_date": str(row["match_date"])[:10],
                "home_team": row["home_team_name"],
                "away_team": row["away_team_name"],
                "prob_H": round(prob_H, 4),
                "prob_D": round(prob_D, 4),
                "prob_A": round(prob_A, 4),
                "predicted_result": predicted,
                "actual_result": actual,
                "result_correct": predicted == actual,
                "p_max": round(p_max, 4),
                "margin_top2": round(margin_top2, 4),
                "entropy_norm": round(entropy_norm, 4),
                "train_size": int(len(X_train)),
                "train_rounds": train_rounds_list,
                "elo_missing_any": bool(row.get("elo_missing_any", 0)),
            }
            predictions.append(pred)

            all_y_true.append(actual)
            all_y_proba.append([probas[i, class_idx[c]] for c in ["A", "D", "H"]])
            all_marginal_proba.append(
                [marginal_probs[i, class_idx[c]] for c in ["A", "D", "H"]]
            )

            # Debug output
            if debug_match_id and fixture_id == debug_match_id:
                print(f"\n{'='*60}")
                print(f"DEBUG: Match {fixture_id}")
                print(f"  {row['home_team_name']} vs {row['away_team_name']} (R{row['round_number']})")
                print(f"  Actual: {actual}")
                print(f"\n  Features BEFORE scaling:")
                for j, col in enumerate(FEATURE_COLS):
                    print(f"    {col:30s} = {X_test[i, j]:8.2f}")
                print(f"\n  Features AFTER scaling:")
                for j, col in enumerate(FEATURE_COLS):
                    print(f"    {col:30s} = {X_test_scaled[i, j]:8.4f}")
                print(f"\n  Probabilities: H={prob_H:.3f}  D={prob_D:.3f}  A={prob_A:.3f}")
                print(f"  Predicted: {predicted}  Correct: {predicted == actual}")
                print(f"  p_max={p_max:.3f}  margin={margin_top2:.3f}  entropy_norm={entropy_norm:.3f}")
                print(f"  Train: {len(X_train)} matches, rounds {train_rounds_list[0]}-{train_rounds_list[-1]}")
                print(f"  team_states round used: {int(row['round_number']) - 1}")
                print(f"{'='*60}\n")

    # Compute aggregate metrics
    results = _compute_metrics(predictions, all_y_true, all_y_proba, all_marginal_proba, predict_rounds)

    return predictions, results


def _compute_metrics(
    predictions: List[Dict],
    y_true: List[str],
    y_proba: List[List[float]],
    marginal_proba: List[List[float]],
    predict_rounds: List[int],
) -> ProbabilisticEvalResults:
    """Compute all evaluation metrics."""
    results = ProbabilisticEvalResults()
    results.total_predictions = len(predictions)
    results.predict_rounds = predict_rounds

    if not predictions:
        return results

    y_true_arr = np.array(y_true)
    y_proba_arr = np.array(y_proba)
    marginal_arr = np.array(marginal_proba)
    labels = ["A", "D", "H"]

    # Primary metrics
    results.log_loss_val = float(log_loss(y_true_arr, y_proba_arr, labels=labels))
    results.accuracy = sum(1 for p in predictions if p["result_correct"]) / len(predictions)

    # Baselines
    n = len(y_true_arr)
    uniform_proba = np.full((n, 3), 1.0 / 3.0)
    results.uniform_log_loss = float(log_loss(y_true_arr, uniform_proba, labels=labels))
    results.marginal_log_loss = float(log_loss(y_true_arr, marginal_arr, labels=labels))

    # By result type
    predicted_results = [p["predicted_result"] for p in predictions]
    actual_results = [p["actual_result"] for p in predictions]

    # Home accuracy
    home_pred = [i for i, p in enumerate(predicted_results) if p == "H"]
    results.home_win_accuracy = (
        sum(1 for i in home_pred if actual_results[i] == "H") / len(home_pred)
        if home_pred else 0.0
    )

    # Draw accuracy + recall
    draw_pred = [i for i, p in enumerate(predicted_results) if p == "D"]
    actual_draws = [i for i, a in enumerate(actual_results) if a == "D"]
    results.draw_accuracy = (
        sum(1 for i in draw_pred if actual_results[i] == "D") / len(draw_pred)
        if draw_pred else 0.0
    )
    results.draw_recall = (
        sum(1 for i in actual_draws if predicted_results[i] == "D") / len(actual_draws)
        if actual_draws else 0.0
    )

    # Away accuracy
    away_pred = [i for i, p in enumerate(predicted_results) if p == "A"]
    results.away_win_accuracy = (
        sum(1 for i in away_pred if actual_results[i] == "A") / len(away_pred)
        if away_pred else 0.0
    )

    # Distribution
    total = len(predicted_results)
    results.pct_home_predicted = len(home_pred) / total
    results.pct_draw_predicted = len(draw_pred) / total
    results.pct_away_predicted = len(away_pred) / total

    # Per-round breakdown
    for round_num in predict_rounds:
        round_preds = [p for p in predictions if p["round_number"] == round_num]
        if not round_preds:
            continue

        round_y_true = [p["actual_result"] for p in round_preds]
        round_y_proba = []
        for p in round_preds:
            round_y_proba.append([p["prob_A"], p["prob_D"], p["prob_H"]])

        round_correct = sum(1 for p in round_preds if p["result_correct"])

        round_info = {
            "round_number": round_num,
            "n_matches": len(round_preds),
            "correct": round_correct,
            "accuracy": round_correct / len(round_preds),
            "log_loss": float(log_loss(round_y_true, round_y_proba, labels=labels)),
            "train_size": round_preds[0]["train_size"],
        }
        results.per_round.append(round_info)

    return results


def load_market_baseline(
    csv_path: Optional[Path] = None,
    df: Optional[pd.DataFrame] = None,
) -> Optional[float]:
    """
    Compute market baseline log loss from Bet365 odds in E0_2526.csv.

    Matches CSV rows to prediction rows by date + home + away team names.
    Returns log_loss or None if CSV not found / no matches.
    """
    if csv_path is None:
        csv_path = _PROJECT_ROOT / "data" / "football_data" / "odds" / "E0_2526.csv"

    if not csv_path.exists():
        print(f"Market baseline CSV not found: {csv_path}")
        return None

    odds_df = pd.read_csv(csv_path)

    # Normalize columns
    required = ["Date", "HomeTeam", "AwayTeam", "B365H", "B365D", "B365A", "FTR"]
    if not all(c in odds_df.columns for c in required):
        print(f"Market CSV missing columns. Found: {list(odds_df.columns)}")
        return None

    # Build implied probabilities (normalized after vig removal)
    odds_df["impl_H"] = 1.0 / odds_df["B365H"]
    odds_df["impl_D"] = 1.0 / odds_df["B365D"]
    odds_df["impl_A"] = 1.0 / odds_df["B365A"]
    total_impl = odds_df["impl_H"] + odds_df["impl_D"] + odds_df["impl_A"]
    odds_df["prob_H"] = odds_df["impl_H"] / total_impl
    odds_df["prob_D"] = odds_df["impl_D"] / total_impl
    odds_df["prob_A"] = odds_df["impl_A"] / total_impl

    if df is None:
        return None

    # Match by date + home + away
    # Normalize team names for matching
    def _normalize(name: str) -> str:
        return name.strip().lower().replace(" ", "")

    matched_true = []
    matched_proba = []

    for _, pred_row in df.iterrows():
        match_date = str(pred_row["match_date"])[:10]
        home = _normalize(str(pred_row["home_team_name"]))
        away = _normalize(str(pred_row["away_team_name"]))

        for _, odds_row in odds_df.iterrows():
            odds_home = _normalize(str(odds_row["HomeTeam"]))
            odds_away = _normalize(str(odds_row["AwayTeam"]))

            if odds_home == home and odds_away == away:
                result = str(pred_row["result"])
                matched_true.append(result)
                matched_proba.append(
                    [odds_row["prob_A"], odds_row["prob_D"], odds_row["prob_H"]]
                )
                break

    if not matched_true:
        print("No market matches found (team name mismatch?)")
        return None

    market_ll = float(log_loss(matched_true, matched_proba, labels=["A", "D", "H"]))
    print(f"Market baseline: {len(matched_true)}/{len(df)} matches matched, log_loss={market_ll:.4f}")
    return market_ll
