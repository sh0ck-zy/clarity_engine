"""
Telegram Renderer — renders match_intelligence.json as a Telegram post.

v1.8: Premium 7-field format — verdict/read/mechanism/risk/kill_switch/score/lean/decision.
"""

from __future__ import annotations

from typing import Any, Dict


def render_telegram_v15(
    intelligence: Dict[str, Any],
    report: Dict[str, Any],
) -> str:
    """
    Render match_intelligence.json + report.json as a premium Telegram post.

    v1.8: Maps 7-field output to tight scout briefing format.
    """
    # If MI was skipped, minimal output (no fake v1.8 tag)
    mi_status = intelligence.get("mi_status", "")
    if mi_status in ("skip", "skipped", "degraded"):
        fixture = report.get("fixture", {})
        home = fixture.get("home_team", "?")
        away = fixture.get("away_team", "?")
        rnd = fixture.get("round_number", "?")
        reason = intelligence.get("reason", "insufficient data")
        return f"## {home} vs {away} | R{rnd}\n\nAnalysis unavailable: {reason}"

    fixture = report.get("fixture", {})
    home = fixture.get("home_team", "?")
    away = fixture.get("away_team", "?")
    rnd = fixture.get("round_number", "?")
    probs = report.get("probabilities", {})

    h_pct = int(round(probs.get("home_win", 0.33) * 100))
    d_pct = int(round(probs.get("draw", 0.33) * 100))
    a_pct = int(round(probs.get("away_win", 0.33) * 100))

    # v1.8 fields (with legacy fallbacks)
    verdict = intelligence.get("verdict", intelligence.get("key_question", ""))
    core_read = intelligence.get("core_read", intelligence.get("main_read", ""))
    main_mechanism = intelligence.get("main_mechanism", "")
    main_risk = intelligence.get("main_risk", "")
    kill_switch = intelligence.get("kill_switch", intelligence.get("invalidation_condition", ""))
    best_score_range = intelligence.get("best_score_range", "")
    lean = intelligence.get("lean", "")
    confidence = intelligence.get("confidence", "Medium")
    decision = intelligence.get("decision", {})
    directions = intelligence.get("directions", decision.get("directions", {}))

    lines = []

    # Header
    lines.append(f"## {home} vs {away} | R{rnd}")
    lines.append("")

    # Verdict (bold, the hook)
    if verdict:
        lines.append(f"**{verdict}**")
        lines.append("")

    # Core read
    if core_read:
        lines.append(core_read)
        lines.append("")

    # Mechanism + Risk (compact two-liner)
    if main_mechanism:
        lines.append(f"Mechanism: {main_mechanism}")
    if main_risk:
        lines.append(f"Risk: {main_risk}")
    if main_mechanism or main_risk:
        lines.append("")

    # Kill switch
    if kill_switch:
        lines.append(f"Kill switch: {kill_switch}")
        lines.append("")

    # Probabilities + score range
    prob_line = f"H {h_pct}% | D {d_pct}% | A {a_pct}%"
    if best_score_range:
        prob_line += f" | {best_score_range}"
    lines.append(prob_line)
    lines.append("")

    # Lean + Confidence + Decision
    if lean:
        lines.append(f"**Lean:** {lean}")
        lines.append(f"**Confidence:** {confidence}")

    # Decision badge
    if decision:
        action = decision.get("action", "")
        direction = decision.get("direction", "")
        edge = decision.get("edge_vs_market")

        action_labels = {
            "PICK": "PICK",
            "LEAN": "LEAN",
            "WATCHLIST": "WATCHLIST",
            "NO_BET": "NO BET",
        }
        label = action_labels.get(action, action)

        dir_map = {"H": home, "D": "Draw", "A": away}
        dir_label = dir_map.get(direction, "")

        decision_line = f"**Decision:** {label}"
        if dir_label:
            decision_line += f" {dir_label}"
        if edge is not None and action in ("PICK", "LEAN"):
            decision_line += f" (edge: {edge:+.1%})"
        lines.append(decision_line)

    # Direction trace (compact)
    if directions:
        ml_dir = directions.get("ml_anchor", "")
        tac_dir = directions.get("tactical_read", "")
        final_dir = directions.get("final_decision", "")
        if ml_dir and tac_dir and ml_dir != tac_dir:
            lines.append(f"Directions: ML={ml_dir} Tactical={tac_dir} Final={final_dir}")

    lines.append("")
    lines.append(_provenance_tag(intelligence))

    return "\n".join(lines)


def _provenance_tag(intelligence: Dict[str, Any]) -> str:
    """Build a provenance tag showing the full pipeline used to generate this analysis."""
    schema = intelligence.get("schema_version", "?")
    trace = intelligence.get("llm_trace", intelligence.get("_llm_trace", {}))
    model = trace.get("model", "?")
    provider = trace.get("provider", "?")

    # Short provider label
    provider_label = {"openai": "oai", "anthropic": "anth", "huggingface": "hf", "gemini": "gem"}.get(provider, provider)

    return f"[mi-v{schema} | {provider_label}:{model}]"
