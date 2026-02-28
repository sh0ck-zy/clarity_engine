"""
LLM Narrator — generates expert match analysis in 4 pillar sections.

Sections:
  📝 a_historia     (journalist)  — narrative arc, stakes, emotion
  ⚽ onde_se_decide (pundit)      — tactical matchup, key battles
  🔬 o_que_pode_correr_mal (analyst) — risks, contrarian data
  💡 bottom_line    (synthesis)   — one-sentence read

Usage:
    narrator = Narrator(model="gpt-4o-mini")
    result = narrator.generate(context_dict)
    # result = {"sections": {...}, "model": ..., "tokens_used": ..., ...}
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import openai


# ──────────────────────────────────────────────────────────────
# System prompt — defines the 4 pillars and writing style
# ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Premier League match intelligence analyst writing for Clarity Engine, an elite football intelligence service.

You produce 4 analysis sections for each match. Each section has a specific voice and purpose:

## 1. A HISTÓRIA (📝 Journalist)
Write the narrative arc of this fixture. What's at stake for each team? Where are they in their season story? Reference recent results by opponent name and score. Mention manager context if relevant (new manager, poor run, etc). Use form strings. Make the reader FEEL what this match means.

## 2. ONDE SE DECIDE (⚽ Pundit)
Tactical analysis. Compare formations, possession styles, attacking/defensive numbers. Identify the key battle that will decide the match. Name specific players and their contributions. Where will the game be won or lost?

## 3. O QUE PODE CORRER MAL (🔬 Analyst)
Contrarian view. What data contradicts the obvious narrative? List at least 3 specific risks with supporting numbers. Include the model's probability assessment and explain what the drivers mean. Challenge assumptions.

## 4. BOTTOM LINE (💡 Synthesis)
One or two sentences maximum. The definitive read on this match. Be direct, not wishy-washy. No fence-sitting.

## Rules:
- Every claim MUST be backed by data from the context provided
- Use exact numbers: "2.8 big chances/game" not "lots of chances"
- Name players: "Enzo Fernández (8G, 2A)" not "their midfielder"
- Reference formations: "4-3-3 vs 4-2-3-1"
- Reference form strings: "LWWDW"
- Include model probabilities naturally
- Never use: guaranteed, certain, definitely, will win, will lose
- Never predict exact scorelines
- Write in English
- Be authoritative but honest about uncertainty

## Output Format:
Return ONLY a JSON object with this exact structure:
{
  "a_historia": "...",
  "onde_se_decide": "...",
  "o_que_pode_correr_mal": "...",
  "bottom_line": "..."
}

Each section should be 2-4 sentences (except bottom_line which is 1-2 sentences).
Total output: approximately 250-400 words across all 4 sections."""


USER_PROMPT_TEMPLATE = """Write match intelligence for **{home}** vs **{away}** (Round {round}).

MATCH CONTEXT:
{context_json}

Generate the 4 sections now. Use specific data from the context above."""


class Narrator:
    """LLM-based narrative generator with caching."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 1200,
    ):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY not set. Export it or add to .env"
            )
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def generate(
        self,
        context: Dict,
        cache_path: Optional[Path] = None,
        regenerate: bool = False,
    ) -> Dict:
        """
        Generate narrative from context.

        Args:
            context: Full match context dict (from MatchContextBuilder)
            cache_path: Path to narrative.json for caching
            regenerate: If True, skip cache and regenerate

        Returns:
            Dict with sections + metadata
        """
        # Check cache
        if cache_path and cache_path.exists() and not regenerate:
            try:
                cached = json.loads(cache_path.read_text())
                if cached.get("context_version") == context.get("context_version"):
                    return cached
            except (json.JSONDecodeError, KeyError):
                pass  # stale cache, regenerate

        # Build prompt
        home = context.get("factual", {}).get("home", {})
        away = context.get("factual", {}).get("away", {})

        # Find team names from match or from context
        match_info = context.get("match", {})
        fixture = context.get("ml_inference", {})

        # Get names from recent results or match info
        home_name = match_info.get("home_team", "Home")
        away_name = match_info.get("away_team", "Away")

        # If names not in match, try to extract from context
        if home_name == "Home":
            # Try to get from key_players team
            home_name = "Home Team"
        if away_name == "Away":
            away_name = "Away Team"

        # Prepare a clean context for the LLM (remove unnecessary fields)
        clean_context = {
            "match": context.get("match", {}),
            "factual": context.get("factual", {}),
            "ml_inference": context.get("ml_inference", {}),
            "narrative_angles": context.get("narrative_angles", {}),
        }

        user_prompt = USER_PROMPT_TEMPLATE.format(
            home=home_name,
            away=away_name,
            round=match_info.get("round_number", "?"),
            context_json=json.dumps(clean_context, indent=2, default=str),
        )

        # Call LLM
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        usage = response.usage

        # Parse sections
        try:
            sections_raw = json.loads(raw)
        except json.JSONDecodeError:
            sections_raw = {
                "a_historia": raw,
                "onde_se_decide": "",
                "o_que_pode_correr_mal": "",
                "bottom_line": "",
            }

        # Build result
        sections = {}
        pillar_map = {
            "a_historia": "journalist",
            "onde_se_decide": "pundit",
            "o_que_pode_correr_mal": "analyst",
            "bottom_line": "synthesis",
        }
        for key, pillar in pillar_map.items():
            sections[key] = {
                "pillar": pillar,
                "content": sections_raw.get(key, ""),
            }

        # Cost estimate (gpt-4o-mini pricing as of 2026)
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = (input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000

        result = {
            "sections": sections,
            "model": self.model,
            "tokens_used": usage.total_tokens if usage else 0,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_estimate": round(cost, 6),
            "context_version": context.get("context_version", "1.0"),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

        # Write cache
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

        return result
