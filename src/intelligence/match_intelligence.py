"""
Match Intelligence Engine — reads football matches like an analyst.

v1.6: Thinking model support + tactical rubric + structured reasoning.
The ML anchor is probabilistic context, NOT the truth base.

Supports multiple LLM providers:
- OpenAI: gpt-4o, gpt-4.1, o3, gpt-5.4
- Anthropic: claude-opus-4-6, claude-sonnet-4-6
- HuggingFace: any model via HF router (e.g. hf:zai-org/GLM-5:fastest)
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


# Provider detection
ANTHROPIC_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"}


def _is_anthropic(model: str) -> bool:
    return model in ANTHROPIC_MODELS or model.startswith("claude-")


def _is_huggingface(model: str) -> bool:
    return model.startswith("hf:")


def _is_gemini(model: str) -> bool:
    return model.startswith("gemini:")


def _needs_max_completion_tokens(model: str) -> bool:
    """gpt-5.*, o3*, o4* use max_completion_tokens instead of max_tokens."""
    if "/" in model or model.startswith("gemini"):  # HF, Gemini or other third-party models
        return False
    m = model.lower()
    return m.startswith("gpt-5") or m.startswith("o3") or m.startswith("o4")


def _supports_temperature(model: str) -> bool:
    """Only classic chat models support temperature. Reasoning/gpt-5 do not."""
    m = model.lower()
    if m.startswith("o3") or m.startswith("o4"):
        return False
    if m.startswith("gpt-5"):
        return False
    return True


def _supports_json_mode(model: str) -> bool:
    """Reasoning and gpt-5 models don't support response_format json_object."""
    return _supports_temperature(model)


