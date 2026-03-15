"""
Tactical Rubric — structured representation of match factors.

Fills ~20 tactical factors for EACH match BEFORE the LLM generates the narrative.
The LLM sees the game through this rubric, not raw numbers.

All computations are deterministic — no LLM calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _get(d: Dict, *keys, default=None):
    """Safely navigate nested dicts."""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current


def _rating(value: float, low: float, mid: float, high: float) -> str:
    """Convert numeric value to qualitative rating."""
    if value >= high:
        return "high"
    if value >= mid:
        return "moderate"
    if value >= low:
        return "low"
    return "very_low"


def _score_0_10(value: float, low: float, high: float) -> int:
    """Map a value to a 0-10 integer score."""
    if value <= low:
        return 0
    if value >= high:
        return 10
    return round((value - low) / (high - low) * 10)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_tactical_rubric(
    match_pack: Dict[str, Any],
    ml_anchor: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a tactical rubric for a match from match_pack data.

    Returns a dict with ~20 factors, each containing:
    - score (0-10)
    - rating (qualitative)
    - evidence (what data backs it)
    - relevance (why it matters for this game)
    """
    home = match_pack.get("home", {})
    away = match_pack.get("away", {})
    fixture = match_pack.get("fixture", {})
    matchup = match_pack.get("matchup", {})

    home_state = home.get("state", {})
    away_state = away.get("state", {})
    home_form = home.get("form_detail", {})
    away_form = away.get("form_detail", {})

    rubric = {}

    # =====================================================================
    # A. CONTEXT FACTORS
    # =====================================================================

    rubric["form_momentum"] = _compute_form_momentum(home_state, away_state)
    rubric["schedule_strength"] = _compute_schedule_strength(
        match_pack.get("recent_matches", {}), home_state, away_state
    )
    rubric["rest_days_delta"] = _compute_rest_delta(match_pack)
    rubric["key_absences"] = _compute_key_absences(home, away)

    # =====================================================================
    # B. ATTACK vs DEFENSE MATCHUP
    # =====================================================================

    rubric["creation_quality"] = _compute_creation_quality(home, away)
    rubric["transition_threat"] = _compute_transition_threat(home, away, home_state, away_state)
    rubric["set_piece_danger"] = _compute_set_piece_danger(home, away, home_state, away_state)
    rubric["defensive_solidity"] = _compute_defensive_solidity(home, away, home_state, away_state)

    # =====================================================================
    # C. TACTICAL MATCHUP
    # =====================================================================

    rubric["possession_vs_block"] = _compute_possession_vs_block(home_state, away_state)
    rubric["press_vs_buildup"] = _compute_press_vs_buildup(home, away, home_state, away_state)
    rubric["physical_intensity"] = _compute_physical_intensity(home_state, away_state)
    rubric["style_clash"] = _compute_style_clash(home_state, away_state, matchup)

    # =====================================================================
    # D. GAME STATE TENDENCIES
    # =====================================================================

    rubric["first_goal_tendency"] = _compute_first_goal_tendency(home_state, away_state)
    rubric["reaction_to_adversity"] = _compute_reaction_to_adversity(home_state, away_state)
    rubric["game_closing"] = _compute_game_closing(home_state, away_state)
    rubric["goals_expected"] = _compute_goals_expected(home, away, home_state, away_state)

    # =====================================================================
    # E. KEY MATCHUP SUMMARY
    # =====================================================================

    rubric["home_edge_factors"] = _compute_edge_factors(rubric, "home")
    rubric["away_edge_factors"] = _compute_edge_factors(rubric, "away")
    rubric["decisive_factors"] = _compute_decisive_factors(rubric)

    return {
        "schema_version": "1.6",
        "match_id": fixture.get("fixture_id", ""),
        "factors": rubric,
    }


# =========================================================================
# A. CONTEXT
# =========================================================================

