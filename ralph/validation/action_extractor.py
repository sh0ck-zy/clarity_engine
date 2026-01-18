from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Dict, Optional


class ActionType(Enum):
    NO_ACTION = "NO_ACTION"
    AVOID_PUBLIC_SIDE = "AVOID_PUBLIC_SIDE"
    BET_1X2 = "BET_1X2"


class BetSelection(Enum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"


@dataclass(frozen=True)
class Action:
    action_type: ActionType
    selection: Optional[BetSelection] = None
    market_key: Optional[str] = None
    selection_key: Optional[str] = None
    source_text: Optional[str] = None


_NO_ACTION_PHRASES = (
    "no bet",
    "pass",
    "skip",
    "stay away",
    "no play",
    "sit out",
)

_AVOID_PUBLIC_PHRASES = (
    "avoid public",
    "avoid the public",
    "public side",
    "fade the public",
    "fade public",
    "against the public",
)


def extract_action(
    full_json: Dict[str, Any],
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
) -> Action:
    verdict = _extract_market_verdict(full_json)
    if not verdict:
        return Action(action_type=ActionType.NO_ACTION)

    verdict_clean = verdict.strip()
    verdict_lower = verdict_clean.lower()

    if _contains_any(verdict_lower, _NO_ACTION_PHRASES):
        return Action(action_type=ActionType.NO_ACTION, source_text=verdict_clean)

    if _contains_any(verdict_lower, _AVOID_PUBLIC_PHRASES):
        return Action(action_type=ActionType.AVOID_PUBLIC_SIDE, source_text=verdict_clean)

    selection = _parse_selection(verdict_lower, home_team, away_team)
    if selection is None:
        return Action(action_type=ActionType.NO_ACTION, source_text=verdict_clean)

    return Action(
        action_type=ActionType.BET_1X2,
        selection=selection,
        market_key="1X2",
        selection_key=selection.value,
        source_text=verdict_clean,
    )


def _extract_market_verdict(full_json: Dict[str, Any]) -> Optional[str]:
    if not full_json:
        return None

    evidence_chain = full_json.get("evidence_chain")
    if isinstance(evidence_chain, dict):
        verdict = evidence_chain.get("market_verdict")
        if isinstance(verdict, str) and verdict.strip():
            return verdict

    for key in ("market_verdict", "betting_recommendation"):
        verdict = full_json.get(key)
        if isinstance(verdict, str) and verdict.strip():
            return verdict

    return None


def _parse_selection(
    verdict_lower: str,
    home_team: Optional[str],
    away_team: Optional[str],
) -> Optional[BetSelection]:
    if "draw no bet" in verdict_lower or "dnb" in verdict_lower:
        return None

    if re.search(r"\b(draw|tie)\b", verdict_lower):
        return BetSelection.DRAW

    if re.search(r"\bhome win\b|\bhome victory\b|\bhome side\b", verdict_lower):
        return BetSelection.HOME

    if re.search(r"\baway win\b|\baway victory\b|\baway side\b", verdict_lower):
        return BetSelection.AWAY

    if re.search(r"\bfade home\b|\bfade the home\b|\bfade home team\b", verdict_lower):
        return BetSelection.AWAY

    if re.search(r"\bfade away\b|\bfade the away\b|\bfade away team\b", verdict_lower):
        return BetSelection.HOME

    normalized_verdict = _normalize_text(verdict_lower)
    home_match = _team_in_text(normalized_verdict, home_team)
    away_match = _team_in_text(normalized_verdict, away_team)

    if home_match and away_match:
        return None

    if home_match:
        return BetSelection.HOME

    if away_match:
        return BetSelection.AWAY

    return None


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _team_in_text(normalized_text: str, team: Optional[str]) -> bool:
    if not team:
        return False
    normalized_team = _normalize_text(team)
    if not normalized_team:
        return False
    return normalized_team in normalized_text
