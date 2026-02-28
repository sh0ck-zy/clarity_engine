"""
Anti-hallucination guardrails for LLM-generated drafts.

Validates draft text against facts and report to ensure no fabricated data.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

# Reuse banned words from the existing renderer
from renderers.match_renderer import _BANNED_WORDS


def validate_draft(text: str, facts: Dict[str, Any], report: Dict[str, Any]) -> List[str]:
    """
    Validate a draft text against source facts and report.

    Returns list of violation strings. Empty list = draft is safe.
    """
    violations = []
    text_lower = text.lower()

    # 1. Banned causality words
    for word in _BANNED_WORDS:
        if word in text_lower:
            violations.append(f"banned_word: '{word}'")

    # 2. Percentage coherence — any % must match facts.ml.probabilities ±1.5pp
    probs = facts["ml"]["probabilities"]
    valid_pcts = set()
    for p in probs.values():
        pct = p * 100
        valid_pcts.add(round(pct, 1))
        valid_pcts.add(round(pct, 0))

    found_pcts = re.findall(r"(\d+\.?\d*)%", text)
    for pct_str in found_pcts:
        pct_val = float(pct_str)
        if not any(abs(pct_val - p * 100) < 1.5 for p in probs.values()):
            violations.append(f"unverified_percentage: {pct_str}%")

    # 3. Team names present
    home = facts["fixture"]["home_team"].lower()
    away = facts["fixture"]["away_team"].lower()
    if not _name_present(home, text_lower):
        violations.append(f"missing_team: {facts['fixture']['home_team']}")
    if not _name_present(away, text_lower):
        violations.append(f"missing_team: {facts['fixture']['away_team']}")

    # 4. Audit trail (report_id or run_id)
    report_id = report.get("report_id", "")
    run_id = facts["provenance"].get("run_id", "")
    if report_id and report_id not in text and run_id and run_id not in text:
        violations.append("missing_audit_trail: no report_id or run_id in text")

    return violations


def _name_present(team_lower: str, text_lower: str) -> bool:
    """Check if team name (or significant part) appears in text."""
    if team_lower in text_lower:
        return True
    # Check significant parts (>3 chars)
    for part in team_lower.split():
        if len(part) > 3 and part in text_lower:
            return True
    return False
