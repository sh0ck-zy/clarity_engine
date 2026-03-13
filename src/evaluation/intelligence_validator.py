"""
Intelligence Validator — quality checks for match_intelligence.json.

Scores 0-100 across 7 dimensions including usefulness.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Weight distribution across checks
WEIGHTS = {
    "key_question_quality": 0.15,
    "evidence_balance": 0.20,
    "scenario_quality": 0.20,
    "data_citations": 0.15,
    "lean_anchor_consistency": 0.10,
    "player_references": 0.10,
    "usefulness": 0.10,
}


@dataclass
class ValidationResult:
    """Result of intelligence validation."""

    score: float = 0.0
    components: Dict[str, float] = field(default_factory=dict)
    issues: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "components": {k: round(v, 1) for k, v in self.components.items()},
            "issues": self.issues,
            "passed": self.score >= 60,
        }


class IntelligenceValidator:
    """Validates match_intelligence.json quality."""

    def validate(
        self,
        intelligence: Dict[str, Any],
        ml_anchor: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        Run all quality checks. Returns score 0-100.
        Quality gate: >= 60 to pass.
        """
        result = ValidationResult()

        # Run each check
        result.components["key_question_quality"] = self._check_key_question(
            intelligence, result.issues
        )
        result.components["evidence_balance"] = self._check_evidence(
            intelligence, result.issues
        )
        result.components["scenario_quality"] = self._check_scenarios(
            intelligence, result.issues
        )
        result.components["data_citations"] = self._check_citations(
            intelligence, result.issues
        )
        result.components["lean_anchor_consistency"] = self._check_lean_anchor(
            intelligence, ml_anchor, result.issues
        )
        result.components["player_references"] = self._check_players(
            intelligence, result.issues
        )
        result.components["usefulness"] = self._check_usefulness(
            intelligence, result.issues
        )

        # Weighted score
        result.score = sum(
            result.components[k] * WEIGHTS[k] for k in WEIGHTS
        )

        return result

    def _check_key_question(
        self, intel: Dict, issues: List[Dict]
    ) -> float:
        """Is the key question tactical, specific, and a real question?"""
        kq = intel.get("key_question", "")

        if not kq:
            issues.append({"check": "key_question", "issue": "Missing key_question"})
            return 0.0

        score = 0.0

        # Is it a question?
        if "?" in kq:
            score += 30
        else:
            issues.append({"check": "key_question", "issue": "Not a question (no ?)"})

        # Long enough to be meaningful?
        if len(kq) > 30:
            score += 20
        else:
            issues.append({"check": "key_question", "issue": "Too short"})

        # Contains at least one team/tactical term?
        tactical_terms = [
            "press", "transition", "counter", "possession", "control",
            "space", "line", "block", "width", "tempo", "formation",
            "midfield", "defense", "attack", "pace", "set piece",
            "dominat", "edge", "threat", "fragile", "compact",
        ]
        has_tactical = any(t.lower() in kq.lower() for t in tactical_terms)
        if has_tactical:
            score += 30
        else:
            issues.append({"check": "key_question", "issue": "Not clearly tactical"})

        # Not too generic?
        generic_patterns = [
            r"^who will win",
            r"^can .+ win",
            r"^will .+ beat",
            r"^which team is better",
        ]
        is_generic = any(re.match(p, kq, re.IGNORECASE) for p in generic_patterns)
        if not is_generic:
            score += 20
        else:
            issues.append({"check": "key_question", "issue": "Too generic"})

        return score

    def _check_evidence(self, intel: Dict, issues: List[Dict]) -> float:
        """Are evidence for/against balanced and substantive?"""
        ev_for = intel.get("evidence_for", [])
        ev_against = intel.get("evidence_against", [])

        score = 0.0

        # Minimum counts
        if len(ev_for) >= 3:
            score += 30
        elif len(ev_for) >= 2:
            score += 15
        else:
            issues.append({"check": "evidence", "issue": f"Only {len(ev_for)} evidence_for (need 3+)"})

        if len(ev_against) >= 2:
            score += 30
        elif len(ev_against) >= 1:
            score += 15
        else:
            issues.append({"check": "evidence", "issue": f"Only {len(ev_against)} evidence_against (need 2+)"})

        # All have data citations?
        all_items = ev_for + ev_against
        if all_items:
            with_data = sum(1 for e in all_items if e.get("data"))
            data_pct = with_data / len(all_items)
            score += data_pct * 20
            if data_pct < 0.8:
                issues.append({"check": "evidence", "issue": f"Only {data_pct:.0%} items cite data"})

        # Strength variety?
        strengths = [e.get("strength") for e in all_items if e.get("strength")]
        if len(set(strengths)) >= 2:
            score += 20
        elif strengths:
            score += 10

        return score

    def _check_scenarios(self, intel: Dict, issues: List[Dict]) -> float:
        """Are scenarios plausible, distinct, and properly structured?"""
        scenarios = intel.get("scenarios", [])

        score = 0.0

        # Count check
        if 2 <= len(scenarios) <= 4:
            score += 25
        elif len(scenarios) == 1:
            score += 10
            issues.append({"check": "scenarios", "issue": "Only 1 scenario (need 2-3)"})
        else:
            issues.append({"check": "scenarios", "issue": f"{len(scenarios)} scenarios (need 2-4)"})

        # Has "most likely"?
        likelihoods = [s.get("likelihood", "") for s in scenarios]
        if "most likely" in likelihoods:
            score += 25
        else:
            issues.append({"check": "scenarios", "issue": "No 'most likely' scenario"})

        # Different likelihoods?
        if len(set(likelihoods)) >= 2:
            score += 15
        else:
            issues.append({"check": "scenarios", "issue": "All scenarios same likelihood"})

        # Have triggers?
        with_triggers = sum(1 for s in scenarios if s.get("trigger"))
        if scenarios and with_triggers == len(scenarios):
            score += 20
        elif scenarios:
            score += 10

        # Different names?
        names = [s.get("name", "") for s in scenarios]
        if len(set(names)) == len(names) and all(names):
            score += 15

        return score

    def _check_citations(self, intel: Dict, issues: List[Dict]) -> float:
        """Do evidence claims reference specific numbers?"""
        all_evidence = intel.get("evidence_for", []) + intel.get("evidence_against", [])

        if not all_evidence:
            return 0.0

        # Check for numbers in data field
        with_numbers = 0
        for e in all_evidence:
            data = e.get("data", "")
            if re.search(r"\d+\.?\d*", data):
                with_numbers += 1

        pct = with_numbers / len(all_evidence)
        score = pct * 80

        # Check main_read for numbers too
        main_read = intel.get("main_read", "")
        if re.search(r"\d+\.?\d*", main_read):
            score += 20
        else:
            issues.append({"check": "citations", "issue": "main_read has no specific numbers"})

        return min(score, 100)

    def _check_lean_anchor(
        self, intel: Dict, anchor: Optional[Dict], issues: List[Dict]
    ) -> float:
        """Does lean direction generally match ML direction?"""
        if not anchor:
            return 50.0  # neutral if no anchor

        predicted = anchor.get("predicted_result", "")
        lean = intel.get("lean", "").lower()
        confidence = intel.get("confidence", "Medium")

        # Determine lean direction from text
        lean_direction = _infer_lean_direction(lean)

        # If lean agrees with ML, good
        if lean_direction == predicted:
            return 100.0

        # If lean disagrees but confidence is low or Medium, acceptable
        # (the lean CAN disagree if evidence supports it)
        if confidence in ("Low", "Medium"):
            return 60.0

        # High confidence lean that disagrees with ML — flag it
        issues.append({
            "check": "lean_anchor",
            "issue": f"High confidence lean disagrees with ML ({predicted})"
        })
        return 30.0

    def _check_players(self, intel: Dict, issues: List[Dict]) -> float:
        """Are specific players mentioned with context?"""
        # Collect all text
        all_text = _collect_all_text(intel)

        # Count capitalized multi-word names (heuristic for player names)
        # Look for patterns like "Salah", "De Bruyne", "Mbappé"
        name_pattern = r"[A-Z][a-zéèêëàâäùûüôöîïñ]+(?:\s+(?:de\s+)?[A-Z][a-zéèêëàâäùûüôöîïñ]+)*"
        names = re.findall(name_pattern, all_text)

        # Filter out common non-name words
        non_names = {
            "Home", "Away", "Draw", "Medium", "High", "Low", "Strong",
            "Moderate", "Weak", "Control", "Transition", "Stalemate",
            "The", "This", "That", "Most", "Score", "First",
        }
        player_names = [n for n in names if n not in non_names and len(n) > 3]
        unique_names = set(player_names)

        if len(unique_names) >= 3:
            return 100.0
        if len(unique_names) >= 2:
            return 70.0
        if len(unique_names) >= 1:
            issues.append({"check": "players", "issue": "Only 1 player named"})
            return 40.0

        issues.append({"check": "players", "issue": "No players named"})
        return 0.0

    def _check_usefulness(self, intel: Dict, issues: List[Dict]) -> float:
        """Does the analysis help form a clear opinion about the match?"""
        score = 0.0

        # Key question is non-generic (already checked, but weight here)
        kq = intel.get("key_question", "")
        if len(kq) > 40 and "?" in kq:
            score += 30

        # Lean is specific (not just "Home win" or "Draw")
        lean = intel.get("lean", "")
        generic_leans = ["home win", "away win", "draw", "home", "away"]
        if lean and lean.lower().strip() not in generic_leans and len(lean) > 15:
            score += 30
        else:
            issues.append({"check": "usefulness", "issue": "Lean is too generic"})

        # Risks are actionable (have data, not generic)
        risks = intel.get("risks", [])
        specific_risks = sum(1 for r in risks if re.search(r"\d", r))
        if specific_risks >= 2:
            score += 20
        elif specific_risks >= 1:
            score += 10
        else:
            issues.append({"check": "usefulness", "issue": "Risks lack specific data"})

        # Confidence is justified (not just "Medium" without context)
        confidence = intel.get("confidence", "")
        if confidence in ("High", "Low"):
            # Extreme confidence = more informative
            score += 20
        elif confidence == "Medium":
            # Medium is the safe default — less informative
            score += 10

        return score


