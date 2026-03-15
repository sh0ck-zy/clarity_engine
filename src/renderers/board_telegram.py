"""
Board Telegram Renderer — renders board.json as a single Telegram post.

TOP_ANGLE + LIVE_DOG: full 3-line treatment.
TRAP_SPOT: compact 2-line treatment.
TOO_THIN: names only, single line.
"""

from __future__ import annotations

from typing import Any, Dict, List


_CATEGORY_LABELS = {
    "TOP_ANGLE": "TARGET",
    "LIVE_DOG": "LIVE DOG",
    "TRAP_SPOT": "TRAP",
    "TOO_THIN": "TOO THIN",
}

_SEPARATOR = "\u2501" * 23  # thin box line


def _fmt_edge(edge: float | None) -> str:
    if edge is None:
        return ""
    return f"{edge:+.1%}"


def _render_full(entry: Dict[str, Any]) -> str:
    """Full 3-line treatment for TOP_ANGLE and LIVE_DOG."""
    label = _CATEGORY_LABELS.get(entry["category"], entry["category"])
    home = entry["home_team"]
    away = entry["away_team"]
    action = entry["action"]
    direction = entry.get("direction", "")
    confidence = entry.get("confidence", "")
    edge = _fmt_edge(entry.get("edge"))
    core_read = entry.get("core_read", "")
    score = entry.get("clarity_score", 0)

    lines = []
    lines.append(f"[{label}] {home} vs {away}")

    # Action line
    action_parts = [action]
    if direction:
        action_parts.append(direction)
    if confidence:
        action_parts.append(f"({confidence})")
    action_line = " ".join(action_parts)
    if edge:
        action_line += f" | {edge}"
    lines.append(action_line)

    # Core read (truncate if too long)
    if core_read:
        if len(core_read) > 120:
            core_read = core_read[:117] + "..."
        lines.append(core_read)

    lines.append(f"Score: {score}")
    return "\n".join(lines)


def _render_compact(entry: Dict[str, Any]) -> str:
    """Compact 2-line treatment for TRAP_SPOT."""
    label = _CATEGORY_LABELS.get(entry["category"], entry["category"])
    home = entry["home_team"]
    away = entry["away_team"]
    action = entry.get("action", "")
    directions = entry.get("directions", {})

    lines = []
    lines.append(f"[{label}] {home} vs {away}")

    # Show divergence if present
    ml_dir = directions.get("ml_anchor", "")
    tac_dir = directions.get("tactical_read", "")
    if ml_dir and tac_dir and ml_dir != tac_dir:
        dir_map = {"H": home, "D": "Draw", "A": away}
        lines.append(f"{action} | ML->{dir_map.get(ml_dir, ml_dir)}, "
                     f"tactical->{dir_map.get(tac_dir, tac_dir)}")
    else:
        core_read = entry.get("core_read", "")
        if core_read:
            if len(core_read) > 100:
                core_read = core_read[:97] + "..."
            lines.append(core_read)

    return "\n".join(lines)


def render_board_telegram(board: Dict[str, Any]) -> str:
    """Render board.json as a single Telegram post."""
    league = board.get("league", "")
    round_number = board.get("round_number", "")
    date = board.get("date", "")
    analyzed = board.get("matches_analyzed", 0)
    actionable = board.get("actionable_angles", 0)
    entries = board.get("board", [])

    # Format date as "14 Mar" style
    date_short = date
    if date and len(date) == 10:
        try:
            from datetime import datetime
            dt = datetime.strptime(date, "%Y-%m-%d")
            date_short = dt.strftime("%-d %b")
        except (ValueError, ImportError):
            pass

    lines = []

    # Header
    lines.append(f"CLARITY BOARD | {league} R{round_number} | {date_short}")
    lines.append(f"{analyzed} analyzed | {actionable} actionable")
    lines.append(_SEPARATOR)
    lines.append("")

    # Categorized entries
    too_thin: List[str] = []

    for entry in entries:
        category = entry.get("category", "TOO_THIN")

        if category == "TOO_THIN":
            home = entry.get("home_team", "?")
            away = entry.get("away_team", "?")
            too_thin.append(f"{home} vs {away}")
            continue

        if category in ("TOP_ANGLE", "LIVE_DOG"):
            lines.append(_render_full(entry))
        elif category == "TRAP_SPOT":
            lines.append(_render_compact(entry))

        lines.append("")

    # TOO THIN summary line
    if too_thin:
        lines.append(_SEPARATOR)
        if len(too_thin) <= 2:
            lines.append(f"TOO THIN: {', '.join(too_thin)}")
        else:
            shown = too_thin[:2]
            rest = len(too_thin) - 2
            lines.append(f"TOO THIN: {', '.join(shown)}, +{rest} more")

    lines.append("")
    lines.append(_provenance_tag(board))

    return "\n".join(lines)


def _provenance_tag(board: Dict[str, Any]) -> str:
    """Build a provenance tag showing the pipeline used to generate this board."""
    trace = board.get("llm_trace", {})
    model = trace.get("model", "?")
    provider = trace.get("provider", "?")
    provider_label = {"openai": "oai", "anthropic": "anth", "huggingface": "hf", "gemini": "gem"}.get(provider, provider)

    # MI schema version comes from the individual matches, board schema is separate
    mi_version = "1.8"  # current MI schema version

    return f"[mi-v{mi_version} | {provider_label}:{model} | board-v1.0]"
