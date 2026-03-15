"""
Intelligence Validator — quality checks for match_intelligence.json.

v1.8: 6-check system aligned to 7-field output format.
Harder scoring — targets 60-80 range for good output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# v1.8 weight distribution — 6 checks
WEIGHTS = {
    "verdict_quality": 0.20,
    "core_read_substance": 0.25,
    "direction_coherence": 0.20,
    "risk_specificity": 0.15,
    "player_references": 0.10,
    "kill_switch_quality": 0.10,
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
    """Validates match_intelligence.json quality (v1.8 — 6 checks)."""

    def validate(
        self,
        intelligence: Dict[str, Any],
        ml_anchor: Optional[Dict[str, Any]] = None,
        match_pack: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        Run all quality checks. Returns score 0-100.
        Quality gate: >= 60 to pass.
        """
        result = ValidationResult()

        result.components["verdict_quality"] = self._check_verdict(
            intelligence, result.issues
        )
        result.components["core_read_substance"] = self._check_core_read(
            intelligence, result.issues
        )
        result.components["direction_coherence"] = self._check_direction_coherence(
            intelligence, ml_anchor, result.issues
        )
        result.components["risk_specificity"] = self._check_risk_specificity(
            intelligence, result.issues
        )
        result.components["player_references"] = self._check_players(
            intelligence, match_pack, result.issues
        )
        result.components["kill_switch_quality"] = self._check_kill_switch(
            intelligence, result.issues
        )

        # Weighted score
        result.score = sum(
            result.components[k] * WEIGHTS[k] for k in WEIGHTS
        )

        return result

    # ── Check 1: verdict_quality (20%) ──────────────────────────

    def _check_verdict(self, intel: Dict, issues: List[Dict]) -> float:
        """Verdict must contain a team name AND a mechanism."""
        verdict = intel.get("verdict", intel.get("key_question", ""))
        if not verdict:
            issues.append({"check": "verdict_quality", "issue": "Missing verdict"})
            return 0.0

        score = 0.0

        # Must contain at least one proper noun (team name proxy)
        # Look for capitalized words that aren't common English words
        common_words = {
            "The", "This", "That", "Will", "Can", "How", "Why", "What",
            "Home", "Away", "Draw", "Win", "Lose", "Match", "Game",
        }
        cap_words = re.findall(r"\b[A-Z][a-zéèêëàâäùûüôöîïñ]{2,}", verdict)
        team_refs = [w for w in cap_words if w not in common_words]
        if team_refs:
            score += 40
        else:
            issues.append({"check": "verdict_quality", "issue": "No team name in verdict"})

        # Must contain a mechanism word
        mechanism_words = [
            "press", "transition", "counter", "possession", "control",
            "space", "block", "tempo", "set piece", "dominat", "edge",
            "compact", "expose", "overload", "exploit", "pace", "width",
            "high line", "low block", "midfield", "wing", "channel",
            "xg", "concede", "create", "threat", "fragile", "sturdy",
        ]
        has_mechanism = any(w in verdict.lower() for w in mechanism_words)
        if has_mechanism:
            score += 40
        else:
            issues.append({"check": "verdict_quality", "issue": "No mechanism in verdict"})

        # Length: not too short, not too long
        if 20 <= len(verdict) <= 200:
            score += 20
        elif len(verdict) < 20:
            issues.append({"check": "verdict_quality", "issue": "Verdict too short"})
        else:
            score += 10  # too long but still has content

        return score

    # ── Check 2: core_read_substance (25%) ──────────────────────

    def _check_core_read(self, intel: Dict, issues: List[Dict]) -> float:
        """Core read must have ≥2 numbers, ≤5 sentences, no filler."""
        core_read = intel.get("core_read", intel.get("main_read", ""))
        if not core_read:
            issues.append({"check": "core_read_substance", "issue": "Missing core_read"})
            return 0.0

        score = 0.0

        # Must contain ≥2 specific numbers
        numbers = re.findall(r"\d+\.?\d*", core_read)
        if len(numbers) >= 3:
            score += 35
        elif len(numbers) >= 2:
            score += 25
        elif len(numbers) >= 1:
            score += 10
            issues.append({"check": "core_read_substance", "issue": f"Only {len(numbers)} number(s) in core_read (need 2+)"})
        else:
            issues.append({"check": "core_read_substance", "issue": "No numbers in core_read"})

        # Sentence count: ≤5 is tight, >7 is bloated
        sentences = [s.strip() for s in re.split(r'[.!?]+', core_read) if s.strip()]
        if 2 <= len(sentences) <= 5:
            score += 30
        elif len(sentences) == 1:
            score += 15
            issues.append({"check": "core_read_substance", "issue": "Only 1 sentence in core_read"})
        elif len(sentences) > 5:
            score += 10
            issues.append({"check": "core_read_substance", "issue": f"{len(sentences)} sentences in core_read (max 5)"})

        # No filler phrases
        filler = [
            "it remains to be seen", "only time will tell",
            "anything can happen", "football is unpredictable",
            "on paper", "in theory", "it's worth noting",
            "it should be noted", "having said that",
        ]
        has_filler = any(f in core_read.lower() for f in filler)
        if not has_filler:
            score += 20
        else:
            issues.append({"check": "core_read_substance", "issue": "Contains filler phrases"})

        # Must be >50 chars
        if len(core_read) >= 50:
            score += 15
        else:
            issues.append({"check": "core_read_substance", "issue": "core_read too short"})

        return min(score, 100)

    # ── Check 3: direction_coherence (20%) ──────────────────────

    def _check_direction_coherence(
        self, intel: Dict, anchor: Optional[Dict], issues: List[Dict]
    ) -> float:
        """Text direction (from verdict/core_read/lean) must match decision direction."""
        decision = intel.get("decision", {})
        directions = intel.get("directions", decision.get("directions", {}))

        # If no decision yet, fall back to lean vs ML check
        if not directions and not decision:
            return self._check_lean_anchor_legacy(intel, anchor, issues)

        if not directions:
            # Decision exists but no directions trace — partial credit
            return 50.0

        ml_dir = directions.get("ml_anchor", "")
        tactical_dir = directions.get("tactical_read", "")
        final_dir = directions.get("final_decision", "")
        override_reason = directions.get("override_reason")

        score = 0.0

        # Final direction exists
        if final_dir:
            score += 20
        else:
            issues.append({"check": "direction_coherence", "issue": "No final direction resolved"})
            return 0.0

        # Check lean text aligns with tactical_read direction
        lean = intel.get("lean", "")
        if lean:
            inferred = _infer_lean_direction(lean)
            if inferred == tactical_dir:
                score += 30
            else:
                issues.append({
                    "check": "direction_coherence",
                    "issue": f"Lean text implies {inferred} but tactical_read is {tactical_dir}"
                })
                score += 10

        # Agreement bonus / divergence handling
        if ml_dir == tactical_dir:
            score += 30  # full agreement
        elif override_reason:
            score += 20  # diverged but explained
        else:
            issues.append({
                "check": "direction_coherence",
                "issue": f"ML ({ml_dir}) vs tactical ({tactical_dir}) diverge without explanation"
            })

        # Decision action is consistent with direction
        action = decision.get("action", "")
        dec_direction = decision.get("direction", "")
        if action in ("PICK", "LEAN") and dec_direction == final_dir:
            score += 20
        elif action in ("WATCHLIST", "NO_BET"):
            score += 15  # lower-action decisions don't need tight alignment
        elif dec_direction != final_dir:
            issues.append({
                "check": "direction_coherence",
                "issue": f"Decision direction ({dec_direction}) != resolved direction ({final_dir})"
            })

        return min(score, 100)

    def _check_lean_anchor_legacy(
        self, intel: Dict, anchor: Optional[Dict], issues: List[Dict]
    ) -> float:
        """Legacy fallback: lean vs ML anchor check."""
        if not anchor:
            return 50.0
        predicted = anchor.get("predicted_result", "")
        lean = intel.get("lean", "").lower()
        lean_direction = _infer_lean_direction(lean)
        if lean_direction == predicted:
            return 100.0
        confidence = intel.get("confidence", "Medium")
        if confidence in ("Low", "Medium", "Medium-Low"):
            return 60.0
        issues.append({
            "check": "direction_coherence",
            "issue": f"Lean ({lean_direction}) disagrees with ML ({predicted})"
        })
        return 40.0

    # ── Check 4: risk_specificity (15%) ─────────────────────────

    def _check_risk_specificity(self, intel: Dict, issues: List[Dict]) -> float:
        """main_risk must have concrete data, not generic warnings."""
        main_risk = intel.get("main_risk", "")

        # Fall back to risks list if main_risk not present
        if not main_risk:
            risks = intel.get("risks", [])
            main_risk = risks[0] if risks else ""

        if not main_risk:
            issues.append({"check": "risk_specificity", "issue": "Missing main_risk"})
            return 0.0

        score = 0.0

        # Must contain a number (specific data)
        if re.search(r"\d+\.?\d*", main_risk):
            score += 40
        else:
            issues.append({"check": "risk_specificity", "issue": "main_risk has no concrete data"})

        # Must be specific enough (>30 chars)
        if len(main_risk) >= 30:
            score += 25
        elif len(main_risk) >= 15:
            score += 10
        else:
            issues.append({"check": "risk_specificity", "issue": "main_risk too short"})

        # Not generic
        generic_risks = [
            "anything can happen", "football is unpredictable",
            "injuries could affect", "weather could play a role",
            "form can change", "they could lose",
        ]
        is_generic = any(g in main_risk.lower() for g in generic_risks)
        if not is_generic:
            score += 20
        else:
            issues.append({"check": "risk_specificity", "issue": "main_risk is generic"})

        # Contains a team or player reference
        cap_words = re.findall(r"\b[A-Z][a-zéèêëàâäùûüôöîïñ]{2,}", main_risk)
        common = {"The", "This", "That", "Home", "Away"}
        refs = [w for w in cap_words if w not in common]
        if refs:
            score += 15
        else:
            issues.append({"check": "risk_specificity", "issue": "main_risk has no team/player reference"})

        return min(score, 100)

    # ── Check 5: player_references (10%) ────────────────────────

    def _check_players(
        self, intel: Dict, match_pack: Optional[Dict], issues: List[Dict]
    ) -> float:
        """Only score when player data confidence is high (key_players non-empty)."""
        # Check if match_pack has player data
        has_player_data = False
        if match_pack:
            home_players = match_pack.get("home_team", {}).get("key_players", [])
            away_players = match_pack.get("away_team", {}).get("key_players", [])
            has_player_data = bool(home_players or away_players)

        if not has_player_data:
            # No player data in pack — don't penalize, return neutral
            return 50.0

        # Player data exists — check if intelligence references them
        all_text = _collect_all_text(intel)

        name_pattern = r"[A-Z][a-zéèêëàâäùûüôöîïñ]+(?:\s+(?:de\s+)?[A-Z][a-zéèêëàâäùûüôöîïñ]+)*"
        names = re.findall(name_pattern, all_text)

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
            issues.append({"check": "player_references", "issue": "Only 1 player named (pack has player data)"})
            return 40.0

        issues.append({"check": "player_references", "issue": "No players named despite pack having player data"})
        return 10.0

    # ── Check 6: kill_switch_quality (10%) ──────────────────────

    def _check_kill_switch(self, intel: Dict, issues: List[Dict]) -> float:
        """Kill switch must be specific and actionable, not generic."""
        kill_switch = intel.get("kill_switch", intel.get("invalidation_condition", ""))
        if not kill_switch:
            issues.append({"check": "kill_switch_quality", "issue": "Missing kill_switch"})
            return 0.0

        score = 0.0

        # Must be specific enough
        if len(kill_switch) >= 20:
            score += 30
        else:
            issues.append({"check": "kill_switch_quality", "issue": "kill_switch too short"})
            score += 10

        # Must contain a number or specific condition
        has_number = bool(re.search(r"\d+", kill_switch))
        has_specific = any(w in kill_switch.lower() for w in [
            "injury", "lineup", "out", "miss", "suspend",
            "rain", "pitch", "minute", "goal", "red card",
            "formation", "bench", "start",
        ])
        if has_number:
            score += 30
        elif has_specific:
            score += 20
        else:
            issues.append({"check": "kill_switch_quality", "issue": "kill_switch lacks specific trigger"})

        # Not generic
        generic_ks = [
            "if something changes", "if form drops",
            "anything unexpected", "if they don't play well",
        ]
        is_generic = any(g in kill_switch.lower() for g in generic_ks)
        if not is_generic:
            score += 25
        else:
            issues.append({"check": "kill_switch_quality", "issue": "kill_switch is generic"})

        # Contains a team/player reference
        cap_words = re.findall(r"\b[A-Z][a-zéèêëàâäùûüôöîïñ]{2,}", kill_switch)
        common = {"The", "This", "That", "Home", "Away", "If"}
        refs = [w for w in cap_words if w not in common]
        if refs:
            score += 15

        return min(score, 100)

    def _check_data_plausibility(
        self, intel: Dict, match_pack: Optional[Dict], issues: List[Dict]
    ) -> float:
        """Check if numbers cited in evidence actually exist in match_pack."""
        if not match_pack:
            return 50.0  # neutral

        all_evidence = intel.get("evidence_for", []) + intel.get("evidence_against", [])
        if not all_evidence:
            return 50.0

        pack_text = str(match_pack)
        found = 0
        total = 0

        for e in all_evidence:
            data = e.get("data", "")
            numbers = re.findall(r"\d+\.?\d*", data)
            for num in numbers:
                total += 1
                if num in pack_text:
                    found += 1

        if total == 0:
            return 50.0

        pct = found / total
        if pct < 0.5:
            issues.append({
                "check": "data_plausibility",
                "issue": f"Only {pct:.0%} of cited numbers found in match_pack",
            })

        return pct * 100


