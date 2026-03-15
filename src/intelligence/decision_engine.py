"""
Decision Engine — deterministic jump from "good read" to "pick / watchlist / no-bet".

v1.8: Explicit direction resolution layer.
Three directions tracked: ml_anchor, tactical_read, final_decision.
Final decision follows tactical read only through explicit resolution logic.

Does NOT gate MI — only affects editorial/publishing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Decision:
    action: str          # "NO_BET" | "WATCHLIST" | "LEAN" | "PICK"
    direction: str       # "H" | "D" | "A" | None
    reasoning: list[str] = field(default_factory=list)
    edge_vs_market: float | None = None
    directions: dict = field(default_factory=dict)  # resolved direction trace

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "direction": self.direction,
            "reasoning": self.reasoning,
            "edge_vs_market": round(self.edge_vs_market, 4) if self.edge_vs_market is not None else None,
            "directions": self.directions,
        }


def _count_signal_conflicts(
    ml_anchor: Dict[str, Any],
    signals: Dict[str, Any],
    tactical_rubric: Dict[str, Any],
) -> int:
    """Count conflicts between ML prediction and signals/rubric."""
    conflicts = 0
    predicted = ml_anchor.get("predicted_result", "")
    sigs = signals.get("signals", {})

    if predicted == "H" and sigs.get("fragile_home_edge"):
        conflicts += 1
    if predicted == "H" and sigs.get("upset_potential"):
        conflicts += 1
    if predicted in ("H", "A") and sigs.get("draw_pressure_risk"):
        conflicts += 1

    summary = tactical_rubric.get("summary", {})
    home_edge_count = summary.get("home_edge_count", 0)
    away_edge_count = summary.get("away_edge_count", 0)

    if predicted == "H" and away_edge_count > home_edge_count + 2:
        conflicts += 1
    if predicted == "A" and home_edge_count > away_edge_count + 2:
        conflicts += 1

    return conflicts


def _rubric_aligns_with_direction(
    direction: str,
    tactical_rubric: Dict[str, Any],
) -> bool:
    """Check if rubric edge aligns with a given direction."""
    summary = tactical_rubric.get("summary", {})
    home_edge_count = summary.get("home_edge_count", 0)
    away_edge_count = summary.get("away_edge_count", 0)

    if direction == "H":
        return home_edge_count >= away_edge_count
    if direction == "A":
        return away_edge_count >= home_edge_count
    # Draw: edges are close
    return abs(home_edge_count - away_edge_count) <= 1


def _compute_edge_vs_market(
    direction: str,
    ml_anchor: Dict[str, Any],
    market_odds: Optional[Dict[str, float]],
) -> Optional[float]:
    """Compute edge for a given direction against market odds."""
    if not market_odds or not direction:
        return None

    probs = ml_anchor.get("probabilities", {})
    our_prob = probs.get(direction, 0.0)
    market_prob = market_odds.get(f"prob_{direction}", market_odds.get(direction, 0.0))

    if our_prob and market_prob:
        return our_prob - market_prob
    return None


def infer_lean_direction(
    lean_text: str,
    home_team: str = "",
    away_team: str = "",
) -> str:
    """Infer H/D/A direction from lean text, using team names when available."""
    text = lean_text.lower()

    # Check for team names first (most reliable)
    home_score = 0
    away_score = 0
    draw_score = 0

    if home_team:
        # Match full name or significant parts (>3 chars)
        home_parts = [p for p in home_team.lower().split() if len(p) > 3]
        for part in home_parts:
            if part in text:
                home_score += 2

    if away_team:
        away_parts = [p for p in away_team.lower().split() if len(p) > 3]
        for part in away_parts:
            if part in text:
                away_score += 2

    # Generic direction words (weaker signal)
    home_words = ["home", "host", "control", "dominat"]
    away_words = ["away", "visitor", "underdog", "upset", "counter"]
    draw_words = ["draw", "stalemate", "even", "balanced", "tight", "1-1", "0-0"]

    home_score += sum(1 for w in home_words if w in text)
    away_score += sum(1 for w in away_words if w in text)
    draw_score += sum(1 for w in draw_words if w in text)

    if draw_score > home_score and draw_score > away_score:
        return "D"
    if away_score > home_score:
        return "A"
    if home_score > 0:
        return "H"
    return "H"  # default


def _resolve_direction(
    ml_direction: str,
    tactical_direction: str,
    confidence_level: str,
    margin: float,
    signals: Dict[str, Any],
    tactical_rubric: Dict[str, Any],
) -> tuple[str, str | None]:
    """
    Resolve final direction from ML and tactical read.

    Returns (final_direction, override_reason or None).

    Resolution rules:
    - If ML and tactical agree → follow both (no override)
    - If they diverge AND tactical is supported by rubric/signals → follow tactical
    - If they diverge AND tactical is NOT supported → follow ML (tactical read is noise)
    - Divergence always downgrades action one tier
    """
    if ml_direction == tactical_direction:
        return ml_direction, None

    # They diverge — check if tactical read has support
    sigs = signals.get("signals", {})
    rubric_supports_tactical = _rubric_aligns_with_direction(tactical_direction, tactical_rubric)

    # Signal support for tactical direction
    signal_support = 0
    if tactical_direction == "D" and sigs.get("draw_pressure_risk"):
        signal_support += 1
    if tactical_direction == "H" and sigs.get("home_territorial_edge"):
        signal_support += 1
    if tactical_direction == "A" and sigs.get("upset_potential"):
        signal_support += 1
    if tactical_direction == "A" and sigs.get("fragile_home_edge"):
        signal_support += 1

    # Follow tactical read when it has backing
    if rubric_supports_tactical or signal_support >= 1:
        reason = (
            f"tactical read ({tactical_direction}) diverges from ML ({ml_direction}), "
            f"supported by {'rubric' if rubric_supports_tactical else ''}"
            f"{' + ' if rubric_supports_tactical and signal_support else ''}"
            f"{f'{signal_support} signal(s)' if signal_support else ''}"
        )
        return tactical_direction, reason

    # Tactical read has no backing — follow ML
    reason = (
        f"tactical read ({tactical_direction}) diverges from ML ({ml_direction}), "
        f"but lacks rubric/signal support — following ML"
    )
    return ml_direction, reason


def make_decision(
    ml_anchor: Dict[str, Any],
    confidence_level: str,
    dq_result: Any,
    signals: Dict[str, Any],
    tactical_rubric: Dict[str, Any],
    market_odds: Optional[Dict[str, float]] = None,
    lean_text: str = "",
    home_team: str = "",
    away_team: str = "",
) -> Decision:
    """
    Make a deterministic decision with explicit direction resolution.

    Direction resolution:
    - ml_anchor.direction: from ML model
    - tactical_read.direction: inferred from LLM lean text
    - final_decision.direction: resolved through rubric/signal validation
    """
    ml_signals = ml_anchor.get("signals", {})
    margin = ml_signals.get("margin_top2", 0.0) or 0.0
    entropy = ml_signals.get("entropy_norm", 1.0) or 1.0
    ml_direction = ml_anchor.get("predicted_result", "")

    integrity_score = getattr(dq_result, "integrity_score", getattr(dq_result, "score", 100.0))

    signal_conflicts = _count_signal_conflicts(ml_anchor, signals, tactical_rubric)

    # Resolve direction
    tactical_direction = infer_lean_direction(lean_text, home_team, away_team) if lean_text else ml_direction
    final_direction, override_reason = _resolve_direction(
        ml_direction, tactical_direction, confidence_level, margin,
        signals, tactical_rubric,
    )
    has_divergence = ml_direction != tactical_direction

    directions = {
        "ml_anchor": ml_direction,
        "tactical_read": tactical_direction,
        "final_decision": final_direction,
        "override_reason": override_reason,
    }

    rubric_aligns = _rubric_aligns_with_direction(final_direction, tactical_rubric)
    edge = _compute_edge_vs_market(final_direction, ml_anchor, market_odds)

    reasoning = []

    # === NO_BET ===
    if confidence_level == "Low":
        reasoning.append(f"confidence={confidence_level}")
        return Decision("NO_BET", None, reasoning, edge, directions)

    if entropy > 0.997:
        reasoning.append(f"entropy={entropy:.3f} > 0.997 (true coin flip)")
        return Decision("NO_BET", None, reasoning, edge, directions)

    if integrity_score < 60:
        reasoning.append(f"integrity_score={integrity_score:.0f} < 60")
        return Decision("NO_BET", None, reasoning, edge, directions)

    # === PICK (highest bar) ===
    if (confidence_level in ("High", "Medium-High")
            and margin >= 0.10
            and rubric_aligns
            and signal_conflicts == 0
            and not has_divergence):  # divergence blocks PICK
        reasoning.append(f"confidence={confidence_level}, margin={margin:.2f}")
        reasoning.append("rubric aligns, 0 signal conflicts, no direction divergence")
        if edge is not None and edge > 0.03:
            reasoning.append(f"edge_vs_market={edge:+.3f} > 0.03")
            return Decision("PICK", final_direction, reasoning, edge, directions)
        reasoning.append(f"edge_vs_market={edge:+.3f}" if edge is not None else "no market odds")
        return Decision("LEAN", final_direction, reasoning, edge, directions)

    # === WATCHLIST ===
    if confidence_level == "Medium-Low":
        reasoning.append(f"confidence={confidence_level}")
        return Decision("WATCHLIST", final_direction, reasoning, edge, directions)

    if margin < 0.03:
        reasoning.append(f"margin={margin:.3f} < 0.03")
        return Decision("WATCHLIST", final_direction, reasoning, edge, directions)

    if signal_conflicts >= 2:
        reasoning.append(f"{signal_conflicts} signal conflicts")
        return Decision("WATCHLIST", final_direction, reasoning, edge, directions)

    # Divergence downgrades by one tier
    if has_divergence:
        reasoning.append(f"direction divergence: ML={ml_direction} vs tactical={tactical_direction}")
        if override_reason:
            reasoning.append(override_reason)
        # Would-be LEAN becomes WATCHLIST, would-be PICK becomes LEAN (handled above)
        if confidence_level in ("High", "Medium-High") and rubric_aligns:
            return Decision("LEAN", final_direction, reasoning, edge, directions)
        return Decision("WATCHLIST", final_direction, reasoning, edge, directions)

    # === LEAN (default for decent data + alignment) ===
    if rubric_aligns and signal_conflicts == 0:
        reasoning.append(f"confidence={confidence_level}, margin={margin:.2f}")
        reasoning.append("rubric aligns, no conflicts")
        return Decision("LEAN", final_direction, reasoning, edge, directions)

    # Fallback: WATCHLIST
    reasoning.append(f"confidence={confidence_level}, margin={margin:.2f}")
    if not rubric_aligns:
        reasoning.append("rubric does not align")
    if signal_conflicts:
        reasoning.append(f"{signal_conflicts} signal conflict(s)")
    return Decision("WATCHLIST", final_direction, reasoning, edge, directions)