class MatchIntelligenceEngine:
    """
    v1.6 Match Intelligence Engine.

    Supports OpenAI and Anthropic models including thinking models.
    Produces match_intelligence.json (game read).
    """

    def __init__(
        self,
        model: str = "claude-opus-4-6",
        temperature: float = 0.7,
        max_tokens: int = 16000,
    ):
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None

        if _is_huggingface(model):
            self._provider = "huggingface"
            self.model = model[3:]  # strip "hf:" prefix
        elif _is_gemini(model):
            self._provider = "gemini"
            self.model = model[7:]  # strip "gemini:" prefix
        elif _is_anthropic(model):
            self._provider = "anthropic"
            self.model = model
        else:
            self._provider = "openai"
            self.model = model

    @property
    def client(self):
        """Lazy-init the appropriate client."""
        if self._client is None:
            if self._provider == "anthropic":
                import anthropic
                self._client = anthropic.Anthropic(
                    api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
                    timeout=120.0,
                )
            elif self._provider == "huggingface":
                import openai
                self._client = openai.OpenAI(
                    base_url="https://router.huggingface.co/v1",
                    api_key=os.environ.get("HF_TOKEN", ""),
                    timeout=120.0,
                )
            elif self._provider == "gemini":
                import openai
                self._client = openai.OpenAI(
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    api_key=os.environ.get("GEMINI_API_KEY", ""),
                    timeout=120.0,
                )
            else:
                import openai
                self._client = openai.OpenAI(
                    api_key=os.environ.get("OPENAI_API_KEY", ""),
                    timeout=120.0,
                )
        return self._client

    def generate(
        self,
        match_pack: Dict[str, Any],
        ml_anchor: Dict[str, Any],
        match_signals: Dict[str, Any],
        tactical_rubric: Optional[Dict[str, Any]] = None,
        cache_path: Optional[Path] = None,
        regenerate: bool = False,
        confidence_level: str = "",
        data_warnings: list = None,
    ) -> Dict[str, Any]:
        """
        Generate match intelligence for a single match.

        v1.6: Now accepts tactical_rubric for structured game context.
        Supports OpenAI and Anthropic providers including thinking models.
        """
        # Check cache (skip stale degraded/skipped records from prior runs)
        if cache_path and cache_path.exists() and not regenerate:
            try:
                cached = json.loads(cache_path.read_text())
                if (cached.get("schema_version") in ("1.5", "1.6", "1.7", "1.8")
                        and cached.get("mi_status") not in ("degraded", "skipped", "skip")):
                    return cached
            except (json.JSONDecodeError, KeyError):
                pass

        # Build prompt (with confidence level, data warnings, and tactical rubric)
        user_prompt = build_user_prompt(
            match_pack, ml_anchor, match_signals,
            tactical_rubric=tactical_rubric,
            confidence_level=confidence_level,
            data_warnings=data_warnings,
        )

        # LLM call — route to appropriate provider
        if self._provider == "anthropic":
            raw, usage_info = self._call_anthropic(user_prompt)
        else:
            # Both "openai" and "huggingface" use the OpenAI-compatible client
            raw, usage_info = self._call_openai(user_prompt)

        # Parse LLM output
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = _fallback_parse(raw)

        # Assemble final output
        match_id = match_pack.get("fixture", {}).get("fixture_id", "")
        final_confidence = confidence_level if confidence_level else parsed.get("confidence", "Medium")

        result = {
            "schema_version": "1.8",
            "match_id": match_id,
            # v1.8 fields (7-field format)
            "verdict": parsed.get("verdict", ""),
            "core_read": parsed.get("core_read", parsed.get("main_read", "")),
            "main_mechanism": parsed.get("main_mechanism", ""),
            "main_risk": parsed.get("main_risk", ""),
            "kill_switch": parsed.get("kill_switch", parsed.get("invalidation_condition", "")),
            "best_score_range": parsed.get("best_score_range", ""),
            "lean": parsed.get("lean", ""),
            "confidence": final_confidence,
            # Legacy compat (kept for backward-compatible renderers)
            "key_question": parsed.get("verdict", parsed.get("key_question", "")),
            "main_read": parsed.get("core_read", parsed.get("main_read", "")),
            "scenarios": _clean_scenarios(parsed.get("scenarios", [])),
            "risks": [parsed.get("main_risk", "")] if parsed.get("main_risk") else parsed.get("risks", []),
        }

        _validate_schema(result)

        # Build LLM trace metadata
        llm_trace = {
            "model": self.model,
            "provider": self._provider,
            "temperature": self.temperature,
            "prompt_tokens": usage_info.get("prompt_tokens", 0),
            "completion_tokens": usage_info.get("completion_tokens", 0),
            "cost_usd": round(usage_info.get("cost_usd", 0.0), 6),
        }
        result["_llm_trace"] = llm_trace
        result["llm_trace"] = llm_trace  # persisted to disk for provenance

        # Save to cache
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            save_result = {k: v for k, v in result.items() if not k.startswith("_")}
            cache_path.write_text(
                json.dumps(save_result, indent=2, ensure_ascii=False)
            )

        total_tokens = usage_info.get("prompt_tokens", 0) + usage_info.get("completion_tokens", 0)
        cost = usage_info.get("cost_usd", 0.0)
        print(f"    MI Engine [{self.model}]: {total_tokens} tokens (${cost:.4f})")

        return result

    def _call_anthropic(self, user_prompt: str) -> tuple:
        """Call Anthropic API (Claude models). Returns (raw_text, usage_info)."""
        # Claude uses extended thinking for deep reasoning
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
            "system": GAME_READER_SYSTEM_PROMPT,
        }

        # Enable extended thinking for opus/sonnet
        if "opus" in self.model or "sonnet" in self.model:
            kwargs["temperature"] = 1  # required for extended thinking
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": 10000,
            }
        else:
            kwargs["temperature"] = self.temperature

        response = self.client.messages.create(**kwargs)

        # Extract text from response (may have thinking blocks)
        raw = ""
        for block in response.content:
            if block.type == "text":
                raw = block.text
                break

        usage = response.usage
        prompt_tokens = usage.input_tokens if usage else 0
        completion_tokens = usage.output_tokens if usage else 0
        cost = _estimate_cost(self.model, prompt_tokens, completion_tokens)

        return raw, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
        }

    def _call_openai(self, user_prompt: str) -> tuple:
        """Call OpenAI API. Returns (raw_text, usage_info).

        Handles three model families:
        - Classic (gpt-4o, gpt-4.1): max_tokens, temperature, json_object
        - Reasoning (o3, o4-mini): max_completion_tokens, reasoning.effort, no temp/json
        - GPT-5 (gpt-5.4): max_completion_tokens, reasoning.effort, no temp/json
        """
        messages = [
            {"role": "system", "content": GAME_READER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        kwargs = {
            "model": self.model,
            "messages": messages,
        }

        # Token limit parameter
        if _needs_max_completion_tokens(self.model):
            kwargs["max_completion_tokens"] = self.max_tokens
            # Reasoning effort — SDK uses reasoning_effort (str), not reasoning (dict)
            kwargs["reasoning_effort"] = "high"
        else:
            kwargs["max_tokens"] = self.max_tokens

        # Temperature (only classic models)
        if _supports_temperature(self.model):
            kwargs["temperature"] = self.temperature

        # JSON mode (only classic models)
        if _supports_json_mode(self.model):
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)

        raw = response.choices[0].message.content
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        cost = _estimate_cost(self.model, prompt_tokens, completion_tokens)

        return raw, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
        }


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


