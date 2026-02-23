"""
Snapshot tests for match renderer.

Ensures renderer output doesn't change unexpectedly. If you intentionally
change the renderer, update golden snapshots with:
    python tests/test_renderer.py --update
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from renderers.match_renderer import (
    ReportValidationError,
    classify_editorial,
    render_telegram_post,
    render_x_post,
    validate_report,
    validate_rendered_text,
)

GOLDEN_PATH = PROJECT_ROOT / "tests" / "golden" / "renderer_snapshots.json"


# ---------------------------------------------------------------------------
# Test fixtures (minimal valid reports)
# ---------------------------------------------------------------------------

_HIGH_CONF = {
    "report_id": "test_high_1",
    "schema_version": "1.0",
    "model_version": "v1.1",
    "fixture": {
        "fixture_id": "4813400",
        "round_number": 11,
        "match_date": "2025-11-16",
        "home_team": "Chelsea",
        "away_team": "Wolverhampton Wanderers",
    },
    "probabilities": {"home_win": 0.645, "draw": 0.198, "away_win": 0.158},
    "prediction": {
        "predicted_result": "H",
        "confidence": "high",
        "p_max": 0.645,
        "margin_top2": 0.447,
        "entropy_norm": 0.806,
    },
    "drivers": [
        {"feature": "goal_diff_season_delta", "value": 22.0, "contribution": 0.18, "direction": "for"},
        {"feature": "elo_delta", "value": 215.9, "contribution": 0.15, "direction": "for"},
        {"feature": "home_venue_points", "value": 7.0, "contribution": 0.09, "direction": "for"},
    ],
    "risk_flags": [],
    "metadata": {"train_size": 90, "train_rounds": [2, 3, 4, 5, 6, 7, 8, 9, 10], "feature_subset": [], "C": 0.01},
}

_MEDIUM_CONF = {
    "report_id": "test_med_1",
    "schema_version": "1.0",
    "model_version": "v1.1",
    "fixture": {
        "fixture_id": "4813300",
        "round_number": 8,
        "match_date": "2025-10-19",
        "home_team": "Crystal Palace",
        "away_team": "AFC Bournemouth",
    },
    "probabilities": {"home_win": 0.517, "draw": 0.246, "away_win": 0.237},
    "prediction": {
        "predicted_result": "H",
        "confidence": "medium",
        "p_max": 0.517,
        "margin_top2": 0.271,
        "entropy_norm": 0.935,
    },
    "drivers": [
        {"feature": "xg_diff_last5_delta", "value": 3.1, "contribution": 0.08, "direction": "for"},
        {"feature": "elo_delta", "value": 25.7, "contribution": 0.04, "direction": "for"},
    ],
    "risk_flags": ["small_training_set"],
    "metadata": {"train_size": 60, "train_rounds": [2, 3, 4, 5, 6, 7], "feature_subset": [], "C": 0.01},
}

_FLAGGED = {
    "report_id": "test_flag_1",
    "schema_version": "1.0",
    "model_version": "v1.1",
    "fixture": {
        "fixture_id": "4813200",
        "round_number": 8,
        "match_date": "2025-10-19",
        "home_team": "Burnley",
        "away_team": "Leeds United",
    },
    "probabilities": {"home_win": 0.415, "draw": 0.270, "away_win": 0.316},
    "prediction": {
        "predicted_result": "H",
        "confidence": "low",
        "p_max": 0.415,
        "margin_top2": 0.099,
        "entropy_norm": 0.985,
    },
    "drivers": [
        {"feature": "xg_diff_last5_delta", "value": -8.6, "contribution": -0.10, "direction": "against"},
    ],
    "risk_flags": ["near_uniform", "small_training_set"],
    "metadata": {"train_size": 60, "train_rounds": [2, 3, 4, 5, 6, 7], "feature_subset": [], "C": 0.01},
}

_TIGHT_MARGIN = {
    "report_id": "test_tight_1",
    "schema_version": "1.0",
    "model_version": "v1.1",
    "fixture": {
        "fixture_id": "4813100",
        "round_number": 15,
        "match_date": "2025-12-14",
        "home_team": "Brentford",
        "away_team": "Everton",
    },
    "probabilities": {"home_win": 0.38, "draw": 0.30, "away_win": 0.32},
    "prediction": {
        "predicted_result": "H",
        "confidence": "low",
        "p_max": 0.38,
        "margin_top2": 0.06,
        "entropy_norm": 0.96,
    },
    "drivers": [
        {"feature": "form_points_delta", "value": 2.0, "contribution": 0.03, "direction": "for"},
    ],
    "risk_flags": [],
    "metadata": {"train_size": 130, "train_rounds": list(range(2, 15)), "feature_subset": [], "C": 0.01},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_validation_ok():
    """All test fixtures pass validation."""
    for label, report in [("high", _HIGH_CONF), ("medium", _MEDIUM_CONF), ("flagged", _FLAGGED)]:
        validate_report(report)
    print("  [PASS] validation_ok")


def test_validation_bad_probs():
    """Bad probability sum raises error."""
    bad = {**_HIGH_CONF, "probabilities": {"home_win": 0.5, "draw": 0.5, "away_win": 0.5}}
    try:
        validate_report(bad)
        assert False, "Should have raised"
    except ReportValidationError:
        pass
    print("  [PASS] validation_bad_probs")


def test_validation_argmax_mismatch():
    """Mismatched argmax raises error."""
    bad = {**_HIGH_CONF, "probabilities": {"home_win": 0.2, "draw": 0.5, "away_win": 0.3}}
    try:
        validate_report(bad)
        assert False, "Should have raised"
    except ReportValidationError as e:
        assert "argmax" in str(e)
    print("  [PASS] validation_argmax_mismatch")


def test_validation_missing_report_id():
    """Missing report_id raises error."""
    bad = {k: v for k, v in _HIGH_CONF.items() if k != "report_id"}
    try:
        validate_report(bad)
        assert False, "Should have raised"
    except ReportValidationError as e:
        assert "report_id" in str(e)
    print("  [PASS] validation_missing_report_id")


def test_banned_words():
    """Banned causality words are caught."""
    try:
        validate_rendered_text("Arsenal will win guaranteed")
        assert False, "Should have raised"
    except ReportValidationError as e:
        assert "banned" in str(e).lower()
    print("  [PASS] banned_words")


def test_editorial_high_is_publish():
    assert classify_editorial(_HIGH_CONF) == "publish"
    print("  [PASS] editorial_high_is_publish")


def test_editorial_medium_is_publish():
    assert classify_editorial(_MEDIUM_CONF) == "publish"
    print("  [PASS] editorial_medium_is_publish")


def test_editorial_near_uniform_is_skip():
    assert classify_editorial(_FLAGGED) == "skip"
    print("  [PASS] editorial_near_uniform_is_skip")


def test_editorial_low_with_margin_is_watchlist():
    assert classify_editorial(_TIGHT_MARGIN) == "watchlist"
    print("  [PASS] editorial_low_with_margin_is_watchlist")


def test_telegram_contains_report_id():
    """Telegram post includes report_id for audit trail."""
    text = render_telegram_post(_HIGH_CONF)
    assert _HIGH_CONF["report_id"] in text
    print("  [PASS] telegram_contains_report_id")


def test_x_under_280_chars():
    """X post respects 280 char limit."""
    for report in [_HIGH_CONF, _MEDIUM_CONF, _FLAGGED]:
        text = render_x_post(report)
        assert len(text) <= 280, f"X post is {len(text)} chars: {text}"
    print("  [PASS] x_under_280_chars")


def test_telegram_no_banned_words():
    """Rendered telegram posts contain no banned language."""
    for report in [_HIGH_CONF, _MEDIUM_CONF, _FLAGGED]:
        text = render_telegram_post(report)
        validate_rendered_text(text)
    print("  [PASS] telegram_no_banned_words")


def test_watchlist_framing():
    """Watchlist games use 'Game to watch' not 'Strong lean'."""
    text = render_telegram_post(_TIGHT_MARGIN, editorial="watchlist")
    assert "Game to watch" in text
    assert "Strong lean" not in text
    print("  [PASS] watchlist_framing")


def test_small_training_set_not_in_external_caveat():
    """small_training_set is internal-only, not shown externally."""
    text = render_telegram_post(_MEDIUM_CONF)
    assert "Limited training" not in text
    print("  [PASS] small_training_set_not_in_external_caveat")


def test_snapshot_telegram(update: bool = False):
    """Snapshot test: telegram output matches golden file."""
    current = {}
    for label, report in [("high", _HIGH_CONF), ("medium", _MEDIUM_CONF), ("flagged", _FLAGGED)]:
        current[f"telegram_{label}"] = render_telegram_post(report)
        current[f"x_{label}"] = render_x_post(report)

    if update:
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(GOLDEN_PATH, "w") as f:
            json.dump(current, f, indent=2)
        print(f"  [UPDATED] Golden snapshots written to {GOLDEN_PATH}")
        return

    if not GOLDEN_PATH.exists():
        print(f"  [SKIP] No golden file at {GOLDEN_PATH}. Run with --update to create.")
        return

    with open(GOLDEN_PATH) as f:
        golden = json.load(f)

    for key in current:
        if key not in golden:
            print(f"  [FAIL] snapshot {key}: missing from golden file")
            continue
        if current[key] != golden[key]:
            print(f"  [FAIL] snapshot {key}: output changed!")
            print(f"    Expected:\n{golden[key]}")
            print(f"    Got:\n{current[key]}")
        else:
            print(f"  [PASS] snapshot {key}")


def run_all(update: bool = False):
    print("\nRenderer tests:")
    print("-" * 40)
    test_validation_ok()
    test_validation_bad_probs()
    test_validation_argmax_mismatch()
    test_validation_missing_report_id()
    test_banned_words()
    test_editorial_high_is_publish()
    test_editorial_medium_is_publish()
    test_editorial_near_uniform_is_skip()
    test_editorial_low_with_margin_is_watchlist()
    test_telegram_contains_report_id()
    test_x_under_280_chars()
    test_telegram_no_banned_words()
    test_watchlist_framing()
    test_small_training_set_not_in_external_caveat()
    test_snapshot_telegram(update=update)
    print("-" * 40)
    print("All tests passed.\n")


if __name__ == "__main__":
    update = "--update" in sys.argv
    run_all(update=update)
