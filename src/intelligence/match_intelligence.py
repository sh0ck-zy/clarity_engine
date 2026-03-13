"""
Match Intelligence Engine — reads football matches like an analyst.

v1.5: Single LLM call that produces match_intelligence.json.
The ML anchor is probabilistic context, NOT the truth base.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from intelligence.game_reader_prompt import GAME_READER_SYSTEM_PROMPT, build_user_prompt


class MatchIntelligenceEngine:
    """
    v1.5 Match Intelligence Engine.

    Replaces GroundedNarrator for new-style output.
    Produces match_intelligence.json (game read) instead of
    narrative.json (driver explanations).
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 3000,
    ):
        import openai

        self.client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(
        self,
        match_pack: Dict[str, Any],
        ml_anchor: Dict[str, Any],
        match_signals: Dict[str, Any],
        cache_path: Optional[Path] = None,
        regenerate: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate match intelligence for a single match.

        Steps:
        1. Check cache
        2. Build prompt from match_pack + ml_anchor + match_signals
        3. Single LLM call to read the game
        4. Parse and validate output
        5. Return match_intelligence dict
        """
        # Check cache
        if cache_path and cache_path.exists() and not regenerate:
            try:
                cached = json.loads(cache_path.read_text())
                if cached.get("schema_version") == "1.5":
                    return cached
            except (json.JSONDecodeError, KeyError):
                pass

        # Build prompt
        user_prompt = build_user_prompt(match_pack, ml_anchor, match_signals)

        # LLM call
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": GAME_READER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        usage = response.usage

        # Parse LLM output
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = _fallback_parse(raw)

        # Assemble final output (lean schema — no metadata bloat)
        match_id = match_pack.get("fixture", {}).get("fixture_id", "")

        result = {
            "schema_version": "1.5",
            "match_id": match_id,
            "key_question": parsed.get("key_question", ""),
            "main_read": parsed.get("main_read", ""),
            "evidence_for": _clean_evidence(parsed.get("evidence_for", [])),
            "evidence_against": _clean_evidence(parsed.get("evidence_against", [])),
            "scenarios": _clean_scenarios(parsed.get("scenarios", [])),
            "risks": parsed.get("risks", []),
            "uncertainty": parsed.get("uncertainty", []),
            "lean": parsed.get("lean", ""),
            "confidence": parsed.get("confidence", "Medium"),
        }

        # Save to cache
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False)
            )

        # Print cost info
        tokens = usage.total_tokens if usage else 0
        cost = _estimate_cost(self.model, usage) if usage else 0.0
        print(f"    MI Engine: {tokens} tokens (${cost:.4f})")

        return result


def _clean_evidence(items: list) -> list:
    """Ensure evidence items have required fields."""
    clean = []
    for item in items:
        if isinstance(item, dict):
            clean.append({
                "claim": item.get("claim", ""),
                "data": item.get("data", ""),
                "strength": item.get("strength", "moderate"),
            })
        elif isinstance(item, str):
            clean.append({"claim": item, "data": "", "strength": "moderate"})
    return clean


def _clean_scenarios(items: list) -> list:
    """Ensure scenario items have required fields."""
    clean = []
    for item in items:
        if isinstance(item, dict):
            clean.append({
                "name": item.get("name", ""),
                "likelihood": item.get("likelihood", "possible"),
                "description": item.get("description", ""),
                "trigger": item.get("trigger", ""),
            })
    return clean


def _fallback_parse(raw: str) -> dict:
    """Try to extract JSON from a response that isn't pure JSON."""
    # Try to find JSON in the response
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass
    return {}


def _estimate_cost(model: str, usage) -> float:
    """Estimate cost based on model and token usage."""
    if not usage:
        return 0.0

    # Approximate pricing per 1M tokens (input/output)
    pricing = {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
    }
    input_rate, output_rate = pricing.get(model, (2.50, 10.00))

    input_cost = (usage.prompt_tokens / 1_000_000) * input_rate
    output_cost = (usage.completion_tokens / 1_000_000) * output_rate
    return input_cost + output_cost


def render_intelligence_text(intelligence: Dict[str, Any]) -> str:
    """Render match_intelligence.json as human-readable plaintext."""
    lines = []

    lines.append(f"KEY QUESTION: {intelligence.get('key_question', '?')}")
    lines.append("")
    lines.append(f"MAIN READ: {intelligence.get('main_read', '?')}")
    lines.append("")

    # Evidence
    ev_for = intelligence.get("evidence_for", [])
    if ev_for:
        lines.append("EVIDENCE FOR:")
        for e in ev_for:
            strength = f"[{e.get('strength', '?')}]"
            lines.append(f"  + {e.get('claim', '')} — {e.get('data', '')} {strength}")
        lines.append("")

    ev_against = intelligence.get("evidence_against", [])
    if ev_against:
        lines.append("EVIDENCE AGAINST:")
        for e in ev_against:
            strength = f"[{e.get('strength', '?')}]"
            lines.append(f"  - {e.get('claim', '')} — {e.get('data', '')} {strength}")
        lines.append("")

    # Scenarios
    scenarios = intelligence.get("scenarios", [])
    if scenarios:
        lines.append("SCENARIOS:")
        for s in scenarios:
            lines.append(
                f"  [{s.get('likelihood', '?')}] {s.get('name', '?')}: "
                f"{s.get('description', '')}"
            )
            if s.get("trigger"):
                lines.append(f"    Trigger: {s['trigger']}")
        lines.append("")

    # Risks
    risks = intelligence.get("risks", [])
    if risks:
        lines.append("RISKS:")
        for r in risks:
            lines.append(f"  ! {r}")
        lines.append("")

    # Uncertainty
    uncertainty = intelligence.get("uncertainty", [])
    if uncertainty:
        lines.append("UNCERTAINTY:")
        for u in uncertainty:
            lines.append(f"  ? {u}")
        lines.append("")

    # Lean
    lines.append(f"LEAN: {intelligence.get('lean', '?')}")
    lines.append(f"CONFIDENCE: {intelligence.get('confidence', '?')}")

    return "\n".join(lines)
