"""
Match report renderer: transforms probabilistic motor JSON into text for Telegram/X.

The LLM is a WRITER, not a predictor. Every number in the output comes directly
from the report JSON. The renderer may not alter probabilities, invent drivers,
or add analytical claims not supported by the data.

Guardrails:
    - All probabilities come verbatim from report["probabilities"]
    - Drivers come verbatim from report["drivers"]
    - Confidence label comes from report["prediction"]["confidence"]
    - Risk flags modulate language tone (hedging, caveats)
    - No scoreline predictions (optional illustrative only)
"""

from __future__ import annotations

from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = {
    "schema_version",
    "model_version",
    "fixture",
    "probabilities",
    "prediction",
    "drivers",
    "risk_flags",
    "metadata",
}

_REQUIRED_FIXTURE = {"fixture_id", "round_number", "match_date", "home_team", "away_team"}
_REQUIRED_PROBS = {"home_win", "draw", "away_win"}
_REQUIRED_PRED = {"predicted_result", "confidence", "p_max", "margin_top2", "entropy_norm"}


class ReportValidationError(ValueError):
    """Raised when a match report fails validation."""
    pass


def validate_report(report: Dict) -> None:
    """
    Validate a match report before rendering.

    Checks:
        - All required fields present
        - Probabilities sum to ~1.0
        - argmax matches predicted_result
        - Confidence is a valid label
        - Drivers have required structure
    """
    # Top-level fields
    missing = _REQUIRED_FIELDS - set(report.keys())
    if missing:
        raise ReportValidationError(f"Missing top-level fields: {missing}")

    # Fixture
    missing_f = _REQUIRED_FIXTURE - set(report["fixture"].keys())
    if missing_f:
        raise ReportValidationError(f"Missing fixture fields: {missing_f}")

    # Probabilities
    probs = report["probabilities"]
    missing_p = _REQUIRED_PROBS - set(probs.keys())
    if missing_p:
        raise ReportValidationError(f"Missing probability fields: {missing_p}")

    total = probs["home_win"] + probs["draw"] + probs["away_win"]
    if abs(total - 1.0) > 0.02:
        raise ReportValidationError(f"Probabilities sum to {total:.4f}, expected ~1.0")

    # argmax consistency
    pred = report["prediction"]
    missing_pr = _REQUIRED_PRED - set(pred.keys())
    if missing_pr:
        raise ReportValidationError(f"Missing prediction fields: {missing_pr}")

    prob_map = {"H": probs["home_win"], "D": probs["draw"], "A": probs["away_win"]}
    argmax = max(prob_map, key=prob_map.get)
    if pred["predicted_result"] != argmax:
        raise ReportValidationError(
            f"predicted_result={pred['predicted_result']} but argmax={argmax} "
            f"(H={probs['home_win']:.4f} D={probs['draw']:.4f} A={probs['away_win']:.4f})"
        )

    # Confidence label
    if pred["confidence"] not in ("high", "medium", "low"):
        raise ReportValidationError(f"Invalid confidence: {pred['confidence']}")

    # Drivers structure
    for d in report.get("drivers", []):
        if not all(k in d for k in ("feature", "value", "contribution", "direction")):
            raise ReportValidationError(f"Malformed driver: {d}")
        if d["direction"] not in ("for", "against"):
            raise ReportValidationError(f"Invalid driver direction: {d['direction']}")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_RESULT_LABELS = {"H": "Home Win", "D": "Draw", "A": "Away Win"}

_FEATURE_DISPLAY = {
    "xg_diff_last5_delta": "xG advantage (last 5)",
    "form_points_delta": "Form gap",
    "goal_diff_season_delta": "Goal diff gap",
    "position_delta": "Table position gap",
    "elo_delta": "ELO rating gap",
    "home_venue_points": "Home ground strength",
    "away_venue_points": "Away record",
    "home_strength_delta": "Venue strength gap",
    "league_rest_days_delta": "Rest days gap",
    "xg_for_last5_delta": "xG attack gap (last 5)",
    "xg_against_last5_delta": "xG defence gap (last 5)",
}

_CONFIDENCE_TONE = {
    "high": "Strong lean",
    "medium": "Moderate lean",
    "low": "Tight call",
}

_FLAG_CAVEATS = {
    "elo_missing": "ELO data incomplete for this fixture",
    "near_uniform": "Model sees this as a coin flip",
    "tight_margin": "Very slim margin between outcomes",
    "small_training_set": "Limited training data available",
}


def _fmt_pct(p: float) -> str:
    """Format probability as percentage without decimal if round."""
    pct = p * 100
    if abs(pct - round(pct)) < 0.05:
        return f"{pct:.0f}%"
    return f"{pct:.1f}%"