def _compute_form_momentum(home_state: Dict, away_state: Dict) -> Dict:
    """Form trajectory and momentum for both teams."""
    home_trend = _get(home_state, "trajectory", "form_trend", default="stable")
    away_trend = _get(away_state, "trajectory", "form_trend", default="stable")
    home_form_pts = _get(home_state, "form", "form_points", default=0) or 0
    away_form_pts = _get(away_state, "form", "form_points", default=0) or 0
    home_form_str = _get(home_state, "form", "form_string", default="") or ""
    away_form_str = _get(away_state, "form", "form_string", default="") or ""

    # Momentum score: improving = bonus, declining = penalty
    momentum_map = {"improving": 2, "stable": 0, "declining": -2}
    home_momentum = momentum_map.get(home_trend, 0)
    away_momentum = momentum_map.get(away_trend, 0)
    delta = home_momentum - away_momentum

    return {
        "home_trend": home_trend,
        "away_trend": away_trend,
        "home_form_points": home_form_pts,
        "away_form_points": away_form_pts,
        "home_form_string": home_form_str,
        "away_form_string": away_form_str,
        "momentum_delta": delta,
        "edge": "home" if delta > 0 else "away" if delta < 0 else "neutral",
        "evidence": f"Home {home_form_str} ({home_form_pts}/15, {home_trend}) vs Away {away_form_str} ({away_form_pts}/15, {away_trend})",
    }


def _compute_schedule_strength(
    recent_matches: Dict, home_state: Dict, away_state: Dict
) -> Dict:
    """Strength of recent opponents (were wins against strong or weak teams?)."""
    home_pos = _get(home_state, "position", "position", default=10) or 10
    away_pos = _get(away_state, "position", "position", default=10) or 10

    # Use recent matches to estimate opponent quality
    home_recent = recent_matches.get("home", [])
    away_recent = recent_matches.get("away", [])

    # Simple heuristic: if recent opponents are from top half, schedule was hard
    home_difficulty = "unknown"
    away_difficulty = "unknown"

    if home_recent:
        home_difficulty = "moderate"  # default; would need opponent positions for precision
    if away_recent:
        away_difficulty = "moderate"

    return {
        "home_schedule_difficulty": home_difficulty,
        "away_schedule_difficulty": away_difficulty,
        "home_position": home_pos,
        "away_position": away_pos,
        "position_gap": abs(home_pos - away_pos),
        "edge": "home" if home_pos < away_pos else "away" if away_pos < home_pos else "neutral",
        "evidence": f"Home {home_pos}th vs Away {away_pos}th (gap: {abs(home_pos - away_pos)})",
    }


def _compute_rest_delta(match_pack: Dict) -> Dict:
    """Rest days between matches (derived from recent matches if available)."""
    # We don't have explicit rest days; derive from recent match dates if available
    home_recent = match_pack.get("recent_matches", {}).get("home", [])
    away_recent = match_pack.get("recent_matches", {}).get("away", [])

    home_last_round = home_recent[0].get("round_number", 0) if home_recent else 0
    away_last_round = away_recent[0].get("round_number", 0) if away_recent else 0
    current_round = match_pack.get("fixture", {}).get("round_number", 0)

    home_gap = current_round - home_last_round if home_last_round else None
    away_gap = current_round - away_last_round if away_last_round else None

    return {
        "home_rounds_since_last": home_gap,
        "away_rounds_since_last": away_gap,
        "edge": "neutral",  # can't determine without dates
        "evidence": f"Home gap: {home_gap} rounds, Away gap: {away_gap} rounds",
    }


def _compute_key_absences(home: Dict, away: Dict) -> Dict:
    """Impact of missing players."""
    home_injuries = home.get("injuries", [])
    away_injuries = away.get("injuries", [])

    home_high = [i for i in home_injuries if i.get("impact") == "High"]
    away_high = [i for i in away_injuries if i.get("impact") == "High"]

    home_names = [i.get("name", "?") for i in home_high]
    away_names = [i.get("name", "?") for i in away_high]

    home_impact = len(home_high)
    away_impact = len(away_high)

    edge = "neutral"
    if home_impact > away_impact:
        edge = "away"  # home loses more
    elif away_impact > home_impact:
        edge = "home"

    return {
        "home_missing_high_impact": home_names,
        "away_missing_high_impact": away_names,
        "home_total_missing": len(home_injuries),
        "away_total_missing": len(away_injuries),
        "edge": edge,
        "score": _score_0_10(abs(home_impact - away_impact), 0, 3),
        "evidence": f"Home missing {len(home_injuries)} ({home_impact} high impact: {', '.join(home_names) or 'none'}), Away missing {len(away_injuries)} ({away_impact} high impact: {', '.join(away_names) or 'none'})",
    }