def build_evaluation_record(
    match_pack: Dict,
    ml_anchor: Dict,
    match_signals: Dict,
    intelligence: Dict,
    validation: ValidationResult,
) -> Dict[str, Any]:
    """
    Build evaluation_record.json — snapshot for later comparison.
    """
    fixture = match_pack.get("fixture", {})

    return {
        "schema_version": "1.5",
        "match_id": fixture.get("fixture_id", ""),
        "fixture": {
            "home_team": fixture.get("home_team", ""),
            "away_team": fixture.get("away_team", ""),
            "round": fixture.get("round_number", 0),
            "league": fixture.get("league", ""),
        },
        "method_version": "v1.5-mi-engine",
        "generated_at": datetime.utcnow().isoformat() + "Z"
        if "datetime" in dir()
        else intelligence.get("built_at", ""),
        "artefacts": {
            "match_pack": "match_pack.json",
            "ml_anchor": "ml_anchor.json",
            "match_signals": "match_signals.json",
            "match_intelligence": "match_intelligence.json",
        },
        "ml_anchor_summary": {
            "probabilities": ml_anchor.get("probabilities", {}),
            "predicted_result": ml_anchor.get("predicted_result", ""),
            "confidence": ml_anchor.get("confidence", ""),
        },
        "intelligence_summary": {
            "key_question": intelligence.get("key_question", ""),
            "lean": intelligence.get("lean", ""),
            "confidence": intelligence.get("confidence", ""),
            "n_evidence_for": len(intelligence.get("evidence_for", [])),
            "n_evidence_against": len(intelligence.get("evidence_against", [])),
            "n_scenarios": len(intelligence.get("scenarios", [])),
        },
        "validator_score": round(validation.score, 1),
        "validator_details": {
            k: round(v, 1) for k, v in validation.components.items()
        },
        "validator_issues": validation.issues,
        # Filled post-match
        "result": None,
        "result_added_at": None,
    }


def _infer_lean_direction(lean: str) -> str:
    """Infer H/D/A direction from lean text."""
    lean_lower = lean.lower()
    home_words = ["home", "host", "favourite", "favorite", "control"]
    away_words = ["away", "visitor", "underdog", "upset"]
    draw_words = ["draw", "stalemate", "even", "balanced", "tight"]

    home_score = sum(1 for w in home_words if w in lean_lower)
    away_score = sum(1 for w in away_words if w in lean_lower)
    draw_score = sum(1 for w in draw_words if w in lean_lower)

    if draw_score > home_score and draw_score > away_score:
        return "D"
    if away_score > home_score:
        return "A"
    return "H"  # default to home if ambiguous


def _collect_all_text(intel: Dict) -> str:
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
        parts.append(s.get("trigger", ""))
    for r in intel.get("risks", []):
        parts.append(r)

    return " ".join(parts)


# Fix the import for evaluation_record
from datetime import datetime  # noqa: E402
