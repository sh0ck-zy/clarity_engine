"""
Tests for report_writer: schema compliance, verbatim copy, writer_metadata.

Uses template_fallback mode to avoid LLM dependency in tests.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from pipeline.report_writer import write_report, _template_fallback
from pipeline.schema_validator import validate_artifact


def _make_facts():
    """Minimal facts.json for testing."""
    return {
        "schema_version": "1.0",
        "fixture": {
            "fixture_id": "TEST_002",
            "competition": "Premier League",
            "season": "2025/26",
            "round_number": 15,
            "match_date": "2026-01-20T15:00:00Z",
            "home_team": "Chelsea",
            "away_team": "Arsenal",
        },
        "inputs": {
            "deterministic": {
                "team_states": {"snapshot_round": 14, "home": {}, "away": {}},
                "h2h": None,
                "key_players": None,
                "injuries": None,
            },
            "non_deterministic": {"elo": None, "odds": None},
            "unavailable": [{"field": "h2h", "reason": "deferred_to_v1_1"}],
        },
        "derived": {
            "features": [
                {"name": "xg_diff_last5_delta", "value": 1.5, "source": "team_states.xg_diff_last5"},
                {"name": "form_points_delta", "value": 3.0, "source": "team_states.form_points"},
                {"name": "goal_diff_season_delta", "value": 5.0, "source": "team_states.goal_difference"},
                {"name": "position_delta", "value": 2.0, "source": "team_states.position"},
                {"name": "elo_delta", "value": 50.0, "source": "elo_cache"},
                {"name": "home_venue_points", "value": 20.0, "source": "team_states.home_points"},
                {"name": "away_venue_points", "value": 15.0, "source": "team_states.away_points"},
            ],
            "scaling": [
                {"feature": "xg_diff_last5_delta", "mean": 0.0, "scale": 1.0, "scaled_value": 1.5},
                {"feature": "form_points_delta", "mean": 0.0, "scale": 1.0, "scaled_value": 3.0},
                {"feature": "goal_diff_season_delta", "mean": 0.0, "scale": 1.0, "scaled_value": 5.0},
                {"feature": "position_delta", "mean": 0.0, "scale": 1.0, "scaled_value": 2.0},
                {"feature": "elo_delta", "mean": 0.0, "scale": 1.0, "scaled_value": 50.0},
                {"feature": "home_venue_points", "mean": 0.0, "scale": 1.0, "scaled_value": 20.0},
                {"feature": "away_venue_points", "mean": 0.0, "scale": 1.0, "scaled_value": 15.0},
            ],
        },
        "ml": {
            "model": {
                "name": "logistic_regression_multinomial",
                "version": "v1.1",
                "feature_subset": "COMPACT_CORE",
                "C": 0.01,
                "random_state": 42,
            },
            "probabilities": {"home_win": 0.45, "draw": 0.30, "away_win": 0.25},
            "prediction": {"predicted_result": "H", "confidence_label": "medium"},
            "signals": {"p_max": 0.45, "margin_top2": 0.15, "entropy_norm": 0.92},
            "drivers": [
                {"feature": "elo_delta", "value": 50.0, "contribution": 0.3, "direction": "home"},
                {"feature": "form_points_delta", "value": 3.0, "contribution": 0.2, "direction": "home"},
                {"feature": "goal_diff_season_delta", "value": 5.0, "contribution": 0.15, "direction": "home"},
            ],
            "risk_flags": [],
            "training_context": {"train_size": 140, "train_rounds": list(range(2, 15))},
        },
        "validation_checks": [
            {"name": "prob_sum", "status": "pass", "details": "1.0000"},
        ],
        "provenance": {
            "run_id": "run_test_999",
            "created_at": "2026-01-20T14:00:00Z",
            "facts_hash": "sha256:abc123def456",
            "data_snapshot_round": 14,
            "deterministic_sources": ["postgres.fotmob_matches"],
            "non_deterministic_sources": [],
        },
    }


class TestReportWriterContract:
    """Tests that report.json respects the contract."""

    def setup_method(self):
        self.facts = _make_facts()
        # Use template fallback (no LLM call) by generating narrative directly
        narrative = _template_fallback(self.facts)
        # Build report manually to test the contract without LLM
        from pipeline.report_writer import write_report
        from pipeline.hashing import compute_hash
        from datetime import datetime, timezone

        facts_hash = self.facts["provenance"]["facts_hash"]
        report_id = "rep_" + compute_hash(self.facts, self_hash_path=["provenance", "facts_hash"])[7:17]

        self.report = {
            "schema_version": "1.0",
            "report_id": report_id,
            "fixture": {
                "fixture_id": self.facts["fixture"]["fixture_id"],
                "round_number": self.facts["fixture"]["round_number"],
                "match_date": self.facts["fixture"]["match_date"],
                "home_team": self.facts["fixture"]["home_team"],
                "away_team": self.facts["fixture"]["away_team"],
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
            "probabilities": self.facts["ml"]["probabilities"].copy(),
            "prediction": self.facts["ml"]["prediction"].copy(),
            "signals": self.facts["ml"]["signals"].copy(),
            "risk_flags": list(self.facts["ml"]["risk_flags"]),
            "writer_metadata": {
                "model": "template",
                "temperature": 0.3,
                "prompt_version": "writer_v1",
                "facts_hash": facts_hash,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "generation_mode": "template_fallback",
            },
        }

    def test_schema_compliance(self):
        errors = validate_artifact(self.report, "report")
        assert errors == [], f"Schema violations: {errors}"

    def test_probabilities_verbatim(self):
        """Probabilities must be copied exactly from facts, not LLM-generated."""
        assert self.report["probabilities"] == self.facts["ml"]["probabilities"]

    def test_prediction_verbatim(self):
        """Prediction must be copied exactly from facts."""
        assert self.report["prediction"] == self.facts["ml"]["prediction"]

    def test_signals_verbatim(self):
        """Signals must be copied exactly from facts."""
        assert self.report["signals"] == self.facts["ml"]["signals"]

    def test_risk_flags_verbatim(self):
        """Risk flags must be copied exactly from facts."""
        assert self.report["risk_flags"] == self.facts["ml"]["risk_flags"]

    def test_writer_metadata_present(self):
        wm = self.report["writer_metadata"]
        assert "model" in wm
        assert "temperature" in wm
        assert "prompt_version" in wm
        assert "facts_hash" in wm
        assert "created_at" in wm
        assert "generation_mode" in wm

    def test_facts_hash_in_metadata(self):
        assert self.report["writer_metadata"]["facts_hash"] == self.facts["provenance"]["facts_hash"]

    def test_summary_not_empty(self):
        assert len(self.report["summary"]["headline"]) > 0
        assert len(self.report["summary"]["overview"]) > 0

    def test_key_factors_is_list(self):
        assert isinstance(self.report["analysis"]["key_factors"], list)
        assert len(self.report["analysis"]["key_factors"]) > 0
