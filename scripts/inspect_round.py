#!/usr/bin/env python3
"""
Inspect Round — one-line-per-match summary table for an entire round.

Shows ML pick, MI lean, confidence, rubric, data quality, alignment, and result.

Usage:
    python scripts/inspect_round.py PL_R30
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


def inspect_round(round_label: str) -> None:
    """Print one-line summary for each match in the round."""
    round_path = PROJECT_ROOT / "output" / "rounds" / round_label / "matches"

    if not round_path.exists():
        print(f"Round directory not found: {round_path}")
        return

    matches = sorted([d for d in round_path.iterdir() if d.is_dir()])
    if not matches:
        print(f"No matches found in {round_path}")
        return

    # Header
    print(f"\n{'=' * 100}")
    print(f"  {round_label} — {len(matches)} matches")
    print(f"{'=' * 100}")
    print(
        f"  {'Match':<30} {'ML':>4} {'Lean':>6} {'Conf':>8} "
        f"{'Valid':>5} {'Rubric':>6} {'DQ':>4} {'Align':>8} {'Result':>6}"
    )
    print(f"  {'-' * 90}")

    stats = {"aligned": 0, "divergent": 0, "correct_ml": 0, "correct_lean": 0, "total_with_result": 0}

    for match_dir in matches:
        report = _load_json(match_dir / "report.json")
        intelligence = _load_json(match_dir / "match_intelligence.json")
        eval_record = _load_json(match_dir / "evaluation_record.json")
        trace = _load_json(match_dir / "trace.json")

        # Match name
        name = match_dir.name.replace("_", " ")
        if len(name) > 28:
            name = name[:28] + ".."

        # ML prediction
        ml_pick = ""
        if report:
            ml_pick = report.get("prediction", {}).get("predicted_result", "?")

        # MI lean
        lean_dir = ""
        confidence = ""
        if intelligence:
            lean_text = intelligence.get("lean", "").lower()
            lean_dir = _infer_direction(lean_text)
            confidence = intelligence.get("confidence", "?")
            # Abbreviate confidence
            conf_abbr = {
                "High": "High",
                "Medium-High": "M-Hi",
                "Medium": "Med",
                "Medium-Low": "M-Lo",
                "Low": "Low",
            }
            confidence = conf_abbr.get(confidence, confidence)

        # Validator score
        validator = ""
        if eval_record:
            validator = f"{eval_record.get('validator_score', 0):.0f}"

        # Rubric score
        rubric = ""
        if eval_record and "rubric_score" in eval_record:
            rubric = f"{eval_record['rubric_score']:.0f}"

        # Data quality
        dq = ""
        if trace:
            for step in trace.get("steps", []):
                if step.get("source") == "data_quality":
                    dq_score = step.get("metadata", {}).get("score")
                    if dq_score is not None:
                        dq = f"{dq_score:.0f}"
                    break

        # Alignment
        alignment = ""
        if ml_pick and lean_dir:
            if lean_dir == ml_pick:
                alignment = "ALIGNED"
                stats["aligned"] += 1
            else:
                alignment = "DIVERGE"
                stats["divergent"] += 1

        # Result
        result_str = ""
        if eval_record and eval_record.get("result"):
            actual = eval_record["result"].get("actual_result", "")
            hs = eval_record["result"].get("home_score", "?")
            aws = eval_record["result"].get("away_score", "?")
            result_str = f"{actual}({hs}-{aws})"
            stats["total_with_result"] += 1
            if ml_pick == actual:
                stats["correct_ml"] += 1
            if lean_dir == actual:
                stats["correct_lean"] += 1
        else:
            result_str = "—"

        print(
            f"  {name:<30} {ml_pick:>4} {lean_dir:>6} {confidence:>8} "
            f"{validator:>5} {rubric:>6} {dq:>4} {alignment:>8} {result_str:>6}"
        )

    # Footer stats
    print(f"  {'-' * 90}")
    total = stats["aligned"] + stats["divergent"]
    if total:
        print(f"  Alignment: {stats['aligned']}/{total} aligned ({stats['aligned']/total:.0%})")
    if stats["total_with_result"]:
        n = stats["total_with_result"]
        print(
            f"  Accuracy: ML {stats['correct_ml']}/{n} ({stats['correct_ml']/n:.0%})"
            f" | Lean {stats['correct_lean']}/{n} ({stats['correct_lean']/n:.0%})"
        )
    print()


def _load_json(path: Path) -> dict | None:
    """Load a JSON file, returning None if not found."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, IOError):
        return None


def _infer_direction(text: str) -> str:
    """Infer H/D/A from text."""
    home_words = ["home", "host", "favourite", "favorite", "control", "dominat"]
    away_words = ["away", "visitor", "underdog", "upset"]
    draw_words = ["draw", "stalemate", "even", "balanced", "tight"]

    h = sum(1 for w in home_words if w in text)
    a = sum(1 for w in away_words if w in text)
    d = sum(1 for w in draw_words if w in text)

    if d > h and d > a:
        return "D"
    if a > h:
        return "A"
    return "H"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a round — one line per match")
    parser.add_argument("round", help="Round label (e.g. PL_R30)")
    args = parser.parse_args()

    inspect_round(args.round)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
