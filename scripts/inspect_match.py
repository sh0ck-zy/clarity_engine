#!/usr/bin/env python3
"""
Inspect Match — structured comparison view for a single match.

Non-interactive CLI that prints data quality, signals, v1.4 vs v1.5, and alignment.

Usage:
    python scripts/inspect_match.py PL_R30 Arsenal_vs_Everton
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


def inspect_match(round_label: str, match_folder: str) -> None:
    """Print structured inspection of a single match."""
    match_dir = PROJECT_ROOT / "output" / "rounds" / round_label / "matches" / match_folder

    if not match_dir.exists():
        print(f"Match directory not found: {match_dir}")
        return

    # Load artefacts
    report = _load_json(match_dir / "report.json")
    match_pack = _load_json(match_dir / "match_pack.json")
    ml_anchor = _load_json(match_dir / "ml_anchor.json")
    signals = _load_json(match_dir / "match_signals.json")
    intelligence = _load_json(match_dir / "match_intelligence.json")
    eval_record = _load_json(match_dir / "evaluation_record.json")
    trace = _load_json(match_dir / "trace.json")

    fixture = (match_pack or report or {}).get("fixture", {})
    home = fixture.get("home_team", "Home")
    away = fixture.get("away_team", "Away")
    league = fixture.get("league", "")
    round_num = fixture.get("round_number", "?")

    print(f"\n{'=' * 60}")
    print(f"  {home} vs {away} | {league} R{round_num}")
    print(f"{'=' * 60}")

    # DATA QUALITY
    if trace:
        dq_steps = [s for s in trace.get("steps", []) if s.get("source") == "data_quality"]
        if dq_steps:
            dq = dq_steps[0].get("metadata", {})
            dq_score = dq.get("score", "?")
            dq_warnings = dq.get("warnings", [])
            warn_text = f" ({len(dq_warnings)} warnings)" if dq_warnings else ""
            print(f"\n  DATA: {dq_score}/100{warn_text}")
            for w in dq_warnings[:3]:
                if isinstance(w, dict):
                    print(f"    - {w.get('issue', w)}")
                else:
                    print(f"    - {w}")

    # SIGNALS
    if signals:
        sigs = signals.get("signals", {})
        sig_parts = []
        if sigs.get("draw_pressure_risk"):
            sig_parts.append("draw_pressure=true")
        venue = sigs.get("venue_advantage", "")
        if venue and venue != "none":
            sig_parts.append(f"venue={venue}")
        clash = sigs.get("style_clash_type", "")
        if clash:
            sig_parts.append(f"style={clash}")
        if sigs.get("upset_potential"):
            sig_parts.append("upset=true")
        if sigs.get("away_transition_threat"):
            sig_parts.append("away_transition=true")
        print(f"\n  SIGNALS: {', '.join(sig_parts) if sig_parts else 'none'}")

    # v1.4
    if report:
        probs = report.get("probabilities", {})
        pred = report.get("prediction", {})
        pred_result = pred.get("predicted_result", "?")
        pred_conf = pred.get("confidence_label", "?")
        prob_str = (
            f"H {probs.get('home_win', 0):.1%} | "
            f"D {probs.get('draw', 0):.1%} | "
            f"A {probs.get('away_win', 0):.1%}"
        )
        print(f"\n  v1.4: {pred_result} ({pred_conf}) — {prob_str}")

    # v1.5
    if intelligence:
        lean = intelligence.get("lean", "?")
        conf = intelligence.get("confidence", "?")
        kq = intelligence.get("key_question", "")
        rubric_score = ""
        if eval_record and "rubric_score" in eval_record:
            rubric_score = f", rubric {eval_record['rubric_score']}"
        validator = ""
        if eval_record:
            validator = f", validator {eval_record.get('validator_score', '?')}"
        print(f"\n  v1.5: \"{lean}\" ({conf}{rubric_score}{validator})")
        if kq:
            print(f"    Key Q: {kq}")

    # ALIGNMENT
    if report and intelligence:
        pred_result = report.get("prediction", {}).get("predicted_result", "")
        lean_text = intelligence.get("lean", "").lower()

        # Infer lean direction
        lean_dir = _infer_direction(lean_text)
        aligned = lean_dir == pred_result
        alignment = "ALIGNED" if aligned else "DIVERGENT"
        print(f"\n  ALIGNMENT: {alignment} (ML={pred_result}, lean={lean_dir})")

    # RESULT
    if eval_record:
        result = eval_record.get("result")
        if result:
            actual = result.get("actual_result", "?")
            hs = result.get("home_score", "?")
            aws = result.get("away_score", "?")
            post_rubric = eval_record.get("post_match_rubric", {})
            post_score = post_rubric.get("score", "")
            post_str = f" (post-match: {post_score})" if post_score else ""
            print(f"\n  RESULT: {actual} ({hs}-{aws}){post_str}")
        else:
            print(f"\n  RESULT: (pending)")

    # TRACE summary
    if trace:
        summary = trace.get("summary", {})
        total_ms = trace.get("total_duration_ms", 0)
        failed = summary.get("tools_failed", [])
        total_warns = summary.get("total_warnings", 0)
        fail_str = f", {len(failed)} failed" if failed else ""
        print(f"\n  TRACE: {total_ms}ms, {summary.get('total_steps', 0)} steps{fail_str}, {total_warns} warnings")

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
    parser = argparse.ArgumentParser(description="Inspect a single match")
    parser.add_argument("round", help="Round label (e.g. PL_R30)")
    parser.add_argument("match", help="Match folder name (e.g. Arsenal_vs_Everton)")
    args = parser.parse_args()

    inspect_match(args.round, args.match)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