# =========================================================================
# B. ATTACK vs DEFENSE MATCHUP
# =========================================================================

def _compute_creation_quality(home: Dict, away: Dict) -> Dict:
    """Quality of chance creation (xG, attack profile)."""
    home_xg = _get(home, "form_detail", "xg", "xg_for", default=0.0) or 0.0
    away_xg = _get(away, "form_detail", "xg", "xg_for", default=0.0) or 0.0
    home_attack = home.get("attack_profile", {})
    away_attack = away.get("attack_profile", {})
    home_xg_pg = home_attack.get("xg_per_game", 0) or 0
    away_xg_pg = away_attack.get("xg_per_game", 0) or 0

    return {
        "home_xg_last5": round(home_xg, 2),
        "away_xg_last5": round(away_xg, 2),
        "home_xg_per_game": round(home_xg_pg, 2),
        "away_xg_per_game": round(away_xg_pg, 2),
        "home_attack_rating": home_attack.get("rating", "unknown"),
        "away_attack_rating": away_attack.get("rating", "unknown"),
        "edge": "home" if home_xg_pg > away_xg_pg + 0.2 else "away" if away_xg_pg > home_xg_pg + 0.2 else "neutral",
        "evidence": f"Home {home_xg_pg:.2f} xG/game ({home_attack.get('rating', '?')}) vs Away {away_xg_pg:.2f} xG/game ({away_attack.get('rating', '?')})",
    }


def _compute_transition_threat(
    home: Dict, away: Dict, home_state: Dict, away_state: Dict
) -> Dict:
    """Counter-attack and transition danger."""
    home_poss = _get(home_state, "style", "avg_possession", default=50.0) or 50.0
    away_poss = _get(away_state, "style", "avg_possession", default=50.0) or 50.0

    home_goals = _get(home, "form_detail", "goals", "scored", default=0) or 0
    away_goals = _get(away, "form_detail", "goals", "scored", default=0) or 0

    # Teams with low possession but high goals = transition threat
    home_is_transition = home_poss < 48 and home_goals >= 5
    away_is_transition = away_poss < 48 and away_goals >= 5

    threat_home = "high" if home_is_transition else "moderate" if home_goals >= 4 else "low"
    threat_away = "high" if away_is_transition else "moderate" if away_goals >= 4 else "low"

    return {
        "home_transition_threat": threat_home,
        "away_transition_threat": threat_away,
        "home_possession": round(home_poss, 1),
        "away_possession": round(away_poss, 1),
        "home_goals_last5": home_goals,
        "away_goals_last5": away_goals,
        "matchup_note": _transition_matchup_note(home_poss, away_poss, home_is_transition, away_is_transition),
        "evidence": f"Home {home_poss:.0f}% poss, {home_goals} goals last 5 ({threat_home}) | Away {away_poss:.0f}% poss, {away_goals} goals last 5 ({threat_away})",
    }


def _transition_matchup_note(
    home_poss: float, away_poss: float,
    home_trans: bool, away_trans: bool
) -> str:
    """Generate note about how transition dynamics interact."""
    if home_poss > 55 and away_trans:
        return "HOME dominates ball, AWAY dangerous on transition — classic counter-attack setup"
    if away_poss > 55 and home_trans:
        return "AWAY dominates ball, HOME dangerous on transition — reversed counter-attack setup"
    if home_trans and away_trans:
        return "Both teams effective on transition — open, end-to-end game likely"
    return "No strong transition dynamic"


def _compute_set_piece_danger(
    home: Dict, away: Dict, home_state: Dict, away_state: Dict
) -> Dict:
    """Set piece threat level (derived from available data)."""
    # We don't have direct set piece data, but can infer from clean sheets
    # and goals conceded patterns
    home_cs = _get(home_state, "form", "clean_sheets_last5", default=0) or 0
    away_cs = _get(away_state, "form", "clean_sheets_last5", default=0) or 0

    # Heuristic: teams that concede a lot but have good xG may be vulnerable to set pieces
    home_defense = home.get("defense_profile", {})
    away_defense = away.get("defense_profile", {})

    return {
        "home_clean_sheets_last5": home_cs,
        "away_clean_sheets_last5": away_cs,
        "note": "Set piece data limited — inferred from defensive profiles",
        "edge": "neutral",
        "evidence": f"Home {home_cs} clean sheets last 5, Away {away_cs} clean sheets last 5",
    }


