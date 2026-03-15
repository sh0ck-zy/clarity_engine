"""
Rubric — formal scoring of match intelligence quality.

Two layers:
- Pre-match rubric (automatic, scored before match is played)
- Post-match rubric (scored after result is known)

Also contains deterministic confidence level computation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RubricResult:
    """Result of rubric scoring."""

    score: float = 0.0  # 0-100
    structural: float = 0.0
    content: float = 0.0
    data_foundation: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "structural": round(self.structural, 1),
            "content": round(self.content, 1),
            "data_foundation": round(self.data_foundation, 1),
            "details": self.details,
            "issues": self.issues,
        }


@dataclass
class PostMatchRubricResult:
    """Result of post-match rubric scoring (v1.6 — substance-focused)."""

    score: float = 0.0  # 0-100
    lean_correct: float = 0.0
    confidence_calibration: float = 0.0
    scenario_hit: float = 0.0
    risks_materialized: float = 0.0
    key_question_relevance: float = 0.0
    mechanisms_correct: float = 0.0  # v1.6: were the tactical mechanisms right?
    game_script_accuracy: float = 0.0  # v1.6: did the game follow the predicted script?
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "lean_correct": round(self.lean_correct, 1),
            "confidence_calibration": round(self.confidence_calibration, 1),
            "scenario_hit": round(self.scenario_hit, 1),
            "risks_materialized": round(self.risks_materialized, 1),
            "key_question_relevance": round(self.key_question_relevance, 1),
            "mechanisms_correct": round(self.mechanisms_correct, 1),
            "game_script_accuracy": round(self.game_script_accuracy, 1),
            "details": self.details,
        }


def score_pre_match_rubric(
    intelligence: Dict[str, Any],
    match_pack: Dict[str, Any],
    ml_anchor: Dict[str, Any],
    signals: Dict[str, Any],
    data_quality_score: float = 100.0,
) -> RubricResult:
    """
    Score match intelligence pre-match (0-100).

    Weights:
    - Structural (25%): required fields, evidence count, scenarios, players
    - Content (40%): specificity, differentiated confidence, plausible numbers
    - Data foundation (35%): data quality, completeness
    """
    result = RubricResult()

    # --- STRUCTURAL (25%) ---
    structural = 0.0
    details_structural = {}

    # Key question is tactical
    kq = intelligence.get("key_question", "")
    kq_score = 0
    if kq and "?" in kq and len(kq) > 30:
        kq_score = 100
    elif kq and "?" in kq:
        kq_score = 60
    elif kq:
        kq_score = 30
    structural += kq_score * 0.20
    details_structural["key_question"] = kq_score

    # Evidence 3+2
    ev_for = intelligence.get("evidence_for", [])
    ev_against = intelligence.get("evidence_against", [])
    ev_score = 0
    if len(ev_for) >= 3 and len(ev_against) >= 2:
        ev_score = 100
    elif len(ev_for) >= 2 and len(ev_against) >= 1:
        ev_score = 60
    else:
        ev_score = 20
        result.issues.append(f"Evidence: {len(ev_for)} for, {len(ev_against)} against (need 3+2)")
    structural += ev_score * 0.25
    details_structural["evidence_count"] = ev_score

    # Scenarios 2-3
    scenarios = intelligence.get("scenarios", [])
    sc_score = 0
    if 2 <= len(scenarios) <= 3:
        sc_score = 100
    elif len(scenarios) == 4:
        sc_score = 80
    elif len(scenarios) == 1:
        sc_score = 30
    structural += sc_score * 0.20
    details_structural["scenario_count"] = sc_score

    # Players 3+
    all_text = _collect_text(intelligence)
    player_names = _count_player_names(all_text)
    pl_score = 0
    if player_names >= 3:
        pl_score = 100
    elif player_names >= 2:
        pl_score = 60
    elif player_names >= 1:
        pl_score = 30
    structural += pl_score * 0.20
    details_structural["player_names"] = pl_score

    # Data in evidence
    all_ev = ev_for + ev_against
    with_data = sum(1 for e in all_ev if e.get("data"))
    data_score = (with_data / max(len(all_ev), 1)) * 100
    structural += data_score * 0.15
    details_structural["evidence_has_data"] = round(data_score, 1)

    result.structural = structural
    result.details["structural"] = details_structural

    # --- CONTENT (40%) ---
    content = 0.0
    details_content = {}

    # Lean specificity (not generic)
    lean = intelligence.get("lean", "")
    generic_leans = {"home win", "away win", "draw", "home", "away"}
    lean_score = 0
    if lean and lean.lower().strip() not in generic_leans and len(lean) > 20:
        lean_score = 100
    elif lean and len(lean) > 10:
        lean_score = 50
    else:
        lean_score = 10
        result.issues.append("Lean is too generic or short")
    content += lean_score * 0.30
    details_content["lean_specificity"] = lean_score

    # Confidence is differentiated (5-level)
    confidence = intelligence.get("confidence", "Medium")
    conf_score = 0
    if confidence in ("High", "Medium-High", "Medium-Low", "Low"):
        conf_score = 100  # differentiated
    elif confidence == "Medium":
        conf_score = 50  # safe default
    content += conf_score * 0.20
    details_content["confidence_differentiated"] = conf_score

    # Numbers are plausible (cross-check with match_pack)
    # Check if cited numbers roughly exist in the match_pack
    plausibility = _check_number_plausibility(intelligence, match_pack)
    content += plausibility * 0.25
    details_content["number_plausibility"] = round(plausibility, 1)

    # Signals consistent with analysis
    consistency = _check_signal_consistency(intelligence, signals)
    content += consistency * 0.25
    details_content["signal_consistency"] = round(consistency, 1)

    result.content = content
    result.details["content"] = details_content

    # --- DATA FOUNDATION (35%) ---
    data_found = 0.0
    details_data = {}

    # Data quality score (from data_quality.py)
    dq_contrib = data_quality_score
    data_found += dq_contrib * 0.50
    details_data["data_quality_score"] = round(data_quality_score, 1)

    # Match pack completeness
    completeness = _check_match_pack_completeness(match_pack)
    data_found += completeness * 0.30
    details_data["match_pack_completeness"] = round(completeness, 1)

    # ML anchor present
    ml_present = 100 if ml_anchor and ml_anchor.get("probabilities") else 0
    data_found += ml_present * 0.20
    details_data["ml_anchor_present"] = ml_present

    result.data_foundation = data_found
    result.details["data_foundation"] = details_data

    # --- FINAL SCORE ---
    result.score = (
        result.structural * 0.25
        + result.content * 0.40
        + result.data_foundation * 0.35
    )

    return result


def score_post_match_rubric(
    intelligence: Dict[str, Any],
    result_data: Dict[str, Any],
) -> PostMatchRubricResult:
    """
    Score match intelligence post-match (0-100).

    v1.7 weights:
    - Lean direction: 20% — was H/D/A right?
    - Confidence calibration: 25% — high + wrong = 0, high + right = 100, low = 50
    - First goal prediction: 15% — did game_state_tree first_goal align?
    - Game character: 15% — did we predict open/tight correctly?
    - Possession read: 10% — did we predict who'd dominate ball?
    - Decision quality: 15% — was PICK profitable? was NO_BET correct?

    result_data should contain:
    - actual_result: "H" | "D" | "A"
    - home_score: int, away_score: int
    - first_goal_team: "home" | "away" | None
    - game_character: "open" | "tight"
    - possession_winner: "home" | "away" | "even"
    - decision_quality: float (0-100, from decision engine scoring)
    """
    rubric = PostMatchRubricResult()
    actual = result_data.get("actual_result", "")

    if not actual:
        return rubric

    # --- LEAN DIRECTION CORRECT (20%) ---
    lean = intelligence.get("lean", "").lower()
    lean_dir = _infer_lean_direction(lean)
    lean_correct = 100 if lean_dir == actual else 0
    rubric.lean_correct = lean_correct
    rubric.details["lean_direction"] = lean_dir
    rubric.details["actual_result"] = actual

    # --- CONFIDENCE CALIBRATION (25%) ---
    confidence = intelligence.get("confidence", "Medium")
    if lean_correct == 100:
        cal = {"High": 100, "Medium-High": 90, "Medium": 70, "Medium-Low": 60, "Low": 50}
    else:
        cal = {"High": 0, "Medium-High": 20, "Medium": 50, "Medium-Low": 70, "Low": 90}
    rubric.confidence_calibration = cal.get(confidence, 50)

    # --- FIRST GOAL PREDICTION (15%) ---
    # Check if game_state_tree predicted first goal side correctly
    first_goal_score = 50  # neutral default
    actual_first_goal = result_data.get("first_goal_team")
    if actual_first_goal:
        scenarios = intelligence.get("scenarios", [])
        most_likely = [s for s in scenarios if s.get("likelihood") == "most likely"]
        if most_likely:
            ml_desc = most_likely[0].get("description", "").lower()
            if actual_first_goal == "home" and ("home" in ml_desc and ("scor" in ml_desc or "goal" in ml_desc or "lead" in ml_desc)):
                first_goal_score = 100
            elif actual_first_goal == "away" and ("away" in ml_desc and ("scor" in ml_desc or "goal" in ml_desc or "lead" in ml_desc)):
                first_goal_score = 100
            else:
                first_goal_score = 20

    # --- GAME CHARACTER (15%) ---
    game_char_score = 50  # neutral default
    actual_game_char = result_data.get("game_character")
    if actual_game_char:
        main_read = intelligence.get("main_read", "").lower()
        open_words = ["open", "goals", "attacking", "high-scoring"]
        tight_words = ["tight", "low-scoring", "defensive", "cagey"]
        open_s = sum(1 for w in open_words if w in main_read)
        tight_s = sum(1 for w in tight_words if w in main_read)
        predicted_char = "open" if open_s > tight_s else ("tight" if tight_s > open_s else None)
        if predicted_char == actual_game_char:
            game_char_score = 100
        elif predicted_char is not None:
            game_char_score = 20

    # --- POSSESSION READ (10%) ---
    poss_score = 50  # neutral default
    actual_poss_winner = result_data.get("possession_winner")
    if actual_poss_winner and actual_poss_winner != "even":
        main_read = intelligence.get("main_read", "").lower()
        if actual_poss_winner == "home" and ("home" in main_read and "possess" in main_read or "control" in main_read or "dominat" in main_read):
            poss_score = 100
        elif actual_poss_winner == "away" and ("away" in main_read and "possess" in main_read or "transition" in main_read):
            poss_score = 100

    # --- DECISION QUALITY (15%) ---
    decision_score = result_data.get("decision_quality", 50.0)

    # Store sub-scores for backward compat
    rubric.mechanisms_correct = first_goal_score
    rubric.game_script_accuracy = game_char_score
    rubric.scenario_hit = first_goal_score
    rubric.risks_materialized = poss_score
    rubric.key_question_relevance = decision_score

    # --- FINAL SCORE (v1.7 weights) ---
    rubric.score = (
        rubric.lean_correct * 0.20
        + rubric.confidence_calibration * 0.25
        + first_goal_score * 0.15
        + game_char_score * 0.15
        + poss_score * 0.10
        + decision_score * 0.15
    )

    return rubric


def compute_confidence_level(
    ml_anchor: Dict[str, Any],
    match_signals: Dict[str, Any],
    data_quality_score: float,
) -> str:
    """
    Compute confidence level deterministically.

    Returns one of: High, Medium-High, Medium, Medium-Low, Low.
    Based on ML margin, signals, and data quality — NOT asked to the LLM.
    """
    signals = ml_anchor.get("signals", {})
    margin = signals.get("margin_top2", 0.0) or 0.0
    entropy = signals.get("entropy_norm", 1.0) or 1.0

    match_sigs = match_signals.get("signals", {})
    draw_pressure = match_sigs.get("draw_pressure_risk", False)

    # Use ML confidence justification as proxy for form gap
    ml_conf = match_sigs.get("ml_confidence_justified", "weakly_supported")
    form_gap = {"well_supported": 4, "somewhat_supported": 2, "weakly_supported": 0}.get(ml_conf, 0)

    # Thresholds calibrated to actual model output distribution:
    #   entropy p25=0.956, p50=0.980, p75=0.993, p90=0.998
    #   margin  p25=0.029, p50=0.061, p75=0.110, p90=0.157

    # Low: true coin flip (top-10% flattest) or bad data
    if entropy > 0.997 or data_quality_score < 50:
        return "Low"

    # Medium-Low: very tight margin (bottom quartile) or poor data
    if margin < 0.03 or data_quality_score < 65:
        return "Medium-Low"

    # High: clear separation (top decile margin + below-median entropy + strong form)
    if margin > 0.15 and entropy < 0.96 and form_gap >= 3 and data_quality_score >= 85:
        return "High"

    # Medium-High: above-median margin with good data
    if margin > 0.10 and data_quality_score >= 80:
        return "Medium-High"

    if margin > 0.06 and entropy < 0.97 and not draw_pressure and data_quality_score >= 75:
        return "Medium-High"

    return "Medium"


# --- HELPERS ---

def _collect_text(intel: Dict) -> str:
    """Collect all text from intelligence for analysis."""
    parts = [
        intel.get("key_question", ""),
        intel.get("main_read", ""),
        intel.get("lean", ""),
    ]
    for e in intel.get("evidence_for", []):
        parts.append(e.get("claim", ""))
        parts.append(e.get("data", ""))
    for e in intel.get("evidence_against", []):
        parts.append(e.get("claim", ""))
        parts.append(e.get("data", ""))
    for s in intel.get("scenarios", []):
        parts.append(s.get("description", ""))
    for r in intel.get("risks", []):
        parts.append(r if isinstance(r, str) else "")
    return " ".join(parts)


def _count_player_names(text: str) -> int:
    """Count unique player names in text (heuristic)."""
    name_pattern = r"[A-Z][a-zéèêëàâäùûüôöîïñ]+(?:\s+(?:de\s+)?[A-Z][a-zéèêëàâäùûüôöîïñ]+)*"
    names = re.findall(name_pattern, text)
    non_names = {
        "Home", "Away", "Draw", "Medium", "High", "Low", "Strong",
        "Moderate", "Weak", "Control", "Transition", "Stalemate",
        "The", "This", "That", "Most", "Score", "First",
    }
    player_names = {n for n in names if n not in non_names and len(n) > 3}
    return len(player_names)


def _check_number_plausibility(intel: Dict, match_pack: Dict) -> float:
    """Check if numbers cited in intelligence roughly exist in match_pack data."""
    # Serialize match_pack numbers for lookup
    pack_text = str(match_pack)
    all_evidence = intel.get("evidence_for", []) + intel.get("evidence_against", [])

    if not all_evidence:
        return 50.0  # neutral

    found = 0
    total = 0
    for e in all_evidence:
        data = e.get("data", "")
        numbers = re.findall(r"\d+\.?\d*", data)
        for num in numbers:
            total += 1
            if num in pack_text:
                found += 1

    if total == 0:
        return 50.0

    return (found / total) * 100


def _check_signal_consistency(intel: Dict, signals: Dict) -> float:
    """Check if intelligence analysis is consistent with computed signals."""
    sigs = signals.get("signals", {})
    if not sigs:
        return 50.0

    score = 50.0  # start neutral
    lean = intel.get("lean", "").lower()

    # If draw_pressure_risk is true but lean is strongly one-sided, penalize
    if sigs.get("draw_pressure_risk") and "draw" not in lean:
        score -= 10

    # If upset_potential but lean ignores it
    if sigs.get("upset_potential") and "upset" not in lean and "risk" not in lean:
        score -= 5

    # If home_territorial_edge is strong and lean matches, reward
    if sigs.get("home_territorial_edge") and ("home" in lean or "control" in lean):
        score += 15

    # If away_transition_threat and lean mentions it
    if sigs.get("away_transition_threat") and ("transition" in lean or "counter" in lean):
        score += 10

    return max(0, min(100, score))


def _check_match_pack_completeness(match_pack: Dict) -> float:
    """Check how complete the match_pack is."""
    score = 0.0
    checks = [
        ("home", "state"),
        ("away", "state"),
        ("home", "key_players"),
        ("away", "key_players"),
        ("matchup",),
        ("game_state_tree",),
    ]
    for keys in checks:
        current = match_pack
        for k in keys:
            current = current.get(k, {}) if isinstance(current, dict) else {}
        if current:
            score += 100 / len(checks)

    return score


def _infer_lean_direction(text: str) -> str:
    """Infer H/D/A direction from text."""
    text_lower = text.lower()
    home_words = ["home", "host", "favourite", "favorite", "control", "dominat"]
    away_words = ["away", "visitor", "underdog", "upset"]
    draw_words = ["draw", "stalemate", "even", "balanced", "tight", "share"]

    home_score = sum(1 for w in home_words if w in text_lower)
    away_score = sum(1 for w in away_words if w in text_lower)
    draw_score = sum(1 for w in draw_words if w in text_lower)

    if draw_score > home_score and draw_score > away_score:
        return "D"
    if away_score > home_score:
        return "A"
    return "H"
