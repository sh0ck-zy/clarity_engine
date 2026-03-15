#!/usr/bin/env python3
"""
Compare Versions — v1.4 vs v1.5 comparison across 3 independent axes.

Axis 1: Reading quality (pre-match, no result needed)
Axis 2: Directional accuracy (post-match, needs results)
Axis 3: Financial performance (FUTURE — empty placeholder)

Usage:
    python scripts/compare_versions.py PL_R28
    python scripts/compare_versions.py PL_R28 --output comparison.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


def compare_versions(round_label: str, output_path: str | None = None) -> Dict[str, Any]:
    """
    Compare v1.4 vs v1.5 for a round.

    Returns a comparison dict with 3 axes.
    """
    round_path = PROJECT_ROOT / "output" / "rounds" / round_label / "matches"

    if not round_path.exists():
        print(f"Round directory not found: {round_path}")
        return {}

    matches = sorted([d for d in round_path.iterdir() if d.is_dir()])
    if not matches:
        print(f"No matches found")
        return {}

    # Collect data
    v14_entries: List[Dict] = []
    v15_entries: List[Dict] = []

    for match_dir in matches:
        report = _load_json(match_dir / "report.json")
        intelligence = _load_json(match_dir / "match_intelligence.json")
        eval_record = _load_json(match_dir / "evaluation_record.json")

        if not report:
            continue

        name = match_dir.name
        pred = report.get("prediction", {})

        v14_entry = {
            "match": name,
            "predicted_result": pred.get("predicted_result", ""),
            "confidence": pred.get("confidence_label", ""),
            "p_max": report.get("signals", {}).get("p_max", 0),
        }

        v15_entry = {
            "match": name,
        }

        if intelligence:
            v15_entry["lean"] = intelligence.get("lean", "")
            v15_entry["lean_direction"] = _infer_direction(intelligence.get("lean", "").lower())
            v15_entry["confidence"] = intelligence.get("confidence", "")
            v15_entry["key_question"] = intelligence.get("key_question", "")
            v15_entry["n_evidence"] = (
                len(intelligence.get("evidence_for", []))
                + len(intelligence.get("evidence_against", []))
            )
            v15_entry["n_scenarios"] = len(intelligence.get("scenarios", []))
            v15_entry["n_players"] = _count_players(intelligence)

        if eval_record:
            v15_entry["validator_score"] = eval_record.get("validator_score", 0)
            v15_entry["rubric_score"] = eval_record.get("rubric_score", 0)
            result = eval_record.get("result")
            if result:
                v14_entry["actual_result"] = result.get("actual_result", "")
                v15_entry["actual_result"] = result.get("actual_result", "")
                v14_entry["correct"] = v14_entry["predicted_result"] == result.get("actual_result", "")
                v15_entry["correct"] = v15_entry.get("lean_direction", "") == result.get("actual_result", "")

                post = eval_record.get("post_match_rubric", {})
                if post:
                    v15_entry["post_match_score"] = post.get("score", 0)

        v14_entries.append(v14_entry)
        v15_entries.append(v15_entry)

    # --- AXIS 1: Reading Quality (pre-match) ---
    reading_quality = _compute_reading_quality(v14_entries, v15_entries)

    # --- AXIS 2: Directional Accuracy (post-match) ---
    directional_accuracy = _compute_directional_accuracy(v14_entries, v15_entries)

    # --- AXIS 3: Financial Performance (future) ---
    financial_performance = {
        "status": "not_available",
        "note": "Requires market intelligence layer (future v1.6+)",
    }

    comparison = {
        "round": round_label,
        "total_matches": len(matches),
        "reading_quality": reading_quality,
        "directional_accuracy": directional_accuracy,
        "financial_performance": financial_performance,
    }

    # Print summary
    _print_summary(comparison)

    # Save if requested
    if output_path:
        out = Path(output_path)
    else:
        out = PROJECT_ROOT / "output" / "rounds" / round_label / "version_comparison.json"

    out.write_text(json.dumps(comparison, indent=2, ensure_ascii=False, default=str))
    print(f"\nSaved to: {out}")

    return comparison


def _compute_reading_quality(v14: List[Dict], v15: List[Dict]) -> Dict[str, Any]:
    """Axis 1: Reading quality comparison (pre-match, no results needed)."""
    v15_with_scores = [e for e in v15 if "validator_score" in e]

    # v1.5 metrics
    v15_validator_avg = 0.0
    v15_rubric_avg = 0.0
    v15_evidence_avg = 0.0
    v15_players_avg = 0.0

    if v15_with_scores:
        v15_validator_avg = sum(e.get("validator_score", 0) for e in v15_with_scores) / len(v15_with_scores)
        v15_rubric_avg = sum(e.get("rubric_score", 0) for e in v15_with_scores) / len(v15_with_scores)
        v15_evidence_avg = sum(e.get("n_evidence", 0) for e in v15_with_scores) / len(v15_with_scores)
        v15_players_avg = sum(e.get("n_players", 0) for e in v15_with_scores) / len(v15_with_scores)

    return {
        "v15": {
            "validator_score_avg": round(v15_validator_avg, 1),
            "rubric_score_avg": round(v15_rubric_avg, 1),
            "avg_evidence_items": round(v15_evidence_avg, 1),
            "avg_player_names": round(v15_players_avg, 1),
            "matches_scored": len(v15_with_scores),
        },
        "v14": {
            "note": "v1.4 does not produce reading quality scores — probabilistic only",
        },
    }


def _compute_directional_accuracy(v14: List[Dict], v15: List[Dict]) -> Dict[str, Any]:
    """Axis 2: Directional accuracy comparison (requires results)."""
    v14_with_result = [e for e in v14 if "actual_result" in e]
    v15_with_result = [e for e in v15 if "actual_result" in e]

    result = {
        "matches_with_results": len(v14_with_result),
    }

    if not v14_with_result:
        result["status"] = "no_results_available"
        return result

    # v1.4 accuracy
    v14_correct = sum(1 for e in v14_with_result if e.get("correct"))
    result["v14"] = {
        "accuracy": round(v14_correct / len(v14_with_result), 3),
        "correct": v14_correct,
        "total": len(v14_with_result),
    }

    # v1.5 accuracy
    v15_correct = sum(1 for e in v15_with_result if e.get("correct"))
    result["v15"] = {
        "accuracy": round(v15_correct / len(v15_with_result), 3) if v15_with_result else 0,
        "correct": v15_correct,
        "total": len(v15_with_result),
    }

    # Confidence calibration
    v15_calibration = _compute_calibration(v15_with_result)
    if v15_calibration:
        result["v15"]["calibration"] = v15_calibration

    # v1.5 post-match rubric avg
    post_scores = [e.get("post_match_score", 0) for e in v15_with_result if "post_match_score" in e]
    if post_scores:
        result["v15"]["post_match_rubric_avg"] = round(sum(post_scores) / len(post_scores), 1)

    return result


def _compute_calibration(entries: List[Dict]) -> Dict[str, Any]:
    """Compute confidence calibration: hit rate per confidence level."""
    buckets: Dict[str, List[bool]] = {}
    for e in entries:
        conf = e.get("confidence", "Medium")
        correct = e.get("correct", False)
        if conf not in buckets:
            buckets[conf] = []
        buckets[conf].append(correct)

    if not buckets:
        return {}

    cal = {}
    for conf, results in sorted(buckets.items()):
        hits = sum(1 for r in results if r)
        cal[conf] = {
            "hit_rate": round(hits / len(results), 3),
            "count": len(results),
        }

    return cal


def _count_players(intel: Dict) -> int:
    """Count unique player names in intelligence."""
    import re
    text = " ".join([
        intel.get("main_read", ""),
        intel.get("lean", ""),
        *[e.get("claim", "") for e in intel.get("evidence_for", [])],
        *[e.get("claim", "") for e in intel.get("evidence_against", [])],
        *[s.get("description", "") for s in intel.get("scenarios", [])],
    ])
    names = re.findall(
        r"[A-Z][a-zéèêëàâäùûüôöîïñ]+(?:\s+(?:de\s+)?[A-Z][a-zéèêëàâäùûüôöîïñ]+)*",
        text,
    )
    non_names = {
        "Home", "Away", "Draw", "Medium", "High", "Low", "Strong",
        "Moderate", "Weak", "Control", "Transition", "The", "This",
        "That", "Most", "Score", "First", "Stalemate",
    }
    return len({n for n in names if n not in non_names and len(n) > 3})


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


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, IOError):
        return None


def _print_summary(comparison: Dict) -> None:
    """Print comparison summary to terminal."""
    print(f"\n{'=' * 60}")
    print(f"  VERSION COMPARISON: {comparison['round']}")
    print(f"  {comparison['total_matches']} matches")
    print(f"{'=' * 60}")

    # Reading quality
    rq = comparison.get("reading_quality", {})
    v15_rq = rq.get("v15", {})
    if v15_rq.get("matches_scored", 0):
        print(f"\n  AXIS 1: Reading Quality (pre-match)")
        print(f"    v1.5 validator avg: {v15_rq.get('validator_score_avg', 0):.1f}/100")
        print(f"    v1.5 rubric avg:    {v15_rq.get('rubric_score_avg', 0):.1f}/100")
        print(f"    Avg evidence items: {v15_rq.get('avg_evidence_items', 0):.1f}")
        print(f"    Avg player names:   {v15_rq.get('avg_player_names', 0):.1f}")

    # Directional accuracy
    da = comparison.get("directional_accuracy", {})
    if da.get("matches_with_results", 0):
        print(f"\n  AXIS 2: Directional Accuracy (post-match)")
        v14_da = da.get("v14", {})
        v15_da = da.get("v15", {})
        print(f"    v1.4 accuracy: {v14_da.get('accuracy', 0):.1%} ({v14_da.get('correct', 0)}/{v14_da.get('total', 0)})")
        print(f"    v1.5 accuracy: {v15_da.get('accuracy', 0):.1%} ({v15_da.get('correct', 0)}/{v15_da.get('total', 0)})")

        cal = v15_da.get("calibration", {})
        if cal:
            print(f"    Confidence calibration:")
            for level, data in cal.items():
                print(f"      {level}: {data['hit_rate']:.0%} ({data['count']} matches)")

    # Financial
    fp = comparison.get("financial_performance", {})
    print(f"\n  AXIS 3: Financial Performance")
    print(f"    {fp.get('status', 'not_available')} — {fp.get('note', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare v1.4 vs v1.5")
    parser.add_argument("round", help="Round label (e.g. PL_R28)")
    parser.add_argument("--output", help="Output file path (default: in round dir)")
    args = parser.parse_args()

    compare_versions(args.round, output_path=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