def _compute_defensive_solidity(
    home: Dict, away: Dict, home_state: Dict, away_state: Dict
) -> Dict:
    """How solid is each team's defense?"""
    home_xga = _get(home_state, "form", "xg_against_last5", default=0.0) or 0.0
    away_xga = _get(away_state, "form", "xg_against_last5", default=0.0) or 0.0
    home_cs = _get(home_state, "form", "clean_sheets_last5", default=0) or 0
    away_cs = _get(away_state, "form", "clean_sheets_last5", default=0) or 0
    home_def = home.get("defense_profile", {})
    away_def = away.get("defense_profile", {})
    home_xga_pg = home_def.get("xg_against_per_game", 0) or 0
    away_xga_pg = away_def.get("xg_against_per_game", 0) or 0

    # Lower xGA = better defense
    edge = "neutral"
    if home_xga_pg < away_xga_pg - 0.2:
        edge = "home"
    elif away_xga_pg < home_xga_pg - 0.2:
        edge = "away"

    return {
        "home_xga_per_game": round(home_xga_pg, 2),
        "away_xga_per_game": round(away_xga_pg, 2),
        "home_xga_last5": round(home_xga, 2),
        "away_xga_last5": round(away_xga, 2),
        "home_clean_sheets": home_cs,
        "away_clean_sheets": away_cs,
        "home_defense_rating": home_def.get("rating", "unknown"),
        "away_defense_rating": away_def.get("rating", "unknown"),
        "edge": edge,
        "evidence": f"Home {home_xga_pg:.2f} xGA/game, {home_cs} CS ({home_def.get('rating', '?')}) | Away {away_xga_pg:.2f} xGA/game, {away_cs} CS ({away_def.get('rating', '?')})",
    }


# =========================================================================
# C. TACTICAL MATCHUP
# =========================================================================

def _compute_possession_vs_block(home_state: Dict, away_state: Dict) -> Dict:
    """Possession team vs low block dynamic."""
    home_poss = _get(home_state, "style", "avg_possession", default=50.0) or 50.0
    away_poss = _get(away_state, "style", "avg_possession", default=50.0) or 50.0
    poss_diff = abs(home_poss - away_poss)

    dynamic = "balanced"
    if home_poss > 55 and away_poss < 47:
        dynamic = "home_possession_vs_away_block"
    elif away_poss > 55 and home_poss < 47:
        dynamic = "away_possession_vs_home_block"
    elif home_poss > 52 and away_poss > 52:
        dynamic = "both_want_ball"
    elif home_poss < 48 and away_poss < 48:
        dynamic = "both_direct"

    return {
        "home_possession": round(home_poss, 1),
        "away_possession": round(away_poss, 1),
        "possession_gap": round(poss_diff, 1),
        "dynamic": dynamic,
        "note": _possession_dynamic_note(dynamic, home_poss, away_poss),
        "evidence": f"Home {home_poss:.1f}% vs Away {away_poss:.1f}% possession (gap: {poss_diff:.1f}%)",
    }


def _possession_dynamic_note(dynamic: str, home_poss: float, away_poss: float) -> str:
    """Explain the possession dynamic."""
    notes = {
        "home_possession_vs_away_block": "Home will dominate ball; key is whether they can break down a compact block. Expect patient build-up vs quick transitions.",
        "away_possession_vs_home_block": "Away team wants the ball despite being visitors — unusual dynamic. Home will sit and counter.",
        "both_want_ball": "Both teams want possession — expect a midfield battle. Whoever controls tempo likely controls the game.",
        "both_direct": "Neither team dominant in possession — direct, physical game likely. Set pieces and second balls matter more.",
        "balanced": "Balanced possession profiles — game could go either way tactically.",
    }
    return notes.get(dynamic, "")


