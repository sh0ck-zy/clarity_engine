"""
Board Classifier — maps Decision output to editorial board categories.

Pure function, no LLM. Deterministic classification + clarity score.

Categories (evaluated in order):
  TOP_ANGLE — high-confidence pick with real edge
  LIVE_DOG  — lean/pick diverging toward underdog/draw
  TRAP_SPOT — watchlist with ML/tactical divergence or draw pressure
  TOO_THIN  — everything else
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class BoardEntry:
    match_id: str
    home_team: str
    away_team: str
    category: str           # TOP_ANGLE | LIVE_DOG | TRAP_SPOT | TOO_THIN
    clarity_score: int      # 0-100 deterministic composite
    action: str             # PICK | LEAN | WATCHLIST | NO_BET
    direction: Optional[str]
    confidence: str
    edge: Optional[float]
    lean: str               # thesis text from MI
    core_read: str          # one-liner game read
    directions: Dict[str, str] = field(default_factory=dict)
    signal_conflicts: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "match_id": self.match_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "category": self.category,
            "clarity_score": self.clarity_score,
            "action": self.action,
            "direction": self.direction,
            "confidence": self.confidence,
            "edge": round(self.edge, 4) if self.edge is not None else None,
            "lean": self.lean,
            "core_read": self.core_read,
            "directions": self.directions,
            "signal_conflicts": self.signal_conflicts,
        }
        return d


def _compute_clarity_score(
    confidence: str,
    edge: Optional[float],
    has_divergence: bool,
    signal_conflicts: int,
    entropy: float,
) -> int:
    """Deterministic clarity score, 0-100."""
    score = 50

    if confidence in ("High", "Medium-High"):
        score += 20
    elif confidence == "Medium":
        score += 10

    if edge is not None:
        if edge > 0.05:
            score += 15
        elif edge > 0.02:
            score += 8

    if not has_divergence:
        score += 10

    if signal_conflicts >= 2:
        score -= 10

    if entropy > 0.99:
        score -= 15

    return max(0, min(100, score))


def classify_board_category(
    decision: Dict[str, Any],
    signals: Dict[str, Any],
    ml_anchor: Dict[str, Any],
    mi_result: Dict[str, Any],
) -> BoardEntry:
    """
    Classify a match into a board category from decision/signal/ML/MI data.

    Pure function — no LLM, no side effects.
    """
    action = decision.get("action", "NO_BET")
    direction = decision.get("direction")
    confidence = mi_result.get("confidence", "Medium")
    edge = decision.get("edge_vs_market")
    directions = decision.get("directions", {})

    ml_direction = directions.get("ml_anchor", "")
    tactical_direction = directions.get("tactical_read", "")
    final_direction = directions.get("final_decision", "")

    has_divergence = ml_direction != tactical_direction and ml_direction and tactical_direction

    sigs = signals.get("signals", {})
    ml_signals = ml_anchor.get("signals", {})
    entropy = ml_signals.get("entropy_norm", 1.0) or 1.0

    # Count signal conflicts (reuse logic from decision_engine)
    signal_conflicts = 0
    predicted = ml_anchor.get("predicted_result", "")
    if predicted == "H" and sigs.get("fragile_home_edge"):
        signal_conflicts += 1
    if predicted == "H" and sigs.get("upset_potential"):
        signal_conflicts += 1
    if predicted in ("H", "A") and sigs.get("draw_pressure_risk"):
        signal_conflicts += 1

    # Determine if final direction diverges toward underdog/draw vs ML favorite
    ml_fav = ml_anchor.get("predicted_result", "")
    diverges_from_fav = final_direction != ml_fav and final_direction in ("D", "A", "H")

    # Draw pressure confidence
    draw_pressure = sigs.get("draw_pressure_risk", False)

    # Classification rules (evaluated in order)
    if (action == "PICK"
            and confidence in ("High", "Medium-High")
            and edge is not None and edge > 0.03):
        category = "TOP_ANGLE"

    elif (action in ("LEAN", "PICK")
          and diverges_from_fav
          and (sigs.get("upset_potential") or sigs.get("fragile_home_edge"))):
        category = "LIVE_DOG"

    elif (action == "WATCHLIST"
          and (has_divergence
               or (draw_pressure and confidence in ("Medium", "Medium-High", "High")))):
        category = "TRAP_SPOT"

    else:
        category = "TOO_THIN"

    clarity_score = _compute_clarity_score(
        confidence, edge, has_divergence, signal_conflicts, entropy,
    )

    # Extract thesis content from MI
    lean = mi_result.get("lean", "")
    core_read = mi_result.get("core_read", mi_result.get("main_read", ""))

    fixture = mi_result.get("fixture", {})
    match_id = mi_result.get("match_id", fixture.get("fixture_id", ""))
    home = fixture.get("home_team", mi_result.get("home_team", ""))
    away = fixture.get("away_team", mi_result.get("away_team", ""))

    return BoardEntry(
        match_id=str(match_id),
        home_team=home,
        away_team=away,
        category=category,
        clarity_score=clarity_score,
        action=action,
        direction=direction,
        confidence=confidence,
        edge=edge,
        lean=lean,
        core_read=core_read,
        directions=directions,
        signal_conflicts=signal_conflicts,
    )