REQUIRED_FIELDS = [
    "verdict", "core_read", "main_mechanism", "main_risk",
    "kill_switch", "best_score_range", "lean", "confidence",
]
ALLOWED_CONFIDENCE = ["High", "Medium-High", "Medium", "Medium-Low", "Low"]


def _validate_schema(result: Dict[str, Any]) -> None:
    """Validate the output schema. Logs warnings but does not block."""
    for field in REQUIRED_FIELDS:
        if field not in result or not result[field]:
            print(f"    Schema warning: missing or empty '{field}'")

    conf = result.get("confidence", "")
    if conf not in ALLOWED_CONFIDENCE:
        print(f"    Schema warning: confidence '{conf}' not in allowed values, defaulting to Medium")
        result["confidence"] = "Medium"


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost based on model and token counts."""
    # Approximate pricing per 1M tokens (input/output)
    pricing = {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-5.4": (2.00, 8.00),
        "o3": (2.00, 8.00),
        "o3-mini": (1.10, 4.40),
        "o4-mini": (1.10, 4.40),
        "claude-opus-4-6": (15.00, 75.00),
        "claude-sonnet-4-6": (3.00, 15.00),
        "claude-haiku-4-5-20251001": (0.80, 4.00),
    }
    input_rate, output_rate = pricing.get(model, (5.00, 15.00))

    input_cost = (prompt_tokens / 1_000_000) * input_rate
    output_cost = (completion_tokens / 1_000_000) * output_rate
    return input_cost + output_cost


def render_intelligence_text(intelligence: Dict[str, Any]) -> str:
    """Render match_intelligence.json as human-readable plaintext (v1.8 format)."""
    lines = []

    # v1.8 primary fields
    verdict = intelligence.get("verdict", intelligence.get("key_question", "?"))
    core_read = intelligence.get("core_read", intelligence.get("main_read", "?"))
    main_mechanism = intelligence.get("main_mechanism", "")
    main_risk = intelligence.get("main_risk", "")
    kill_switch = intelligence.get("kill_switch", intelligence.get("invalidation_condition", ""))
    best_score_range = intelligence.get("best_score_range", "")

    lines.append(f"VERDICT: {verdict}")
    lines.append("")
    lines.append(f"CORE READ: {core_read}")
    lines.append("")

    if main_mechanism:
        lines.append(f"MECHANISM: {main_mechanism}")
        lines.append("")

    if main_risk:
        lines.append(f"RISK: {main_risk}")
        lines.append("")

    if kill_switch:
        lines.append(f"KILL SWITCH: {kill_switch}")
        lines.append("")

    if best_score_range:
        lines.append(f"SCORE RANGE: {best_score_range}")
        lines.append("")

    # Lean + Confidence
    lines.append(f"LEAN: {intelligence.get('lean', '?')}")
    lines.append(f"CONFIDENCE: {intelligence.get('confidence', '?')}")

    # Decision (if present)
    decision = intelligence.get("decision", {})
    if decision:
        action = decision.get("action", "")
        direction = decision.get("direction", "")
        edge = decision.get("edge_vs_market")
        lines.append("")
        dec_line = f"DECISION: {action}"
        if direction:
            dec_line += f" {direction}"
        if edge is not None:
            dec_line += f" (edge: {edge:+.4f})"
        lines.append(dec_line)

    # Direction trace
    directions = intelligence.get("directions", decision.get("directions", {}))
    if directions:
        ml = directions.get("ml_anchor", "")
        tac = directions.get("tactical_read", "")
        final = directions.get("final_decision", "")
        override = directions.get("override_reason", "")
        lines.append(f"DIRECTIONS: ML={ml} Tactical={tac} Final={final}")
        if override:
            lines.append(f"  Override: {override}")

    return "\n".join(lines)
