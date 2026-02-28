#!/usr/bin/env python3
"""
Post-match validation — compare narrative claims against actual match data.

After matches are played, checks what the narrative got right vs wrong.

Usage:
    python scripts/validate_postmatch.py PL_R28
    python scripts/validate_postmatch.py PL_R28 --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

ROUNDS_DIR = PROJECT_ROOT / "output" / "rounds"

# Maps section keys to pillar names
PILLAR_NAMES = {
    "a_historia": "Journalist",
    "onde_se_decide": "Pundit",
    "o_que_pode_correr_mal": "Analyst",
    "bottom_line": "Synthesis",
}


def _load_actual_result(match_dir: Path) -> Optional[Dict]:
    """Load actual result from report.json (post-match update)."""
    report_path = match_dir / "report.json"
    if not report_path.exists():
        return None
    with open(report_path) as f:
        report = json.load(f)
    actual = report.get("actual_result")
    if not actual:
        return None
    return {
        "result": actual,
        "correct": report.get("result_correct", False),
        "predicted": report.get("prediction", {}).get("predicted_result"),
        "probabilities": report.get("probabilities", {}),
    }


def _extract_verifiable_claims(narrative: Dict, context: Dict) -> List[Dict]:
    """
    Extract claims from narrative sections that can be verified post-match.

    Claims we can verify:
    - Predicted outcome alignment (H/D/A)
    - Confidence calibration (high confidence = should be right more often)
    - Key player mentions (did they actually perform?)
    - Form continuation (did form trends continue?)
    """
    claims = []
    sections = narrative.get("sections", {})
    ml = context.get("ml_inference", {})

    # 1. Model prediction claim
    predicted = ml.get("predicted_result")
    confidence = ml.get("confidence")
    if predicted:
        claims.append({
            "type": "prediction",
            "section": "ml_inference",
            "claim": f"Model predicted {predicted} with {confidence} confidence",
            "predicted_result": predicted,
            "confidence": confidence,
            "verifiable": True,
        })

    # 2. Extract risk claims from o_que_pode_correr_mal
    analyst = sections.get("o_que_pode_correr_mal", {})
    if isinstance(analyst, dict):
        content = analyst.get("content", "")
    else:
        content = ""

    if content:
        # Split by bullet points or sentences
        risk_lines = re.split(r'[•\n]', content)
        for line in risk_lines:
            line = line.strip()
            if len(line) > 20:  # meaningful content
                claims.append({
                    "type": "risk_flag",
                    "section": "o_que_pode_correr_mal",
                    "claim": line[:200],
                    "verifiable": False,  # most risks need manual review
                })

    # 3. Check if bottom_line was directional
    bottom = sections.get("bottom_line", {})
    if isinstance(bottom, dict):
        bl_content = bottom.get("content", "")
    else:
        bl_content = ""

    if bl_content:
        # Look for directional language
        home_lean = any(w in bl_content.lower() for w in
                       ["home", "arsenal", "liverpool", "should", "favour"])
        draw_lean = any(w in bl_content.lower() for w in
                       ["draw", "tight", "stalemate", "share"])
        away_lean = any(w in bl_content.lower() for w in
                       ["away", "upset", "visitor"])

        direction = None
        if draw_lean:
            direction = "D"
        elif home_lean and not away_lean:
            direction = "H"
        elif away_lean and not home_lean:
            direction = "A"

        if direction:
            claims.append({
                "type": "directional",
                "section": "bottom_line",
                "claim": bl_content[:200],
                "implied_direction": direction,
                "verifiable": True,
            })

    return claims


def validate_match(match_dir: Path) -> Optional[Dict]:
    """
    Validate narrative for a single match against actual result.
    Returns None if match not yet played.
    """
    # Load files
    actual = _load_actual_result(match_dir)
    if not actual:
        return None  # match not played yet

    narrative_path = match_dir / "narrative.json"
    context_path = match_dir / "context.json"

    narrative = {}
    if narrative_path.exists():
        with open(narrative_path) as f:
            narrative = json.load(f)

    context = {}
    if context_path.exists():
        with open(context_path) as f:
            context = json.load(f)

    if not narrative.get("sections"):
        return {
            "match": match_dir.name,
            "actual_result": actual["result"],
            "has_narrative": False,
            "claims_extracted": 0,
            "verifiable": 0,
            "correct": 0,
            "accuracy": 0.0,
        }

    # Extract claims
    claims = _extract_verifiable_claims(narrative, context)

    # Verify claims against actual result
    verified = 0
    correct = 0
    by_section = {}

    for claim in claims:
        if not claim.get("verifiable"):
            continue
        verified += 1

        is_correct = False
        if claim["type"] == "prediction":
            is_correct = claim["predicted_result"] == actual["result"]
        elif claim["type"] == "directional":
            is_correct = claim.get("implied_direction") == actual["result"]

        if is_correct:
            correct += 1
        claim["actual_result"] = actual["result"]
        claim["is_correct"] = is_correct

        # Track by section
        sec = claim.get("section", "unknown")
        if sec not in by_section:
            by_section[sec] = {"claims": 0, "correct": 0}
        by_section[sec]["claims"] += 1
        if is_correct:
            by_section[sec]["correct"] += 1

    accuracy = correct / verified if verified > 0 else 0.0

    return {
        "match": match_dir.name,
        "actual_result": actual["result"],
        "prediction_correct": actual.get("correct", False),
        "has_narrative": True,
        "claims_extracted": len(claims),
        "verifiable": verified,
        "correct": correct,
        "accuracy": round(accuracy, 3),
        "by_section": by_section,
        "claims": claims,
        "validated_at": datetime.now().isoformat(),
    }


def validate_round(round_dir: Path, verbose: bool = False) -> Dict:
    """Validate all matches in a round."""
    matches_dir = round_dir / "matches"
    if not matches_dir.exists():
        print(f"No matches directory found in {round_dir}")
        return {}

    match_dirs = sorted([d for d in matches_dir.iterdir() if d.is_dir()])

    print(f"\n{'='*70}")
    print(f"POST-MATCH VALIDATION | {round_dir.name}")
    print(f"{'='*70}\n")

    results = []
    skipped = 0

    for md in match_dirs:
        result = validate_match(md)
        if result is None:
            skipped += 1
            if verbose:
                print(f"  {md.name}: Not yet played (skipped)")
            continue

        results.append(result)

        # Save per-match validation
        with open(md / "validation.json", "w") as f:
            json.dump(result, f, indent=2, default=str)

        icon = "✓" if result.get("prediction_correct") else "✗"
        acc = result.get("accuracy", 0)
        print(f"  {icon} {result['match']:<40s} "
              f"Predicted: {result.get('actual_result', '?')} | "
              f"Claims: {result['verifiable']} verified, "
              f"{result['correct']} correct ({acc:.0%})")

    # Aggregate
    if results:
        total_correct = sum(1 for r in results if r.get("prediction_correct"))
        total_played = len(results)
        avg_accuracy = sum(r["accuracy"] for r in results) / len(results)

        print(f"\n  {'='*60}")
        print(f"  Matches played: {total_played} ({skipped} not yet played)")
        print(f"  Model predictions correct: {total_correct}/{total_played} "
              f"({total_correct/total_played:.0%})")
        print(f"  Average claim accuracy: {avg_accuracy:.0%}")
    else:
        print(f"\n  No matches have been played yet ({skipped} pending)")

    # Write round validation report
    report = {
        "round": round_dir.name,
        "matches_validated": len(results),
        "matches_pending": skipped,
        "prediction_accuracy": (
            sum(1 for r in results if r.get("prediction_correct")) / len(results)
            if results else 0
        ),
        "avg_claim_accuracy": (
            sum(r["accuracy"] for r in results) / len(results)
            if results else 0
        ),
        "per_match": results,
        "validated_at": datetime.now().isoformat(),
    }

    with open(round_dir / "validation_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"  Report: {round_dir / 'validation_report.json'}")
    print(f"{'='*70}\n")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post-match validation of narrative claims"
    )
    parser.add_argument("round_name", help="Round folder name (e.g., PL_R28)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show skipped matches and claim details")

    args = parser.parse_args()

    rdir = ROUNDS_DIR / args.round_name
    if not rdir.exists():
        print(f"Round directory not found: {rdir}")
        return 1

    validate_round(rdir, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
