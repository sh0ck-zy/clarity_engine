"""
Data Quality Checks — plausibility checks on match_pack BEFORE it reaches the LLM.

v1.7: Two independent scores (completeness + integrity) with binary READY/SKIP gate.
MI gate is strictly about data integrity — "can we trust the inputs?"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DataQualityResult:
    """Result of data quality checks on a match_pack."""

    completeness_score: float = 100.0  # 0-100: are fields present?
    integrity_score: float = 100.0     # 0-100: do fields make sense?
    completeness_issues: List[Dict[str, str]] = field(default_factory=list)
    integrity_issues: List[Dict[str, str]] = field(default_factory=list)
    critical_flags: List[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Combined score for backward compatibility."""
        return (self.completeness_score + self.integrity_score) / 2

    @property
    def warnings(self) -> List[Dict[str, str]]:
        """All issues combined for backward compatibility."""
        return self.completeness_issues + self.integrity_issues

    @property
    def passable(self) -> bool:
        return self.completeness_score >= 30 and self.integrity_score >= 30

    @property
    def mi_status(self) -> str:
        """READY = data is trustworthy, run MI. SKIP = data is broken, don't waste tokens."""
        if self.completeness_score < 50 or self.integrity_score < 40:
            return "skip"
        return "ready"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "completeness_score": round(self.completeness_score, 1),
            "integrity_score": round(self.integrity_score, 1),
            "mi_status": self.mi_status,
            "completeness_issues": self.completeness_issues,
            "integrity_issues": self.integrity_issues,
            "critical_flags": self.critical_flags,
        }


def _get_nested(d: Dict, *keys, default=None):
    """Safely get a nested dict value."""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current


def check_match_pack_quality(match_pack: Dict[str, Any]) -> DataQualityResult:
    """
    Run plausibility checks on a match_pack.

    Returns DataQualityResult with separate completeness and integrity scores.
    """
    result = DataQualityResult()

    for side in ("home", "away"):
        team_name = _get_nested(match_pack, "fixture", f"{side}_team", default=side)
        team = match_pack.get(side, {})
        state = team.get("state", {})
        form = state.get("form", {})
        form_detail = team.get("form_detail", {})

        # === COMPLETENESS CHECKS (are fields present?) ===

        # No team state: -50
        if not state:
            result.completeness_issues.append({
                "field": f"{side}.state",
                "issue": f"{team_name} has no team state data",
                "severity": "critical",
            })
            result.completeness_score -= 50

        # No key players: -15
        if not team.get("key_players"):
            result.completeness_issues.append({
                "field": f"{side}.key_players",
                "issue": f"{team_name} has no key players data",
                "severity": "medium",
            })
            result.completeness_score -= 15

        # No attack/defense profile: -20
        if not team.get("attack_profile") and not team.get("defense_profile"):
            result.completeness_issues.append({
                "field": f"{side}.attack_profile",
                "issue": f"{team_name} has no attack/defense profile",
                "severity": "medium",
            })
            result.completeness_score -= 20

        # No form detail: -15
        if not form_detail:
            result.completeness_issues.append({
                "field": f"{side}.form_detail",
                "issue": f"{team_name} has no form detail",
                "severity": "medium",
            })
            result.completeness_score -= 15

        # === INTEGRITY CHECKS (do fields make sense?) ===

        # xG=0 but goals > 0: -30
        xg_for = form.get("xg_for_last5")
        goals_last5 = form_detail.get("goals", {}).get("scored", 0) or 0
        form_string = form.get("form_string", "")
        wins_from_form = form_string.count("W")

        if xg_for is not None and (xg_for == 0 or xg_for == 0.0):
            if goals_last5 > 0 or wins_from_form > 0:
                result.integrity_issues.append({
                    "field": f"{side}.state.form.xg_for_last5",
                    "issue": f"xG=0.0 but {team_name} scored {goals_last5} goals in last 5",
                    "severity": "high",
                })
                result.integrity_score -= 30

        # xGA=0 but conceded > 0: -30
        xg_against = form.get("xg_against_last5")
        goals_conceded = form_detail.get("goals", {}).get("conceded", 0) or 0
        if xg_against is not None and (xg_against == 0 or xg_against == 0.0):
            if goals_conceded > 0:
                result.integrity_issues.append({
                    "field": f"{side}.state.form.xg_against_last5",
                    "issue": f"xGA=0.0 but {team_name} conceded {goals_conceded} goals in last 5",
                    "severity": "high",
                })
                result.integrity_score -= 30

        # Possession exactly 50.0%: -20
        possession = _get_nested(state, "style", "avg_possession", default=None)
        if possession is not None and possession == 50.0:
            result.integrity_issues.append({
                "field": f"{side}.state.style.avg_possession",
                "issue": f"{team_name} possession exactly 50.0% — likely default/missing",
                "severity": "high",
            })
            result.integrity_score -= 20

        # xG/game=0 but goals > 3: -20
        attack = team.get("attack_profile", {})
        xg_per_game = attack.get("xg_per_game", None)
        if xg_per_game is not None and (xg_per_game == 0 or xg_per_game == 0.0):
            if goals_last5 > 3:
                result.integrity_issues.append({
                    "field": f"{side}.attack_profile.xg_per_game",
                    "issue": f"xG/game=0 but {team_name} scored {goals_last5} in last 5",
                    "severity": "high",
                })
                result.integrity_score -= 20

        # Form string != form points: -10
        form_points = form.get("form_points")
        if form_string and form_points is not None:
            expected_pts = (
                form_string.count("W") * 3
                + form_string.count("D") * 1
            )
            if len(form_string) >= 3 and abs(expected_pts - form_points) > 1:
                result.integrity_issues.append({
                    "field": f"{side}.state.form.form_points",
                    "issue": (
                        f"{team_name} form_string={form_string} "
                        f"implies ~{expected_pts} pts but form_points={form_points}"
                    ),
                    "severity": "low",
                })
                result.integrity_score -= 10

    # --- Build critical_flags (structural data corruption) ---
    for w in result.completeness_issues:
        severity = w.get("severity", "")
        field_path = w.get("field", "")
        if severity == "critical":
            result.critical_flags.append(f"missing_state:{field_path}")

    for w in result.integrity_issues:
        severity = w.get("severity", "")
        issue = w.get("issue", "")
        field_path = w.get("field", "")
        if severity == "high":
            if "xG=0" in issue or "xG/game=0" in issue:
                result.critical_flags.append(f"missing_xg:{field_path}")
            elif "xGA=0" in issue:
                result.critical_flags.append(f"missing_xga:{field_path}")
            elif "possession" in issue.lower() and "50.0" in issue:
                result.critical_flags.append(f"default_possession:{field_path}")

    # Deduplicate critical flags
    result.critical_flags = sorted(set(result.critical_flags))

    # Clamp scores
    result.completeness_score = max(0.0, result.completeness_score)
    result.integrity_score = max(0.0, result.integrity_score)

    return result


def annotate_prompt_warnings(
    match_pack: Dict[str, Any],
    dq_result: DataQualityResult,
) -> Dict[str, List[str]]:
    """
    Build annotations for the LLM prompt based on data quality warnings.

    Returns a dict mapping field paths to human-readable annotations.
    These should be injected into the prompt so the LLM knows which data
    is unreliable.
    """
    annotations: Dict[str, List[str]] = {}

    for w in dq_result.warnings:
        field = w["field"]
        severity = w["severity"]
        issue = w["issue"]

        if severity in ("high", "critical"):
            if field not in annotations:
                annotations[field] = []
            annotations[field].append(f"⚠ DATA WARNING: {issue}")

    return annotations