def _driver_text(driver: Dict) -> str:
    """Format a single driver as readable text."""
    name = _FEATURE_DISPLAY.get(driver["feature"], driver["feature"])
    direction = driver["direction"]
    value = driver["value"]

    if direction == "for":
        return f"{name} ({value:+.1f})"
    else:
        return f"{name} ({value:+.1f}, working against)"


def _build_caveat(flags: List[str]) -> Optional[str]:
    """Build caveat text from risk flags."""
    if not flags:
        return None
    parts = [_FLAG_CAVEATS.get(f, f) for f in flags]
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Telegram renderer
# ---------------------------------------------------------------------------

def render_telegram_post(report: Dict) -> str:
    """
    Render a match report as a Telegram message.

    Format: ~300-500 chars, structured, all data from report JSON.
    """
    validate_report(report)

    f = report["fixture"]
    p = report["probabilities"]
    pred = report["prediction"]
    drivers = report["drivers"]
    flags = report["risk_flags"]

    home = f["home_team"]
    away = f["away_team"]
    round_num = f["round_number"]

    # Header
    lines = [f"R{round_num} | {home} vs {away}"]

    # Probabilities bar
    lines.append(
        f"H {_fmt_pct(p['home_win'])}  D {_fmt_pct(p['draw'])}  A {_fmt_pct(p['away_win'])}"
    )

    # Prediction line
    result_label = _RESULT_LABELS[pred["predicted_result"]]
    tone = _CONFIDENCE_TONE[pred["confidence"]]
    lines.append(f"{tone}: {result_label}")

    # Drivers (top 3)
    if drivers:
        top = drivers[:3]
        driver_parts = [_driver_text(d) for d in top]
        lines.append(f"Key factors: {', '.join(driver_parts)}")

    # Caveat from risk flags
    caveat = _build_caveat(flags)
    if caveat:
        lines.append(f"Note: {caveat}")

    # Footer
    lines.append(f"[{report['model_version']}]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# X (Twitter) renderer
# ---------------------------------------------------------------------------

def render_x_post(report: Dict) -> str:
    """
    Render a match report as an X/Twitter post.

    Format: under 280 chars, dense, all data from report JSON.
    """
    validate_report(report)

    f = report["fixture"]
    p = report["probabilities"]
    pred = report["prediction"]
    drivers = report["drivers"]
    flags = report["risk_flags"]

    home = f["home_team"]
    away = f["away_team"]

    # Shorten team names for X
    home_short = _shorten_team(home)
    away_short = _shorten_team(away)

    result_label = _RESULT_LABELS[pred["predicted_result"]]
    tone = _CONFIDENCE_TONE[pred["confidence"]]

    # Core line
    parts = [
        f"R{f['round_number']} {home_short} vs {away_short}",
        f"H {_fmt_pct(p['home_win'])} D {_fmt_pct(p['draw'])} A {_fmt_pct(p['away_win'])}",
        f"{tone}: {result_label}",
    ]

    # Top driver (just one for brevity)
    if drivers:
        top = drivers[0]
        name = _FEATURE_DISPLAY.get(top["feature"], top["feature"])
        parts.append(f"Driver: {name}")

    # Flag caveat (short)
    if "near_uniform" in flags or "tight_margin" in flags:
        parts.append("Coin flip territory")

    parts.append(f"[{report['model_version']}]")

    text = "\n".join(parts)

    # Truncation guard
    if len(text) > 280:
        # Drop driver line and try again
        parts = [p for p in parts if not p.startswith("Driver:")]
        text = "\n".join(parts)

    return text[:280]


# ---------------------------------------------------------------------------
# Team name shortening for X
# ---------------------------------------------------------------------------

_SHORT_NAMES = {
    "AFC Bournemouth": "Bournemouth",
    "Brighton & Hove Albion": "Brighton",
    "Crystal Palace": "C. Palace",
    "Leicester City": "Leicester",
    "Manchester City": "Man City",
    "Manchester United": "Man Utd",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Tottenham Hotspur": "Spurs",
    "West Ham United": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
    "Ipswich Town": "Ipswich",
    "Leeds United": "Leeds",
    "Luton Town": "Luton",
}


def _shorten_team(name: str) -> str:
    return _SHORT_NAMES.get(name, name)


# ---------------------------------------------------------------------------
# Batch rendering
# ---------------------------------------------------------------------------

def render_round_telegram(reports: List[Dict]) -> str:
    """Render all match reports for a round as a single Telegram message."""
    if not reports:
        return ""

    round_num = reports[0]["fixture"]["round_number"]
    header = f"Premier League Round {round_num} Predictions\n{'='*35}\n"

    posts = []
    for report in reports:
        posts.append(render_telegram_post(report))

    return header + "\n\n".join(posts)