def build_evaluation_record(
    match_pack: Dict,
    ml_anchor: Dict,
    match_signals: Dict,
    intelligence: Dict,
    validation: ValidationResult,
    rubric_result=None,
    data_quality_result=None,
    trace_data: Dict = None,
) -> Dict[str, Any]:
    """
    Build evaluation_record.json — enriched snapshot for later comparison.
    """
    fixture = match_pack.get("fixture", {})

    record = {
        "schema_version": "1.5",
        "match_id": fixture.get("fixture_id", ""),
        "fixture": {
            "home_team": fixture.get("home_team", ""),
            "away_team": fixture.get("away_team", ""),
            "round": fixture.get("round_number", 0),
            "league": fixture.get("league", ""),
        },
        "method_version": "v1.6-mi-engine",
        "generated_at": datetime.utcnow().isoformat() + "Z",
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
            "n_mechanisms": len(intelligence.get("tactical_mechanisms", [])),
            "has_game_script": bool(intelligence.get("game_script")),
            "invalidation_condition": intelligence.get("invalidation_condition", ""),
        },
        "validator_score": round(validation.score, 1),
        "validator_details": {
            k: round(v, 1) for k, v in validation.components.items()
        },
        "validator_issues": validation.issues,
    }

    # --- ENRICHMENTS ---

    # Input trace (tools called/failed, data gaps)
    if trace_data:
        summary = trace_data.get("summary", {})
        record["input_trace"] = {
            "tools_called": summary.get("tools_called", []),
            "tools_failed": summary.get("tools_failed", []),
            "data_gaps": [],
        }
        # Extract data gaps from DQ warnings
        if data_quality_result:
            record["input_trace"]["data_gaps"] = [
                w.get("issue", "") for w in data_quality_result.warnings
                if w.get("severity") in ("high", "critical")
            ]

    # LLM trace
    llm_trace = intelligence.get("_llm_trace")
    if llm_trace:
        record["llm_trace"] = llm_trace

    # Rubric score
    if rubric_result:
        record["rubric_score"] = round(rubric_result.score, 1)
        record["rubric_details"] = rubric_result.to_dict()

    # Data quality
    if data_quality_result:
        record["data_quality"] = data_quality_result.to_dict()

    # Consistency check
    record["consistency_check"] = _compute_consistency(
        intelligence, ml_anchor, match_signals, match_pack
    )

    # Filled post-match
    record["result"] = None
    record["result_added_at"] = None
    record["post_match_rubric"] = None

    return record


