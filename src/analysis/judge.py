import re
from typing import Dict, Tuple


def _parse_score(score_str: str) -> Tuple[int | None, int | None]:
    """Best-effort parser for scorelines like '2-1' or '2 : 1'."""
    if not score_str:
        return (None, None)
    parts = re.findall(r"\d+", str(score_str))
    if len(parts) >= 2:
        return (int(parts[0]), int(parts[1]))
    return (None, None)


class ClarityJudge:
    """
    Lightweight evaluator that compares the model prediction to reality and returns
    a rough diagnostic score plus narrative.
    """

    def evaluate(self, prediction: Dict, actual_data: Dict) -> Dict:
        pred_meta = prediction.get("prediction", {}) if prediction else {}
        pred_score = pred_meta.get("scoreline") or ""
        pred_conf = pred_meta.get("confidence")
        pred_home, pred_away = _parse_score(pred_score)

        actual_score = actual_data.get("score") if actual_data else ""
        act_home, act_away = _parse_score(actual_score)

        if act_home is None or act_away is None:
            return {
                "score": None,
                "verdict": "no_result",
                "reasoning": "No final score available to evaluate this analysis.",
            }

        goal_error = 0
        if pred_home is not None and pred_away is not None:
            goal_error = abs(pred_home - act_home) + abs(pred_away - act_away)

        base_score = max(0, 100 - goal_error * 20)

        verdict = "accurate" if base_score >= 70 else "off_target"
        if goal_error == 0:
            verdict = "spot_on"

        # Factor in confidence if present.
        confidence_penalty = 0
        if isinstance(pred_conf, (int, float)):
            if pred_conf < 50 and verdict == "accurate":
                verdict = "cautious_hit"
            confidence_penalty = max(0, 50 - pred_conf) * 0.1

        final_score = max(0, int(base_score - confidence_penalty))

        reasoning_bits = [
            f"Predicted {pred_score or 'N/A'} vs actual {actual_score}",
            f"Goal error: {goal_error}",
        ]
        if pred_conf is not None:
            reasoning_bits.append(f"Confidence noted at {pred_conf}%")
        if actual_data.get("stats"):
            reasoning_bits.append("xG data captured for reference.")

        return {
            "score": final_score,
            "verdict": verdict,
            "reasoning": "; ".join(reasoning_bits),
        }
