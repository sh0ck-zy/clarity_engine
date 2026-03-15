"""
Match Signals — derived signals from match_pack + ml_anchor.

Rule-based, deterministic, no LLM. Makes reasoning traceable and debuggable.
If match_intelligence says "NEC's transition threat is the main risk" but
match_signals shows away_transition_threat: false, we know the LLM hallucinated.
"""

from __future__ import annotations

from typing import Any, Dict


def _get_nested(d: Dict, *keys, default=None):
    """Safely get a nested dict value."""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current


def compute_match_signals(
    match_pack: Dict[str, Any],
    ml_anchor: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute derived match signals from match_pack and ml_anchor.

    Returns a dict ready to be saved as match_signals.json.
    All signals are rule-based — no LLM calls.
    """
    match_id = match_pack.get("fixture", {}).get("fixture_id", "")

    # Extract key data points
    home_state = _get_nested(match_pack, "home", "state", default={})
    away_state = _get_nested(match_pack, "away", "state", default={})
    home_form = _get_nested(match_pack, "home", "form_detail", default={})
    away_form = _get_nested(match_pack, "away", "form_detail", default={})
    matchup = match_pack.get("matchup", {})

    # ML anchor signals
    margin_top2 = _get_nested(ml_anchor, "signals", "margin_top2", default=0.0)
    entropy_norm = _get_nested(ml_anchor, "signals", "entropy_norm", default=1.0)
    predicted = ml_anchor.get("predicted_result", "")

    # --- COMPUTE SIGNALS ---
    signals = {}
    derivations = {}

    # 1. Home territorial edge
    home_xg_diff = _get_nested(home_state, "form", "xg_diff_last5", default=0.0) or 0.0
    home_possession = _get_nested(home_state, "style", "avg_possession", default=50.0) or 50.0
    signals["home_territorial_edge"] = home_xg_diff > 1.0 and home_possession > 55
    signals["home_territorial_strength"] = _strength_label(
        home_xg_diff, thresholds=(0.5, 1.5, 3.0)
    )
    derivations["home_territorial_edge"] = (
        f"xg_diff_last5={home_xg_diff:.1f} > 1.0 AND possession={home_possession:.1f}% > 55"
    )

    # 2. Away transition threat
    away_goals_last5 = _get_nested(away_form, "goals", "scored", default=0) or 0
    away_xg_last5 = _get_nested(away_form, "xg", "xg_for", default=0.0) or 0.0
    # Transition threat: scoring despite lower possession
    away_possession = _get_nested(away_state, "style", "avg_possession", default=50.0) or 50.0
    is_low_possession = away_possession < 48
    scores_despite = away_goals_last5 >= 5
    signals["away_transition_threat"] = is_low_possession and scores_despite
    signals["away_transition_strength"] = _strength_label(
        away_goals_last5 if is_low_possession else 0, thresholds=(3, 5, 8)
    )
    derivations["away_transition_threat"] = (
        f"away_possession={away_possession:.1f}% < 48 AND goals_last5={away_goals_last5} >= 5"
    )

    # 3. Draw pressure risk
    home_form_pts = _get_nested(home_state, "form", "form_points", default=0) or 0
    away_form_pts = _get_nested(away_state, "form", "form_points", default=0) or 0
    form_close = abs(home_form_pts - away_form_pts) <= 2
    high_entropy = entropy_norm > 0.90
    signals["draw_pressure_risk"] = high_entropy or form_close
    derivations["draw_pressure_risk"] = (
        f"entropy_norm={entropy_norm:.2f} > 0.90 OR "
        f"|form_pts_diff|={abs(home_form_pts - away_form_pts)} <= 2"
    )

    # 4. Fragile home edge
    home_cs_last5 = _get_nested(home_state, "form", "clean_sheets_last5", default=0) or 0
    signals["fragile_home_edge"] = margin_top2 < 0.15 and home_cs_last5 <= 1
    derivations["fragile_home_edge"] = (
        f"margin_top2={margin_top2:.2f} < 0.15 AND home_clean_sheets_last5={home_cs_last5} <= 1"
    )

    # 5. Venue advantage (form_momentum and key_absence_impact removed — already in rubric)
    home_venue_pts = _get_nested(home_state, "home_away", "home_points", default=0) or 0
    home_played = _get_nested(home_state, "position", "played", default=1) or 1
    home_ppg = home_venue_pts / max(home_played / 2, 1)  # approximate home games
    signals["venue_advantage"] = _strength_label(
        home_ppg, thresholds=(1.5, 2.0, 2.5)
    )
    derivations["venue_advantage"] = (
        f"home_venue_points={home_venue_pts}, approx_ppg={home_ppg:.2f}"
    )

    # 6. Upset potential (style_clash_type removed — already in rubric)
    is_home_fav = predicted == "H"
    away_form_strong = away_form_pts >= 10
    home_defense_weak = home_cs_last5 <= 1
    signals["upset_potential"] = (
        is_home_fav and away_form_strong and home_defense_weak
    )
    derivations["upset_potential"] = (
        f"home_fav={is_home_fav} AND away_form_pts={away_form_pts} >= 10 "
        f"AND home_cs_last5={home_cs_last5} <= 1"
    )

    # 7. Confidence calibration
    signals["ml_confidence_justified"] = _assess_ml_confidence(
        margin_top2, entropy_norm, home_form_pts, away_form_pts
    )

    return {
        "schema_version": "1.7",
        "match_id": match_id,
        "signals": signals,
        "derived_from": derivations,
    }


def _strength_label(value: float, thresholds: tuple = (1.0, 2.0, 3.0)) -> str:
    """Convert a numeric value to a qualitative strength label."""
    low, mid, high = thresholds
    if value >= high:
        return "strong"
    if value >= mid:
        return "moderate"
    if value >= low:
        return "weak"
    return "none"


def _assess_ml_confidence(
    margin: float, entropy: float, home_form: int, away_form: int
) -> str:
    """Assess whether ML confidence level seems justified by the data."""
    form_gap = abs(home_form - away_form)

    # High margin + low entropy + big form gap = justified
    if margin > 0.20 and entropy < 0.85 and form_gap >= 4:
        return "well_supported"
    # Decent margin but data is noisy
    if margin > 0.10:
        return "somewhat_supported"
    # Low margin = hard to be confident
    return "weakly_supported"


def compute_ml_divergence_context(
    match_pack: Dict[str, Any],
    ml_anchor: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute structured reasons why the MI lean might diverge from ML prediction.

    Returns a dict with potential divergence factors:
    - key_injuries: high-impact absences not captured by the model
    - form_shift: recent trajectory changes
    - tactical_mismatch: style clash factors
    """
    reasons = []

    # 1. Key injuries not in model features
    home_injuries = match_pack.get("home", {}).get("injuries", [])
    away_injuries = match_pack.get("away", {}).get("injuries", [])
    high_impact = []
    for side, injuries in [("home", home_injuries), ("away", away_injuries)]:
        for inj in injuries:
            if inj.get("impact") == "High":
                high_impact.append(f"{side}: {inj.get('name', '?')} ({inj.get('position', '?')})")
    if high_impact:
        reasons.append({
            "factor": "key_injuries",
            "description": f"High-impact absences: {', '.join(high_impact)}",
            "strength": "strong" if len(high_impact) >= 2 else "moderate",
        })

    # 2. Form shift (trajectory changing direction)
    home_trend = _get_nested(match_pack, "home", "state", "trajectory", "form_trend", default="stable")
    away_trend = _get_nested(match_pack, "away", "state", "trajectory", "form_trend", default="stable")
    predicted = ml_anchor.get("predicted_result", "")

    if predicted == "H" and home_trend == "declining":
        reasons.append({
            "factor": "form_shift",
            "description": "Home team predicted to win but form is declining",
            "strength": "moderate",
        })
    if predicted == "A" and away_trend == "declining":
        reasons.append({
            "factor": "form_shift",
            "description": "Away team predicted to win but form is declining",
            "strength": "moderate",
        })
    if predicted == "H" and away_trend == "improving":
        reasons.append({
            "factor": "form_shift",
            "description": "Away team improving — ML may underweight recent momentum",
            "strength": "weak",
        })

    # 3. Tactical mismatch
    home_poss = _get_nested(match_pack, "home", "state", "style", "avg_possession", default=50.0) or 50.0
    away_poss = _get_nested(match_pack, "away", "state", "style", "avg_possession", default=50.0) or 50.0
    poss_diff = abs(home_poss - away_poss)

    if poss_diff > 10:
        reasons.append({
            "factor": "tactical_mismatch",
            "description": (
                f"Large possession gap ({home_poss:.0f}% vs {away_poss:.0f}%) — "
                f"style clash may create unpredictable dynamics"
            ),
            "strength": "weak",
        })

    return {
        "divergence_reasons": reasons,
        "has_strong_divergence": any(r["strength"] == "strong" for r in reasons),
    }
