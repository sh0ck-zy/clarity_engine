"""
Tests for facts_builder: schema compliance, validation checks, self-hash, unavailable fields.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pandas as pd
from pipeline.facts_builder import build_facts
from pipeline.schema_validator import validate_artifact
from pipeline.hashing import compute_hash


def _make_fixture_row():
    """Create a minimal fixture row matching feature_builder output."""
    return pd.Series({
        "fotmob_match_id": "TEST_001",
        "round_number": 10,
        "match_date": pd.Timestamp("2026-01-15"),
        "home_team_name": "Everton",
        "away_team_name": "Manchester United",
        "result": "A",
        "home_position": 8,
        "home_goal_diff": 3,
        "home_form_points": 8,
        "home_xg_for_last5": 6.12,
        "home_xg_against_last5": 6.46,
        "home_xg_diff_last5": -0.34,
        "home_venue_points": 16.0,
        "away_position": 4,
        "away_goal_diff": 12,
        "away_form_points": 13,
        "away_xg_for_last5": 8.22,
        "away_xg_against_last5": 6.28,
        "away_xg_diff_last5": 1.94,
        "away_venue_points": 18.0,
        "home_elo": 1698.0,
        "away_elo": 1812.0,
        "elo_missing_any": 0,
        "elo_missing_home": 0,
        "elo_missing_away": 0,
        # Features (pre-computed in the feature builder)
        "xg_diff_last5_delta": -2.28,
        "form_points_delta": -5.0,
        "goal_diff_season_delta": -9.0,
        "position_delta": 4.0,
        "elo_delta": -114.0,
        "home_venue_points": 16.0,
        "away_venue_points": 18.0,
    })


def _make_audit_result():
    """Create a minimal audit result matching predict_fixture_with_audit output."""
    return {
        "ml_report": {
            "report_id": "test_report_001",
            "schema_version": "1.0",
            "model_version": "v1.1",
            "fixture": {
                "fixture_id": "TEST_001",
                "round_number": 10,
                "match_date": "2026-01-15",
                "home_team": "Everton",
                "away_team": "Manchester United",
            },
            "probabilities": {"home_win": 0.22, "draw": 0.23, "away_win": 0.55},
            "prediction": {
                "predicted_result": "A",
                "confidence": "medium",
                "p_max": 0.55,
                "margin_top2": 0.32,
                "entropy_norm": 0.90,
            },
            "drivers": [
                {"feature": "elo_delta", "value": -114.0, "contribution": -0.41, "direction": "for"},
            ],
            "risk_flags": [],
            "metadata": {
                "train_size": 90,
                "train_rounds": list(range(2, 10)),
                "feature_subset": ["xg_diff_last5_delta", "form_points_delta", "goal_diff_season_delta", "position_delta", "elo_delta", "home_venue_points", "away_venue_points"],
                "C": 0.01,
            },
        },
        "raw_features": {
            "xg_diff_last5_delta": -2.28,
            "form_points_delta": -5.0,
            "goal_diff_season_delta": -9.0,
            "position_delta": 4.0,
            "elo_delta": -114.0,
            "home_venue_points": 16.0,
            "away_venue_points": 18.0,
        },
        "scaled_features": {
            "xg_diff_last5_delta": -1.34,
            "form_points_delta": -1.66,
            "goal_diff_season_delta": -0.95,
            "position_delta": 0.79,
            "elo_delta": -1.34,
            "home_venue_points": 0.5,
            "away_venue_points": 0.6,
        },
        "scaling_params": {
            "xg_diff_last5_delta": {"mean": 0.03, "scale": 1.72},
            "form_points_delta": {"mean": 0.10, "scale": 3.08},
            "goal_diff_season_delta": {"mean": 0.22, "scale": 9.75},
            "position_delta": {"mean": 0.01, "scale": 5.10},
            "elo_delta": {"mean": 1.80, "scale": 86.40},
            "home_venue_points": {"mean": 12.0, "scale": 4.0},
            "away_venue_points": {"mean": 10.0, "scale": 5.0},
        },
        "class_order": ["A", "D", "H"],
        "coefficients": {},
        "train_size": 90,
        "train_rounds": list(range(2, 10)),
        "drivers_directional": [
            {"feature": "elo_delta", "value": -114.0, "contribution": -0.41, "direction": "away"},
            {"feature": "form_points_delta", "value": -5.0, "contribution": -0.33, "direction": "away"},
            {"feature": "xg_diff_last5_delta", "value": -2.28, "contribution": -0.28, "direction": "away"},
            {"feature": "goal_diff_season_delta", "value": -9.0, "contribution": -0.19, "direction": "away"},
            {"feature": "position_delta", "value": 4.0, "contribution": 0.05, "direction": "home"},
        ],
    }


class TestFactsBuilder:
    """Test suite for facts_builder.build_facts()."""

    def setup_method(self):
        self.row = _make_fixture_row()
        self.audit = _make_audit_result()
        self.run_id = "run_test_12345"
        self.facts = build_facts(self.row, self.audit, self.run_id)

    def test_schema_compliance(self):
        """facts.json must pass JSON Schema validation."""
        errors = validate_artifact(self.facts, "facts")
        assert errors == [], f"Schema violations: {errors}"

    def test_schema_version(self):
        assert self.facts["schema_version"] == "1.0"

    def test_fixture_fields(self):
        f = self.facts["fixture"]
        assert f["fixture_id"] == "TEST_001"
        assert f["home_team"] == "Everton"
        assert f["away_team"] == "Manchester United"
        assert f["round_number"] == 10
        assert f["competition"] == "Premier League"

    def test_unavailable_explicit(self):
        """All unavailable fields must be listed with reasons."""
        unavailable = self.facts["inputs"]["unavailable"]
        fields = {u["field"] for u in unavailable}
        assert "h2h" in fields
        assert "key_players" in fields
        assert "injuries" in fields
        assert "odds" in fields
        for u in unavailable:
            assert u["reason"], f"Missing reason for {u['field']}"

    def test_nullable_inputs(self):
        """h2h, key_players, injuries must be null in v1."""
        det = self.facts["inputs"]["deterministic"]
        assert det["h2h"] is None
        assert det["key_players"] is None
        assert det["injuries"] is None
        assert self.facts["inputs"]["non_deterministic"]["odds"] is None

    def test_features_present(self):
        features = self.facts["derived"]["features"]
        names = [f["name"] for f in features]
        assert "xg_diff_last5_delta" in names
        assert "elo_delta" in names
        assert len(features) == 7

    def test_scaling_present(self):
        scaling = self.facts["derived"]["scaling"]
        assert len(scaling) == 7
        for s in scaling:
            assert "mean" in s
            assert "scale" in s
            assert "scaled_value" in s

    def test_ml_probabilities_sum(self):
        probs = self.facts["ml"]["probabilities"]
        total = probs["home_win"] + probs["draw"] + probs["away_win"]
        assert abs(total - 1.0) < 0.02

    def test_validation_checks(self):
        checks = self.facts["validation_checks"]
        check_names = {c["name"] for c in checks}
        assert "prob_sum" in check_names
        assert "argmax_matches_prediction" in check_names
        assert "elo_available" in check_names
        assert "training_size_minimum" in check_names

    def test_provenance_run_id(self):
        assert self.facts["provenance"]["run_id"] == self.run_id

    def test_self_hash(self):
        """facts_hash must be a valid self-hash (sha256:...)."""
        facts_hash = self.facts["provenance"]["facts_hash"]
        assert facts_hash.startswith("sha256:")
        # Recompute and verify
        recomputed = compute_hash(
            self.facts, self_hash_path=["provenance", "facts_hash"]
        )
        assert recomputed == facts_hash

    def test_drivers_directional(self):
        """Drivers must use home/draw/away/mixed direction."""
        for d in self.facts["ml"]["drivers"]:
            assert d["direction"] in ("home", "draw", "away", "mixed")
