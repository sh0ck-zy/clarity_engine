"""
v1.5 Telegram Renderer — renders match_intelligence.json as a Telegram post.

Replaces the v1.4 stats-based telegram.txt with a game-reading format.
"""

from __future__ import annotations

from typing import Any, Dict


def render_telegram_v15(
    intelligence: Dict[str, Any],
    report: Dict[str, Any],
) -> str:
    """
    Render match_intelligence.json + report.json as a Telegram post.

    Combines v1.5 game read with v1.4 probabilities for a complete post.
    """
    fixture = report.get("fixture", {})
    home = fixture.get("home_team", "?")
    away = fixture.get("away_team", "?")
    rnd = fixture.get("round_number", "?")
    probs = report.get("probabilities", {})
    pred = report.get("prediction", {})

    h_pct = int(round(probs.get("home_win", 0.33) * 100))
    d_pct = int(round(probs.get("draw", 0.33) * 100))
    a_pct = int(round(probs.get("away_win", 0.33) * 100))

    confidence = intelligence.get("confidence", "Medium")
    lean = intelligence.get("lean", "")

    lines = []

    # Header
    lines.append(f"## {home} vs {away} | R{rnd}")
    lines.append("")

    # Key question
    kq = intelligence.get("key_question", "")
    if kq:
        lines.append(f"**{kq}**")
        lines.append("")

    # Main read
    main_read = intelligence.get("main_read", "")
    if main_read:
        lines.append(main_read)
        lines.append("")

    # Probabilities
    lines.append(f"H {h_pct}% | D {d_pct}% | A {a_pct}%")
    lines.append("")

    # Scenarios
    scenarios = intelligence.get("scenarios", [])
    if scenarios:
        for s in scenarios:
            likelihood = s.get("likelihood", "?")
            name = s.get("name", "?")
            desc = s.get("description", "")
            icon = {"most likely": "1.", "plausible": "2.", "possible": "3."}.get(
                likelihood, "-"
            )
            lines.append(f"{icon} **{name}** ({likelihood})")
            lines.append(f"   {desc}")
        lines.append("")

    # Risks
    risks = intelligence.get("risks", [])
    if risks:
        lines.append("Risks:")
        for r in risks:
            lines.append(f"- {r}")
        lines.append("")

    # Lean
    if lean:
        lines.append(f"**Lean:** {lean}")
        lines.append(f"**Confidence:** {confidence}")

    lines.append("")
    lines.append("[v1.5-mi]")

    return "\n".join(lines)