def _compute_press_vs_buildup(
    home: Dict, away: Dict, home_state: Dict, away_state: Dict
) -> Dict:
    """Pressing intensity vs build-up quality."""
    home_style = home.get("style_profile", {})
    away_style = away.get("style_profile", {})

    # Use style classification if available
    home_classification = home_style.get("classification", "")
    away_classification = away_style.get("classification", "")

    return {
        "home_style": home_classification or "unknown",
        "away_style": away_classification or "unknown",
        "note": f"Home plays {home_classification or 'unknown'} vs Away plays {away_classification or 'unknown'}",
        "evidence": f"Home style: {home_classification or 'not classified'}, Away style: {away_classification or 'not classified'}",
    }


def _compute_physical_intensity(home_state: Dict, away_state: Dict) -> Dict:
    """Expected physical intensity of the match."""
    # Infer from possession and league position
    home_poss = _get(home_state, "style", "avg_possession", default=50.0) or 50.0
    away_poss = _get(away_state, "style", "avg_possession", default=50.0) or 50.0
    home_pos = _get(home_state, "position", "position", default=10) or 10
    away_pos = _get(away_state, "position", "position", default=10) or 10

    # Relegation battles and close matches = more physical
    both_low = home_pos >= 14 and away_pos >= 14
    close_table = abs(home_pos - away_pos) <= 3

    intensity = "moderate"
    if both_low:
        intensity = "high"
    elif close_table and (home_poss < 50 or away_poss < 50):
        intensity = "high"
    elif home_poss > 55 and away_poss > 55:
        intensity = "low"

    return {
        "expected_intensity": intensity,
        "note": "Relegation battles and close table neighbours tend to produce more physical games",
        "evidence": f"Positions {home_pos}th vs {away_pos}th, possession {home_poss:.0f}%-{away_poss:.0f}%",
    }


def _compute_style_clash(
    home_state: Dict, away_state: Dict, matchup: Dict
) -> Dict:
    """Overall style clash characterisation."""
    home_poss = _get(home_state, "style", "avg_possession", default=50.0) or 50.0
    away_poss = _get(away_state, "style", "avg_possession", default=50.0) or 50.0
    poss_diff = abs(home_poss - away_poss)

    if poss_diff > 8:
        clash_type = "Asymmetric (possession vs transition)"
    elif home_poss > 52 and away_poss > 52:
        clash_type = "Open (both want the ball)"
    elif home_poss < 48 and away_poss < 48:
        clash_type = "Direct (neither dominates ball)"
    else:
        clash_type = "Balanced"

    matchup_verdict = matchup.get("verdict", "")

    return {
        "clash_type": clash_type,
        "matchup_verdict": matchup_verdict,
        "evidence": f"Style clash: {clash_type}. Matchup verdict: {matchup_verdict or 'N/A'}",
    }


# =========================================================================
# D. GAME STATE TENDENCIES
# =========================================================================

def _compute_first_goal_tendency(home_state: Dict, away_state: Dict) -> Dict:
    """Which team tends to score first?"""
    home_form_str = _get(home_state, "form", "form_string", default="") or ""
    away_form_str = _get(away_state, "form", "form_string", default="") or ""

    # Proxy: teams with more wins likely score first more often
    home_wins = home_form_str.count("W")
    away_wins = away_form_str.count("W")

    return {
        "home_wins_last5": home_wins,
        "away_wins_last5": away_wins,
        "edge": "home" if home_wins > away_wins + 1 else "away" if away_wins > home_wins + 1 else "neutral",
        "evidence": f"Home {home_wins}W in last 5, Away {away_wins}W in last 5",
    }


def _compute_reaction_to_adversity(home_state: Dict, away_state: Dict) -> Dict:
    """How teams react when conceding (collapse or fight back?)."""
    home_trend = _get(home_state, "trajectory", "form_trend", default="stable")
    away_trend = _get(away_state, "trajectory", "form_trend", default="stable")
    home_form_str = _get(home_state, "form", "form_string", default="") or ""
    away_form_str = _get(away_state, "form", "form_string", default="") or ""

    # Teams with draws after losses show resilience
    home_resilience = "unknown"
    away_resilience = "unknown"

    if "LW" in home_form_str or "LDW" in home_form_str:
        home_resilience = "bounces_back"
    elif home_form_str.startswith("LL"):
        home_resilience = "fragile"

    if "LW" in away_form_str or "LDW" in away_form_str:
        away_resilience = "bounces_back"
    elif away_form_str.startswith("LL"):
        away_resilience = "fragile"

    return {
        "home_resilience": home_resilience,
        "away_resilience": away_resilience,
        "evidence": f"Home form: {home_form_str} ({home_resilience}), Away form: {away_form_str} ({away_resilience})",
    }


