"""
Tests for draft guardrails: banned words, percentage verification, team names, fallback.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from pipeline.guardrails import validate_draft
from pipeline.schema_validator import validate_artifact


def _make_facts():
    return {
        "fixture": {
            "fixture_id": "TEST_003",
            "competition": "Premier League",
            "season": "2025/26",
            "round_number": 20,
            "match_date": "2026-02-01T15:00:00Z",
            "home_team": "Liverpool",
            "away_team": "Tottenham Hotspur",
        },
        "ml": {
            "probabilities": {"home_win": 0.55, "draw": 0.25, "away_win": 0.20},
            "prediction": {"predicted_result": "H", "confidence_label": "medium"},
            "signals": {"p_max": 0.55, "margin_top2": 0.30, "entropy_norm": 0.88},
            "drivers": [
                {"feature": "elo_delta", "value": 100.0, "contribution": 0.3, "direction": "home"},
            ],
            "risk_flags": [],
        },
        "provenance": {
            "run_id": "run_guardrail_test",
            "facts_hash": "sha256:test",
        },
    }


def _make_report():
    return {
        "report_id": "rep_guardrail_test",
    }


class TestDraftGuardrails:

    def setup_method(self):
        self.facts = _make_facts()
        self.report = _make_report()

    def test_clean_draft_passes(self):
        text = (
            "R20 | Liverpool vs Tottenham Hotspur\n"
            "H 55% D 25% A 20%\n"
            "Moderate lean: Home Win\n"
            "[rep_guardrail_test]"
        )
        violations = validate_draft(text, self.facts, self.report)
        assert violations == []

    def test_banned_word_detected(self):
        text = (
            "Liverpool will definitely win this match.\n"
            "H 55% D 25% A 20%\n"
            "Tottenham have no chance.\n"
            "[rep_guardrail_test]"
        )
        violations = validate_draft(text, self.facts, self.report)
        banned = [v for v in violations if v.startswith("banned_word")]
        assert len(banned) >= 2  # "definitely" and "no chance"

    def test_fabricated_percentage_detected(self):
        text = (
            "Liverpool vs Tottenham Hotspur\n"
            "H 55% D 25% A 20%\n"
            "Liverpool have won 78% of their last matches.\n"
            "[rep_guardrail_test]"
        )
        violations = validate_draft(text, self.facts, self.report)
        pct_violations = [v for v in violations if "percentage" in v]
        assert len(pct_violations) >= 1  # 78% is fabricated

    def test_valid_percentage_passes(self):
        """Percentages within ±1.5pp of actual probs should pass."""
        text = (
            "Liverpool vs Tottenham Hotspur\n"
            "H 55% D 25% A 20%\n"
            "[rep_guardrail_test]"
        )
        violations = validate_draft(text, self.facts, self.report)
        pct_violations = [v for v in violations if "percentage" in v]
        assert pct_violations == []

    def test_missing_team_detected(self):
        text = (
            "The Reds face Spurs at Anfield.\n"
            "H 55% D 25% A 20%\n"
            "[rep_guardrail_test]"
        )
        violations = validate_draft(text, self.facts, self.report)
        team_violations = [v for v in violations if "missing_team" in v]
        # Liverpool has "pool" (>3 chars) which is in "Liverpool"... but "The Reds" != Liverpool
        # Tottenham has "tottenham" (>3 chars) but "Spurs" != any part of "Tottenham Hotspur"
        # Actually "tottenham" is in "Tottenham Hotspur" but not in the text "Spurs"
        assert len(team_violations) >= 1

    def test_missing_audit_trail_detected(self):
        text = (
            "Liverpool vs Tottenham Hotspur\n"
            "H 55% D 25% A 20%\n"
            "Moderate lean: Home Win"
        )
        violations = validate_draft(text, self.facts, self.report)
        audit_violations = [v for v in violations if "audit_trail" in v]
        assert len(audit_violations) == 1

    def test_partial_team_name_passes(self):
        """'Liverpool' contains 'pool' (>3 chars) in 'Liverpool' - but direct match is better."""
        text = (
            "Liverpool have a strong lean over Tottenham at Anfield.\n"
            "H 55% D 25% A 20%\n"
            "[rep_guardrail_test]"
        )
        violations = validate_draft(text, self.facts, self.report)
        team_violations = [v for v in violations if "missing_team" in v]
        assert team_violations == []


class TestDraftMetaSchema:
    """Verify draft_meta.schema.json compliance."""

    def test_valid_meta_passes(self):
        meta = {
            "schema_version": "1.0",
            "channel": "telegram",
            "source": "llm",
            "violations": [],
            "report_id": "rep_test",
            "run_id": "run_test",
            "char_count": 350,
            "created_at": "2026-02-24T18:00:00Z",
            "model": "gpt-4o-mini",
            "prompt_version": "draft_telegram_v1",
        }
        errors = validate_artifact(meta, "draft_meta")
        assert errors == []

    def test_template_fallback_meta(self):
        meta = {
            "schema_version": "1.0",
            "channel": "x",
            "source": "template_fallback",
            "violations": ["banned_word: 'definitely'"],
            "report_id": "rep_test",
            "run_id": "run_test",
            "char_count": 240,
            "created_at": "2026-02-24T18:00:00Z",
            "model": None,
            "prompt_version": None,
        }
        errors = validate_artifact(meta, "draft_meta")
        assert errors == []
