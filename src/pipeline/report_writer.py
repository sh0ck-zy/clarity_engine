"""
Report writer: transforms facts.json into report.json using an LLM.

The LLM generates ONLY the narrative sections (summary, analysis).
Structured numeric fields (probabilities, prediction, signals, risk_flags)
are copied verbatim from facts — never passed through the LLM.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from pipeline.hashing import compute_hash

PROMPT_VERSION = "writer_v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.3

_SYSTEM_PROMPT = """\
You are a football match analyst writer for Clarity Engine.
Your job: write a structured pre-match analysis based ONLY on the facts provided.

RULES:
- Use ONLY data present in the facts JSON. Do not invent statistics, player names, or claims.
- Use hedged language proportional to confidence level (high → "strong lean", medium → "moderate lean", low → "tight call").
- NEVER use: guaranteed, certain, definitely, surely, will win, will lose, must win, no chance, impossible.
- Reference specific numbers from the facts (probabilities, feature values, drivers).
- Be concise and direct. Avoid filler.

OUTPUT FORMAT (respond with ONLY this JSON, no markdown fences):
{
  "headline": "Short punchy headline (max 80 chars)",
  "overview": "2-3 sentence overview of the match prediction.",
  "prediction_rationale": "Explain WHY the model leans this way, citing specific drivers.",
  "key_factors": ["Factor 1 with number", "Factor 2 with number", "Factor 3"],
  "risks": ["Risk or caveat 1", "Risk 2"],
  "confidence_assessment": "1-2 sentences on confidence level and what it means."
}
"""


def write_report(
    facts: Dict[str, Any],
    prompt_version: str = PROMPT_VERSION,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
) -> Dict[str, Any]:
    """
    Generate report.json from facts.json.

    The LLM writes narrative sections. Numeric fields are copied verbatim from facts.
    Falls back to template if LLM fails.

    Returns:
        report dict conforming to report.schema.json.
    """
    facts_hash = facts["provenance"]["facts_hash"]
    fixture = facts["fixture"]

    # Build report_id from facts hash
    report_id = "rep_" + compute_hash(facts, self_hash_path=["provenance", "facts_hash"])[7:17]

    # Try LLM generation
    try:
        narrative = _call_llm(facts, model, temperature)
    except Exception as e:
        print(f"  LLM writer failed: {e}. Using template fallback.")
        narrative = _template_fallback(facts)
        model_used = "template"
        generation_mode = "template_fallback"
    else:
        model_used = model
        generation_mode = "llm"

    return {
        "schema_version": "1.0",
        "report_id": report_id,
        "fixture": {
            "fixture_id": fixture["fixture_id"],
            "round_number": fixture["round_number"],
            "match_date": fixture["match_date"],
            "home_team": fixture["home_team"],
            "away_team": fixture["away_team"],
        },
        "summary": {
            "headline": narrative["headline"],
            "overview": narrative["overview"],
        },
        "analysis": {
            "prediction_rationale": narrative["prediction_rationale"],
            "key_factors": narrative["key_factors"],
            "risks": narrative["risks"],
            "confidence_assessment": narrative["confidence_assessment"],
        },
        # Verbatim from facts — never LLM-generated
        "probabilities": facts["ml"]["probabilities"].copy(),
        "prediction": facts["ml"]["prediction"].copy(),
        "signals": facts["ml"]["signals"].copy(),
        "risk_flags": list(facts["ml"]["risk_flags"]),
        "writer_metadata": {
            "model": model_used,
            "temperature": temperature,
            "prompt_version": prompt_version,
            "facts_hash": facts_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "generation_mode": generation_mode,
        },
    }


def _call_llm(
    facts: Dict[str, Any],
    model: str,
    temperature: float,
) -> Dict[str, str]:
    """Call the LLM to generate narrative sections."""
    from openai import OpenAI

    client = OpenAI()

    user_content = json.dumps(facts, indent=2, default=str)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=temperature,
        max_tokens=800,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        raw = "\n".join(lines)

    narrative = json.loads(raw)

    required = {"headline", "overview", "prediction_rationale", "key_factors", "risks", "confidence_assessment"}
    missing = required - set(narrative.keys())
    if missing:
        raise ValueError(f"LLM response missing fields: {missing}")

    if not isinstance(narrative["key_factors"], list):
        raise ValueError("key_factors must be a list")
    if not isinstance(narrative["risks"], list):
        raise ValueError("risks must be a list")

    return narrative


def _template_fallback(facts: Dict[str, Any]) -> Dict[str, str]:
    """Generate minimal narrative from facts without LLM."""
    fixture = facts["fixture"]
    ml = facts["ml"]
    probs = ml["probabilities"]
    pred = ml["prediction"]
    drivers = ml["drivers"]
    signals = ml["signals"]

    result_labels = {"H": "Home Win", "D": "Draw", "A": "Away Win"}
    predicted_label = result_labels[pred["predicted_result"]]

    driver_strs = []
    for d in drivers[:3]:
        driver_strs.append(f"{d['feature']} ({d['value']:+.1f})")

    headline = f"{fixture['home_team']} vs {fixture['away_team']}: {pred['confidence_label']} {predicted_label} lean"
    overview = (
        f"The model projects {predicted_label} with {probs['home_win']:.0%} / "
        f"{probs['draw']:.0%} / {probs['away_win']:.0%} (H/D/A). "
        f"Confidence: {pred['confidence_label']}."
    )
    rationale = f"Top drivers: {', '.join(driver_strs)}."
    key_factors = [f"{d['feature']}: {d['value']:+.1f} ({d['direction']})" for d in drivers[:3]]
    risks = [f"Entropy: {signals['entropy_norm']:.2f}"]
    if ml["risk_flags"]:
        risks.extend(ml["risk_flags"])
    confidence = f"{pred['confidence_label'].capitalize()} confidence (margin: {signals['margin_top2']:.3f})."

    return {
        "headline": headline,
        "overview": overview,
        "prediction_rationale": rationale,
        "key_factors": key_factors,
        "risks": risks,
        "confidence_assessment": confidence,
    }
