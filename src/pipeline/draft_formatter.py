"""
Draft formatter: generates channel-specific text drafts from report + facts.

Each draft is an LLM adaptation of the report for a specific channel.
If guardrails fail, falls back to the deterministic template renderer.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from pipeline.guardrails import validate_draft

DRAFT_PROMPT_VERSION_TELEGRAM = "draft_telegram_v1"
DRAFT_PROMPT_VERSION_X = "draft_x_v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.3

_TELEGRAM_SYSTEM_PROMPT = """\
You are a football analyst writing a Telegram channel post.
Given a match analysis report and supporting facts, write an engaging post (~400-500 chars).

RULES:
- Use ONLY data from the report and facts. Do not invent stats, players, or claims.
- Include the probabilities (H/D/A percentages), predicted result, and confidence.
- Mention 2-3 key drivers in natural language.
- Use hedged language proportional to confidence (high → "strong lean", medium → "moderate lean", low → "tight call").
- NEVER use: guaranteed, certain, definitely, will win, will lose, must win.
- End with the report_id in brackets: [{report_id}]
- Be conversational but data-grounded.
- Output ONLY the post text, no JSON or markdown.
"""

_X_SYSTEM_PROMPT = """\
You are a football analyst writing a tweet.
Given a match analysis report and supporting facts, write a tweet (max 270 chars to leave room for the footer).

RULES:
- Use ONLY data from the report and facts. Do not invent anything.
- Include probabilities and predicted result.
- Use hedged language. NEVER: guaranteed, certain, definitely, will win.
- Be concise, punchy, data-driven.
- Output ONLY the tweet text, no JSON or markdown. Do NOT include the report_id — it will be appended automatically.
"""


def format_draft(
    report: Dict[str, Any],
    facts: Dict[str, Any],
    channel: str,
    run_id: str,
) -> Tuple[str, Dict[str, Any]]:
    """
    Generate a draft text and metadata for a channel.

    Args:
        report: report.json dict.
        facts: facts.json dict.
        channel: "telegram" or "x".
        run_id: Pipeline run ID.

    Returns:
        (text, meta_dict) where meta conforms to draft_meta.schema.json.
    """
    report_id = report["report_id"]
    prompt_version = DRAFT_PROMPT_VERSION_TELEGRAM if channel == "telegram" else DRAFT_PROMPT_VERSION_X

    # Try LLM
    try:
        text = _call_llm_draft(report, facts, channel)
        violations = validate_draft(text, facts, report)
        if violations:
            print(f"  Draft {channel} guardrail violations: {violations}. Falling back.")
            text = _template_fallback(report, facts, channel)
            source = "template_fallback"
            model_used = None
            prompt_used = None
        else:
            source = "llm"
            model_used = DEFAULT_MODEL
            prompt_used = prompt_version
    except Exception as e:
        print(f"  Draft {channel} LLM failed: {e}. Using template fallback.")
        text = _template_fallback(report, facts, channel)
        violations = []
        source = "template_fallback"
        model_used = None
        prompt_used = None

    meta = {
        "schema_version": "1.0",
        "channel": channel,
        "source": source,
        "violations": violations if source == "template_fallback" and violations else [],
        "report_id": report_id,
        "run_id": run_id,
        "char_count": len(text),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": model_used,
        "prompt_version": prompt_used,
    }

    return text, meta


def _call_llm_draft(
    report: Dict[str, Any],
    facts: Dict[str, Any],
    channel: str,
) -> str:
    """Call LLM to generate a draft."""
    from openai import OpenAI

    client = OpenAI()
    system = _TELEGRAM_SYSTEM_PROMPT if channel == "telegram" else _X_SYSTEM_PROMPT
    system = system.replace("{report_id}", report["report_id"])

    user_content = (
        f"REPORT:\n{json.dumps(report, indent=2, default=str)}\n\n"
        f"KEY FACTS:\n"
        f"Probabilities: H={facts['ml']['probabilities']['home_win']:.0%} "
        f"D={facts['ml']['probabilities']['draw']:.0%} "
        f"A={facts['ml']['probabilities']['away_win']:.0%}\n"
        f"Prediction: {facts['ml']['prediction']['predicted_result']} "
        f"({facts['ml']['prediction']['confidence_label']})\n"
        f"Drivers: {json.dumps(facts['ml']['drivers'][:3], default=str)}\n"
        f"Risk flags: {facts['ml']['risk_flags']}"
    )

    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=DEFAULT_TEMPERATURE,
        max_tokens=400 if channel == "telegram" else 200,
    )

    text = response.choices[0].message.content.strip()

    # For X: append audit footer and enforce char limit
    if channel == "x":
        footer = f"\n[{report['report_id']}]"
        if len(text) + len(footer) > 280:
            text = text[:280 - len(footer)]
        text += footer
    else:
        # For telegram: ensure report_id is in the text
        if report["report_id"] not in text:
            text += f"\n[{report['report_id']}]"

    return text


def _template_fallback(
    report: Dict[str, Any],
    facts: Dict[str, Any],
    channel: str,
) -> str:
    """Fall back to deterministic renderer from match_renderer.py."""
    from renderers.match_renderer import render_telegram_post, render_x_post, classify_editorial

    # Convert facts-based report back to the legacy match report format
    legacy_report = _to_legacy_report(report, facts)
    editorial = classify_editorial(legacy_report)

    if channel == "telegram":
        return render_telegram_post(legacy_report, editorial=editorial)
    else:
        return render_x_post(legacy_report, editorial=editorial)


def _to_legacy_report(report: Dict[str, Any], facts: Dict[str, Any]) -> Dict[str, Any]:
    """Convert new report/facts format to legacy match_renderer format."""
    return {
        "report_id": report["report_id"],
        "schema_version": "1.0",
        "model_version": facts["ml"]["model"]["version"],
        "fixture": {
            "fixture_id": report["fixture"]["fixture_id"],
            "round_number": report["fixture"]["round_number"],
            "match_date": report["fixture"]["match_date"],
            "home_team": report["fixture"]["home_team"],
            "away_team": report["fixture"]["away_team"],
        },
        "probabilities": report["probabilities"],
        "prediction": {
            "predicted_result": report["prediction"]["predicted_result"],
            "confidence": report["prediction"]["confidence_label"],
            "p_max": report["signals"]["p_max"],
            "margin_top2": report["signals"]["margin_top2"],
            "entropy_norm": report["signals"]["entropy_norm"],
        },
        "drivers": [
            {
                "feature": d["feature"],
                "value": d["value"],
                "contribution": d["contribution"],
                "direction": "for" if d["direction"] in ("home", "away") else "against",
            }
            for d in facts["ml"]["drivers"]
        ],
        "risk_flags": report["risk_flags"],
        "metadata": {
            "train_size": facts["ml"]["training_context"]["train_size"],
            "train_rounds": facts["ml"]["training_context"]["train_rounds"],
            "feature_subset": facts["ml"]["model"]["feature_subset"],
            "C": facts["ml"]["model"]["C"],
        },
    }