def _compute_game_closing(home_state: Dict, away_state: Dict) -> Dict:
    """Can teams hold onto leads?"""
    home_cs = _get(home_state, "form", "clean_sheets_last5", default=0) or 0
    away_cs = _get(away_state, "form", "clean_sheets_last5", default=0) or 0

    home_conceded = _get(home_state, "form", "goals_conceded_last5", default=0) or 0
    away_conceded = _get(away_state, "form", "goals_conceded_last5", default=0) or 0

    return {
        "home_clean_sheets": home_cs,
        "away_clean_sheets": away_cs,
        "home_conceded_last5": home_conceded,
        "away_conceded_last5": away_conceded,
        "home_closes_games": home_cs >= 2,
        "away_closes_games": away_cs >= 2,
        "evidence": f"Home {home_cs} CS, {home_conceded} conceded last 5 | Away {away_cs} CS, {away_conceded} conceded last 5",
    }


def _compute_goals_expected(
    home: Dict, away: Dict, home_state: Dict, away_state: Dict
) -> Dict:
    """Expected goal volume in the match."""
    home_xg_for = _get(home, "form_detail", "xg", "xg_for", default=0.0) or 0.0
    away_xg_for = _get(away, "form_detail", "xg", "xg_for", default=0.0) or 0.0
    home_xga = _get(home_state, "form", "xg_against_last5", default=0.0) or 0.0
    away_xga = _get(away_state, "form", "xg_against_last5", default=0.0) or 0.0

    # Simple total xG expectation
    # Home team's xG_for vs Away's xGA, and vice versa
    home_attack = home.get("attack_profile", {})
    away_attack = away.get("attack_profile", {})
    home_xg_pg = home_attack.get("xg_per_game", 0) or 0
    away_xg_pg = away_attack.get("xg_per_game", 0) or 0

    home_def = home.get("defense_profile", {})
    away_def = away.get("defense_profile", {})
    home_xga_pg = home_def.get("xg_against_per_game", 0) or 0
    away_xga_pg = away_def.get("xg_against_per_game", 0) or 0

    # Expected goals: average of attacking and defensive metrics
    home_expected = (home_xg_pg + away_xga_pg) / 2 if home_xg_pg and away_xga_pg else home_xg_pg or 1.0
    away_expected = (away_xg_pg + home_xga_pg) / 2 if away_xg_pg and home_xga_pg else away_xg_pg or 1.0
    total_expected = home_expected + away_expected

    volume = "low"
    if total_expected > 3.0:
        volume = "high"
    elif total_expected > 2.2:
        volume = "moderate"

    return {
        "home_expected_goals": round(home_expected, 2),
        "away_expected_goals": round(away_expected, 2),
        "total_expected": round(total_expected, 2),
        "volume": volume,
        "over_25_likely": total_expected > 2.5,
        "evidence": f"Expected total: {total_expected:.1f} goals (Home {home_expected:.1f} + Away {away_expected:.1f}). Volume: {volume}",
    }


# =========================================================================
# E. SUMMARY HELPERS
# =========================================================================

def _compute_edge_factors(rubric: Dict, side: str) -> List[str]:
    """List factors that favour a given side."""
    factors = []
    for key, factor in rubric.items():
        if isinstance(factor, dict) and factor.get("edge") == side:
            factors.append(key)
    return factors