def _compute_consistency(
    intelligence: Dict,
    ml_anchor: Dict,
    match_signals: Dict,
    match_pack: Dict,
) -> Dict[str, Any]:
    """Compute consistency checks between intelligence and data sources."""
    # Signal-analysis alignment
    signals = match_signals.get("signals", {})
    lean = intelligence.get("lean", "").lower()
    lean_dir = _infer_lean_direction(lean)
    predicted = ml_anchor.get("predicted_result", "")

    # ML lean alignment
    ml_aligned = lean_dir == predicted

    # Signal consistency score (0-1)
    alignment_score = 0.5  # neutral start
    if signals.get("draw_pressure_risk") and "draw" in lean:
        alignment_score += 0.15
    if signals.get("home_territorial_edge") and lean_dir == "H":
        alignment_score += 0.15
    if signals.get("away_transition_threat") and lean_dir == "A":
        alignment_score += 0.15
    if signals.get("upset_potential") and lean_dir != "H":
        alignment_score += 0.05
    alignment_score = min(1.0, alignment_score)

    # Data cited correctly (check if numbers in evidence exist in match_pack)
    pack_text = str(match_pack)
    all_evidence = intelligence.get("evidence_for", []) + intelligence.get("evidence_against", [])
    cited_numbers = []
    found_numbers = []
    for e in all_evidence:
        nums = re.findall(r"\d+\.?\d*", e.get("data", ""))
        cited_numbers.extend(nums)
        found_numbers.extend(n for n in nums if n in pack_text)

    data_cited_correctly = len(found_numbers) >= len(cited_numbers) * 0.6 if cited_numbers else True

    flagged = []
    if not ml_aligned:
        flagged.append(f"Lean ({lean_dir}) disagrees with ML ({predicted})")
    if cited_numbers and not data_cited_correctly:
        flagged.append(
            f"Only {len(found_numbers)}/{len(cited_numbers)} cited numbers found in match_pack"
        )

    return {
        "signal_analysis_alignment": round(alignment_score, 2),
        "ml_lean_alignment": ml_aligned,
        "data_cited_correctly": data_cited_correctly,
        "flagged_inconsistencies": flagged,
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
