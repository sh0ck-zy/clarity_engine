#!/usr/bin/env python3
"""
Calculate Match Intelligence Score (MIS) for a generated round.

Usage:
    python scripts/quality_check.py PL_R28
    python scripts/quality_check.py PL_R28 --verbose
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

ROUNDS_DIR = PROJECT_ROOT / "output" / "rounds"

# MIS component weights (rebalanced to include narrative)
WEIGHTS = {
    "factual_correctness": 0.25,
    "depth": 0.15,
    "context": 0.15,
    "readability": 0.15,
    "narrative_quality": 0.30,
}

# Narrative section scoring config
SECTION_WEIGHTS = {
    "a_historia": {
        "weight": 0.25,
        "checks": ["storytelling_flow", "emotional_hook", "specific_context"],
    },
    "onde_se_decide": {
        "weight": 0.30,
        "checks": ["tactical_insight", "formation_mentioned", "key_battle_identified"],
    },
    "o_que_pode_correr_mal": {
        "weight": 0.25,
        "checks": ["min_3_risks", "data_backed", "contrarian_view"],
    },
    "bottom_line": {
        "weight": 0.20,
        "checks": ["concise", "actionable", "not_fence_sitting"],
    },
}

# Banned words that shouldn't appear in rendered text
_BANNED_WORDS = [
    "elo_delta", "prob_H", "prob_D", "prob_A", "xg_diff_last5_delta",
    "form_points_delta", "goal_diff_season_delta", "position_delta",
    "home_strength_delta", "market_draw_signal", "market_home_edge",
    "market_entropy", "entropy_norm", "margin_top2",
]


def _score_factual_correctness(
    report: Dict, telegram_text: str, x_text: str
) -> Tuple[float, List[str]]:
    """
    Check rendered text probabilities match report.json within ±0.5pp.
    Returns (score 0-1, issues list).
    """
    issues = []
    checks = 0
    passed = 0

    probs = report.get("probabilities", {})
    h_pct = probs.get("home_win", 0) * 100
    d_pct = probs.get("draw", 0) * 100
    a_pct = probs.get("away_win", 0) * 100

    # Extract percentages from rendered text
    for label, text_name, expected in [
        ("telegram", telegram_text, [h_pct, d_pct, a_pct]),
        ("x", x_text, [h_pct, d_pct, a_pct]),
    ]:
        # Find percentage patterns like "H 10.6%" or "H=10.6%"
        pct_matches = re.findall(r'(\d+\.?\d*)%', text_name)
        if not pct_matches:
            issues.append(f"No percentages found in {label} text")
            checks += 1
            continue

        found_pcts = [float(m) for m in pct_matches[:3]]  # First 3 = H, D, A
        if len(found_pcts) >= 3:
            for i, (found, exp) in enumerate(zip(found_pcts, expected)):
                checks += 1
                if abs(found - exp) <= 0.5:
                    passed += 1
                else:
                    outcome = ["H", "D", "A"][i]
                    issues.append(f"{label}: {outcome} shows {found}% but report says {exp:.1f}%")
        else:
            checks += 1
            issues.append(f"{label}: expected 3 probabilities, found {len(found_pcts)}")

    # Check predicted result is mentioned
    pred = report.get("prediction", {}).get("predicted_result", "")
    result_labels = {"H": ["Home Win", "home"], "D": ["Draw", "draw"], "A": ["Away Win", "away"]}
    if pred in result_labels:
        checks += 1
        if any(lbl.lower() in telegram_text.lower() for lbl in result_labels[pred]):
            passed += 1
        else:
            issues.append(f"Predicted result '{pred}' not clearly stated in telegram text")

    # Check report_id footer
    rid = report.get("report_id", "")
    if rid:
        checks += 1
        if rid in telegram_text:
            passed += 1
        else:
            issues.append("report_id not found in telegram text")

    score = passed / checks if checks > 0 else 0.0
    return score, issues


def _score_depth(report: Dict) -> Tuple[float, List[str]]:
    """
    Score based on driver count, risk flag coverage, confidence presence.
    Returns (score 0-1, issues list).
    """
    issues = []
    score_parts = []

    # Drivers: want >= 5
    drivers = report.get("drivers", [])
    n_drivers = len(drivers)
    if n_drivers >= 5:
        score_parts.append(1.0)
    elif n_drivers >= 3:
        score_parts.append(0.7)
        issues.append(f"Only {n_drivers} drivers (target: 5)")
    else:
        score_parts.append(0.3)
        issues.append(f"Only {n_drivers} drivers (target: 5)")

    # Confidence label exists
    conf = report.get("prediction", {}).get("confidence")
    if conf in ("high", "medium", "low"):
        score_parts.append(1.0)
    else:
        score_parts.append(0.0)
        issues.append("Missing confidence classification")

    # Risk flags properly surfaced (they exist in the report)
    if "risk_flags" in report:
        score_parts.append(1.0)
    else:
        score_parts.append(0.5)
        issues.append("No risk_flags field in report")

    # Margin and entropy present
    pred = report.get("prediction", {})
    if pred.get("margin_top2") is not None and pred.get("entropy_norm") is not None:
        score_parts.append(1.0)
    else:
        score_parts.append(0.5)
        issues.append("Missing margin or entropy metrics")

    score = sum(score_parts) / len(score_parts) if score_parts else 0.0
    return score, issues


def _score_context(facts: Dict) -> Tuple[float, List[str]]:
    """
    Score based on data completeness in facts.json.
    Returns (score 0-1, issues list).
    """
    issues = []
    checks_passed = 0
    total_checks = 4

    # 1. ELO data present (not missing)
    if not facts.get("elo_missing", True):
        checks_passed += 1
    else:
        issues.append("ELO data missing")

    # 2. Market odds available
    if facts.get("market_odds"):
        checks_passed += 1
    else:
        issues.append("No market odds available")

    # 3. Home stats present and non-empty
    home_stats = facts.get("home_stats", {})
    if home_stats and len(home_stats) >= 3:
        checks_passed += 1
    else:
        issues.append("Incomplete home team stats")

    # 4. Computed features present and non-null
    features = facts.get("computed_features", {})
    null_features = [k for k, v in features.items() if v is None]
    if not null_features:
        checks_passed += 1
    else:
        issues.append(f"Null features: {null_features}")

    score = checks_passed / total_checks
    return score, issues


def _score_readability(telegram_text: str, x_text: str) -> Tuple[float, List[str]]:
    """
    Score based on length, banned words, and footer presence.
    Returns (score 0-1, issues list).
    """
    issues = []
    checks_passed = 0
    total_checks = 4

    # 1. Telegram text length (target: 100-500 chars)
    tg_len = len(telegram_text)
    if 100 <= tg_len <= 500:
        checks_passed += 1
    else:
        issues.append(f"Telegram length {tg_len} outside 100-500 range")

    # 2. X text length (target: < 280 chars)
    x_len = len(x_text)
    if x_len <= 280:
        checks_passed += 1
    else:
        issues.append(f"X text length {x_len} exceeds 280 chars")

    # 3. No banned technical jargon
    found_banned = []
    for word in _BANNED_WORDS:
        if word in telegram_text or word in x_text:
            found_banned.append(word)
    if not found_banned:
        checks_passed += 1
    else:
        issues.append(f"Banned jargon found: {found_banned}")

    # 4. Audit footer present (report_id + version)
    if "[v" in telegram_text and "|" in telegram_text:
        checks_passed += 1
    else:
        issues.append("Missing audit footer [version | report_id]")

    score = checks_passed / total_checks
    return score, issues


def _score_narrative_quality(
    match_dir: Path, context_data: Dict
) -> Tuple[float, List[str], Dict]:
    """
    Score the LLM-generated narrative per section.
    Returns (overall_score, issues, by_section_breakdown).
    """
    narrative_path = match_dir / "narrative.json"
    if not narrative_path.exists():
        return 0.0, ["No narrative.json found"], {}

    with open(narrative_path) as f:
        narrative = json.load(f)

    sections = narrative.get("sections", {})
    if not sections:
        return 0.0, ["narrative.json has no sections"], {}

    # Get context for cross-referencing
    factual = context_data.get("factual", {})
    home = factual.get("home", {})
    away = factual.get("away", {})

    # Collect player names for verification
    player_names = set()
    for side in [home, away]:
        for p in side.get("key_players", []):
            name = p.get("name", "")
            if name:
                # Add both full name and last name
                player_names.add(name)
                parts = name.split()
                if len(parts) > 1:
                    player_names.add(parts[-1])

    all_issues = []
    by_section = {}
    weighted_total = 0.0

    for sec_key, sec_config in SECTION_WEIGHTS.items():
        sec = sections.get(sec_key, {})
        content = sec.get("content", "") if isinstance(sec, dict) else ""
        issues = []
        checks = 0
        passed = 0
        weight = sec_config["weight"]

        if not content:
            by_section[sec_key] = {"score": 0, "issues": ["Section is empty"]}
            continue

        word_count = len(content.split())

        if sec_key == "a_historia":
            # storytelling_flow: >= 40 words, narrative structure
            checks += 1
            if word_count >= 40:
                passed += 1
            else:
                issues.append(f"Too short ({word_count} words, need 40+)")

            # emotional_hook: references form, stakes, momentum
            checks += 1
            stakes_words = ["title", "relegation", "crucial", "must-win", "battle",
                           "charge", "run", "streak", "momentum", "improving", "declining",
                           "desperate", "hunt", "fight", "push"]
            if any(w in content.lower() for w in stakes_words):
                passed += 1
            else:
                issues.append("No emotional/stakes language found")

            # specific_context: mentions round numbers or recent results
            checks += 1
            if re.search(r'R\d+|Round \d+|\d+-\d+', content):
                passed += 1
            else:
                issues.append("No specific results/round references")

        elif sec_key == "onde_se_decide":
            # tactical_insight: word count >= 40
            checks += 1
            if word_count >= 40:
                passed += 1
            else:
                issues.append(f"Too short ({word_count} words)")

            # formation_mentioned
            checks += 1
            if re.search(r'\d-\d-\d', content):
                passed += 1
            else:
                issues.append("No formation pattern (e.g., 4-3-3) mentioned")

            # key_battle_identified: player names mentioned
            checks += 1
            mentioned = sum(1 for n in player_names if n in content)
            if mentioned >= 2:
                passed += 1
            else:
                issues.append(f"Only {mentioned} player names (need 2+)")

        elif sec_key == "o_que_pode_correr_mal":
            # min_3_risks: bullet points or distinct risk statements
            checks += 1
            risk_markers = content.count("•") + content.count("- ") + content.count("Firstly") + content.count("Secondly")
            # Also count sentences if no bullet markers
            sentences = [s.strip() for s in re.split(r'[.!]', content) if s.strip()]
            risk_count = max(risk_markers, len(sentences))
            if risk_count >= 3:
                passed += 1
            else:
                issues.append(f"Only {risk_count} risk points (need 3+)")

            # data_backed: has numbers
            checks += 1
            numbers = re.findall(r'\d+\.?\d*', content)
            if len(numbers) >= 3:
                passed += 1
            else:
                issues.append(f"Only {len(numbers)} data points (need 3+)")

            # contrarian_view: challenges assumptions
            checks += 1
            contrarian = ["despite", "however", "but", "risk", "danger", "concern",
                         "vulnerability", "weakness", "contradicts", "although"]
            if any(w in content.lower() for w in contrarian):
                passed += 1
            else:
                issues.append("No contrarian/risk language detected")

        elif sec_key == "bottom_line":
            # concise: <= 50 words
            checks += 1
            if word_count <= 50:
                passed += 1
            else:
                issues.append(f"Too long ({word_count} words, max 50)")

            # actionable: not wishy-washy
            checks += 1
            fence_sitting = ["it could go either way", "hard to say",
                           "anything can happen", "50-50"]
            if not any(f in content.lower() for f in fence_sitting):
                passed += 1
            else:
                issues.append("Bottom line is fence-sitting")

            # not empty basically
            checks += 1
            if word_count >= 8:
                passed += 1
            else:
                issues.append("Bottom line too short")

        sec_score = passed / checks if checks > 0 else 0.0
        by_section[sec_key] = {
            "score": round(sec_score * 100),
            "issues": issues,
        }
        weighted_total += sec_score * weight
        all_issues.extend([f"[{sec_key}] {i}" for i in issues])

    # Normalize to 0-1
    total_weight = sum(sc["weight"] for sc in SECTION_WEIGHTS.values())
    overall = weighted_total / total_weight if total_weight > 0 else 0.0

    return overall, all_issues, by_section


def compute_mis(match_dir: Path) -> Dict:
    """Compute MIS for a single match. Returns score breakdown."""
    # Load files
    report_path = match_dir / "report.json"
    facts_path = match_dir / "facts.json"
    tg_path = match_dir / "drafts" / "telegram.txt"
    x_path = match_dir / "drafts" / "x.txt"

    if not report_path.exists():
        return {"mis_score": 0.0, "error": "report.json not found"}

    with open(report_path) as f:
        report = json.load(f)

    facts = {}
    if facts_path.exists():
        with open(facts_path) as f:
            facts = json.load(f)

    telegram_text = ""
    if tg_path.exists():
        telegram_text = tg_path.read_text()

    x_text = ""
    if x_path.exists():
        x_text = x_path.read_text()

    # Score each component
    fc_score, fc_issues = _score_factual_correctness(report, telegram_text, x_text)
    depth_score, depth_issues = _score_depth(report)
    context_score, context_issues = _score_context(facts)
    read_score, read_issues = _score_readability(telegram_text, x_text)

    # Load context for narrative scoring
    context_data = {}
    ctx_path = match_dir / "context.json"
    if ctx_path.exists():
        with open(ctx_path) as f:
            context_data = json.load(f)

    narr_score, narr_issues, by_section = _score_narrative_quality(match_dir, context_data)

    # Weighted MIS
    mis = (
        fc_score * WEIGHTS["factual_correctness"]
        + depth_score * WEIGHTS["depth"]
        + context_score * WEIGHTS["context"]
        + read_score * WEIGHTS["readability"]
        + narr_score * WEIGHTS["narrative_quality"]
    )

    result = {
        "mis_score": round(mis, 3),
        "breakdown": {
            "factual_correctness": {
                "score": round(fc_score, 3),
                "weight": WEIGHTS["factual_correctness"],
                "issues": fc_issues,
            },
            "depth": {
                "score": round(depth_score, 3),
                "weight": WEIGHTS["depth"],
                "issues": depth_issues,
            },
            "context": {
                "score": round(context_score, 3),
                "weight": WEIGHTS["context"],
                "issues": context_issues,
            },
            "readability": {
                "score": round(read_score, 3),
                "weight": WEIGHTS["readability"],
                "issues": read_issues,
            },
            "narrative_quality": {
                "score": round(narr_score, 3),
                "weight": WEIGHTS["narrative_quality"],
                "issues": narr_issues,
            },
        },
        "checked_at": datetime.now().isoformat(),
    }

    # Add per-section breakdown if narrative exists
    if by_section:
        result["by_section"] = by_section

    return result


def check_round(round_dir: Path, threshold: float = 0.70, verbose: bool = False) -> Dict:
    """Run quality checks on all matches in a round."""
    matches_dir = round_dir / "matches"
    if not matches_dir.exists():
        print(f"No matches directory found in {round_dir}")
        return {}

    match_dirs = sorted([d for d in matches_dir.iterdir() if d.is_dir()])
    results = []

    print(f"\n{'='*70}")
    print(f"QUALITY CHECK | {round_dir.name} | Threshold: {threshold:.0%}")
    print(f"{'='*70}\n")
    print(f"  {'#':<3s} {'Match':<40s} {'MIS':>6s} {'Status':>8s}")
    print(f"  {'-'*57}")

    for i, md in enumerate(match_dirs, 1):
        mis_result = compute_mis(md)

        # Write per-match quality_checks.json
        with open(md / "quality_checks.json", "w") as f:
            json.dump(mis_result, f, indent=2)

        score = mis_result["mis_score"]
        passed = score >= threshold
        status = "PASS" if passed else "FAIL"
        icon = "+" if passed else "!"

        match_name = md.name.replace("_", " ")
        print(f"  {i:<3d} {match_name:<40s} {score:>5.0%} {icon:>3s} {status}")

        if verbose:
            for comp_name, comp in mis_result["breakdown"].items():
                if comp["issues"]:
                    for issue in comp["issues"]:
                        print(f"      [{comp_name}] {issue}")

        results.append({
            "match": md.name,
            "mis": score,
            "passed": passed,
        })

    # Aggregate
    scores = [r["mis"] for r in results]
    below = sum(1 for r in results if not r["passed"])

    quality_report = {
        "round": round_dir.name,
        "mean_mis": round(sum(scores) / len(scores), 3) if scores else 0,
        "min_mis": round(min(scores), 3) if scores else 0,
        "max_mis": round(max(scores), 3) if scores else 0,
        "matches_below_threshold": below,
        "threshold": threshold,
        "per_match": results,
        "checked_at": datetime.now().isoformat(),
    }

    # Write round-level quality report
    with open(round_dir / "quality_report.json", "w") as f:
        json.dump(quality_report, f, indent=2)

    print(f"\n  {'='*57}")
    print(f"  Mean MIS: {quality_report['mean_mis']:.0%} "
          f"(min: {quality_report['min_mis']:.0%}, max: {quality_report['max_mis']:.0%})")
    if below > 0:
        print(f"  WARNING: {below} match(es) below {threshold:.0%} threshold")
    else:
        print(f"  All matches above {threshold:.0%} threshold")
    print(f"  Quality report: {round_dir / 'quality_report.json'}")
    print(f"{'='*70}\n")

    return quality_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Quality check for generated rounds")
    parser.add_argument("round_name", help="Round folder name (e.g., PL_R28)")
    parser.add_argument("--threshold", type=float, default=0.70,
                        help="MIS threshold (default: 0.70)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed issues per match")

    args = parser.parse_args()

    rdir = ROUNDS_DIR / args.round_name
    if not rdir.exists():
        print(f"Round directory not found: {rdir}")
        return 1

    check_round(rdir, threshold=args.threshold, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