def _compute_decisive_factors(rubric: Dict) -> List[Dict]:
    """Identify the most decisive factors for this match."""
    decisive = []

    # Strong form momentum
    momentum = rubric.get("form_momentum", {})
    if abs(momentum.get("momentum_delta", 0)) >= 2:
        decisive.append({
            "factor": "form_momentum",
            "why": f"Clear momentum gap — {momentum.get('evidence', '')}",
            "favours": momentum.get("edge", "neutral"),
        })

    # Key absences
    absences = rubric.get("key_absences", {})
    if absences.get("score", 0) >= 5:
        decisive.append({
            "factor": "key_absences",
            "why": f"Significant absences affecting one side more — {absences.get('evidence', '')}",
            "favours": absences.get("edge", "neutral"),
        })

    # Creation quality gap
    creation = rubric.get("creation_quality", {})
    if creation.get("edge") != "neutral":
        decisive.append({
            "factor": "creation_quality",
            "why": f"Attacking quality gap — {creation.get('evidence', '')}",
            "favours": creation.get("edge", "neutral"),
        })

    # Transition threat vs high-possession team
    transition = rubric.get("transition_threat", {})
    if transition.get("matchup_note") and "counter-attack" in transition.get("matchup_note", ""):
        decisive.append({
            "factor": "transition_threat",
            "why": transition.get("matchup_note", ""),
            "favours": "context_dependent",
        })

    # Defensive solidity gap
    defense = rubric.get("defensive_solidity", {})
    if defense.get("edge") != "neutral":
        decisive.append({
            "factor": "defensive_solidity",
            "why": f"Defensive gap — {defense.get('evidence', '')}",
            "favours": defense.get("edge", "neutral"),
        })

    return decisive


# =========================================================================
# RENDERING (for the LLM prompt)
# =========================================================================

def render_rubric_for_prompt(rubric_data: Dict[str, Any]) -> str:
    """Render the tactical rubric as a readable section for the LLM prompt."""
    factors = rubric_data.get("factors", {})
    if not factors:
        return ""

    lines = ["## TACTICAL RUBRIC (your primary analytical lens)",
             "Pre-computed tactical interpretation. Ground your game read in these factors."]
    lines.append("")

    # A. Context
    lines.append("### A. CONTEXT")
    _render_factor(lines, "Form Momentum", factors.get("form_momentum", {}))
    _render_factor(lines, "Schedule Strength", factors.get("schedule_strength", {}))
    _render_factor(lines, "Key Absences", factors.get("key_absences", {}))
    lines.append("")

    # B. Attack vs Defense
    lines.append("### B. ATTACK vs DEFENSE")
    _render_factor(lines, "Creation Quality", factors.get("creation_quality", {}))
    _render_factor(lines, "Transition Threat", factors.get("transition_threat", {}))
    _render_factor(lines, "Defensive Solidity", factors.get("defensive_solidity", {}))
    _render_factor(lines, "Goals Expected", factors.get("goals_expected", {}))
    lines.append("")

    # C. Tactical Matchup
    lines.append("### C. TACTICAL MATCHUP")
    _render_factor(lines, "Possession Dynamic", factors.get("possession_vs_block", {}))
    _render_factor(lines, "Style Clash", factors.get("style_clash", {}))
    _render_factor(lines, "Physical Intensity", factors.get("physical_intensity", {}))
    lines.append("")

    # D. Game State
    lines.append("### D. GAME STATE TENDENCIES")
    _render_factor(lines, "Reaction to Adversity", factors.get("reaction_to_adversity", {}))
    _render_factor(lines, "Game Closing", factors.get("game_closing", {}))
    lines.append("")

    # E. Summary
    lines.append("### E. KEY MATCHUP SUMMARY")
    home_edges = factors.get("home_edge_factors", [])
    away_edges = factors.get("away_edge_factors", [])
    if home_edges:
        lines.append(f"  Home edge factors: {', '.join(home_edges)}")
    if away_edges:
        lines.append(f"  Away edge factors: {', '.join(away_edges)}")

    decisive = factors.get("decisive_factors", [])
    if decisive:
        lines.append("  Decisive factors:")
        for d in decisive:
            lines.append(f"    - {d['factor']}: {d['why']} (favours {d['favours']})")

    return "\n".join(lines)


def _render_factor(lines: List[str], label: str, factor: Dict):
    """Render a single factor for the prompt."""
    if not factor:
        return
    evidence = factor.get("evidence", "")
    edge = factor.get("edge", "")
    note = factor.get("note", "") or factor.get("matchup_note", "")

    line = f"  {label}: {evidence}"
    if edge and edge != "neutral":
        line += f" [edge: {edge}]"
    lines.append(line)
    if note:
        lines.append(f"    → {note}")
