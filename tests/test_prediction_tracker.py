"""Tests for prediction_tracker — build, resolve, aggregate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from evaluation.prediction_tracker import (
    build_prediction_record,
    resolve_prediction,
    build_round_track_record,
)


# ── Fixtures ────────────────────────────────────────────────────

def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _make_match_dir(tmp_path: Path, name: str = "Arsenal_vs_Chelsea") -> Path:
    """Create a mock match directory with all artifacts."""
    match_dir = tmp_path / "matches" / name
    match_dir.mkdir(parents=True)

    _write_json(match_dir / "ml_anchor.json", {
        "predicted_result": "H",
        "probabilities": {"H": 0.45, "D": 0.30, "A": 0.25},
        "margin": 0.15,
        "entropy": 0.85,
    })

    _write_json(match_dir / "match_intelligence.json", {
        "lean": "Arsenal should control this game at home",
        "decision": {
            "action": "PICK",
            "direction": "H",
            "confidence_level": "High",
            "edge_vs_market": 0.05,
            "override_reason": None,
        },
    })

    _write_json(match_dir / "facts.json", {
        "market_odds": {
            "prob_H": 0.6497, "prob_D": 0.2001, "prob_A": 0.1502,
            "odds_H": 1.54, "odds_D": 5.00, "odds_A": 6.50,
            "source": "Bet365",
            "price_source": "decimal_odds",
        },
    })

    _write_json(match_dir / "evaluation_record.json", {
        "match_id": "4813665",
        "fixture": {
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "round_number": 30,
            "league": "PL",
            "match_date": "2026-03-14",
        },
        "method_version": "v1.8-decision",
    })

    return match_dir


# ── build_prediction_record ─────────────────────────────────────

class TestBuildPredictionRecord:
    def test_full_record(self, tmp_path):
        match_dir = _make_match_dir(tmp_path)
        rec = build_prediction_record(match_dir, round_config={
            "league": "PL", "round_number": 30,
            "model_version": "v1.4",
        })

        assert rec["schema_version"] == "1.0"
        assert rec["match_id"] == "4813665"
        assert rec["fixture"]["home_team"] == "Arsenal"
        assert rec["fixture"]["league"] == "PL"
        assert rec["resolution"] is None

        # ML layer
        ml = rec["predictions"]["ml_layer"]
        assert ml["direction"] == "H"
        assert ml["probabilities"]["H"] == 0.45

        # Tactical layer
        tac = rec["predictions"]["tactical_layer"]
        assert tac["direction"] == "H"
        assert tac["source"] == "lean_text_inferred"

        # Engine layer
        eng = rec["predictions"]["engine_layer"]
        assert eng["action"] == "PICK"
        assert eng["direction"] == "H"
        assert eng["confidence"] == "High"

        # Odds
        odds = rec["odds_snapshot"]
        assert odds["price_source"] == "decimal_odds"
        assert odds["odds_H"] == 1.54
        assert odds["prob_H"] == 0.6497

        # Provenance
        assert rec["provenance"]["model_version"] == "v1.4"
        assert rec["provenance"]["engine_version"] == "v1.8-decision"

    def test_no_odds(self, tmp_path):
        match_dir = _make_match_dir(tmp_path)
        _write_json(match_dir / "facts.json", {"market_odds": None})

        rec = build_prediction_record(match_dir)
        assert rec["odds_snapshot"] is None

    def test_implied_only(self, tmp_path):
        match_dir = _make_match_dir(tmp_path)
        _write_json(match_dir / "facts.json", {
            "market_odds": {
                "prob_H": 0.65, "prob_D": 0.20, "prob_A": 0.15,
                "source": "Bet365",
            },
        })

        rec = build_prediction_record(match_dir)
        odds = rec["odds_snapshot"]
        assert odds["price_source"] == "implied_from_probability"
        assert odds["odds_H"] == round(1 / 0.65, 2)

    def test_no_mi(self, tmp_path):
        match_dir = _make_match_dir(tmp_path)
        (match_dir / "match_intelligence.json").unlink()

        rec = build_prediction_record(match_dir)
        assert rec["predictions"]["tactical_layer"] is None
        assert rec["predictions"]["engine_layer"] is None


# ── resolve_prediction ──────────────────────────────────────────

class TestResolvePrediction:
    def _base_record(self):
        return {
            "predictions": {
                "ml_layer": {"direction": "H"},
                "tactical_layer": {"direction": "H"},
                "engine_layer": {"action": "PICK", "direction": "H", "confidence": "High"},
            },
            "odds_snapshot": {
                "odds_H": 1.54, "odds_D": 5.00, "odds_A": 6.50,
                "prob_H": 0.65, "prob_D": 0.20, "prob_A": 0.15,
                "price_source": "decimal_odds",
            },
            "resolution": None,
        }

    def test_pick_correct(self):
        rec = self._base_record()
        result = resolve_prediction(rec, "H", 2, 0)

        res = result["resolution"]
        assert res["actual_result"] == "H"
        assert res["layers"]["ml_correct"] is True
        assert res["layers"]["engine_correct"] is True
        assert res["pnl"]["stake"] == 1.0
        assert res["pnl"]["profit"] == round(1.54 - 1, 4)
        assert res["pnl"]["correct"] is True

    def test_pick_wrong(self):
        rec = self._base_record()
        result = resolve_prediction(rec, "D", 1, 1)

        res = result["resolution"]
        assert res["layers"]["ml_correct"] is False
        assert res["pnl"]["stake"] == 1.0
        assert res["pnl"]["profit"] == -1.0
        assert res["pnl"]["correct"] is False

    def test_lean_correct(self):
        rec = self._base_record()
        rec["predictions"]["engine_layer"]["action"] = "LEAN"
        result = resolve_prediction(rec, "H", 1, 0)

        assert result["resolution"]["pnl"]["stake"] == 0.5
        assert result["resolution"]["pnl"]["profit"] == round((1.54 - 1) * 0.5, 4)

    def test_watchlist_no_stake(self):
        rec = self._base_record()
        rec["predictions"]["engine_layer"]["action"] = "WATCHLIST"
        result = resolve_prediction(rec, "H", 1, 0)

        assert result["resolution"]["pnl"]["stake"] == 0
        assert result["resolution"]["pnl"]["profit"] == 0.0

    def test_no_odds(self):
        rec = self._base_record()
        rec["odds_snapshot"] = None
        result = resolve_prediction(rec, "H", 1, 0)

        assert result["resolution"]["pnl"]["note"] == "no_odds"
        assert result["resolution"]["pnl"]["stake"] == 0

    def test_idempotent(self):
        rec = self._base_record()
        first = resolve_prediction(rec, "H", 2, 0)
        first_profit = first["resolution"]["pnl"]["profit"]

        # Second call should not change anything
        second = resolve_prediction(first, "D", 1, 1)
        assert second["resolution"]["pnl"]["profit"] == first_profit
        assert second["resolution"]["actual_result"] == "H"

    def test_implied_odds_fallback(self):
        rec = self._base_record()
        rec["odds_snapshot"]["price_source"] = "implied_from_probability"
        result = resolve_prediction(rec, "H", 1, 0)

        expected_odds = 1 / 0.65
        expected_profit = round((expected_odds - 1) * 1.0, 4)
        assert result["resolution"]["pnl"]["profit"] == expected_profit


# ── build_round_track_record ────────────────────────────────────

class TestBuildRoundTrackRecord:
    def test_aggregation(self, tmp_path):
        round_dir = tmp_path

        # Match 1: PICK H, correct
        m1 = _make_match_dir(tmp_path, "Arsenal_vs_Chelsea")
        rec1 = build_prediction_record(m1)
        rec1["board_category"] = "TOP_ANGLE"
        rec1 = resolve_prediction(rec1, "H", 2, 0)
        _write_json(m1 / "prediction_record.json", rec1)

        # Match 2: LEAN A, wrong
        m2 = _make_match_dir(tmp_path, "Liverpool_vs_City")
        rec2 = build_prediction_record(m2)
        rec2["predictions"]["engine_layer"]["action"] = "LEAN"
        rec2["predictions"]["engine_layer"]["direction"] = "A"
        rec2["predictions"]["ml_layer"]["direction"] = "A"
        rec2["board_category"] = "LIVE_DOG"
        rec2 = resolve_prediction(rec2, "H", 3, 1)
        _write_json(m2 / "prediction_record.json", rec2)

        track = build_round_track_record(round_dir)

        assert track["total_matches"] == 2
        assert track["resolved_matches"] == 2

        # By action
        assert track["by_action"]["PICK"]["count"] == 1
        assert track["by_action"]["PICK"]["correct"] == 1
        assert track["by_action"]["LEAN"]["count"] == 1
        assert track["by_action"]["LEAN"]["correct"] == 0

        # ROI
        assert track["roi"]["total_staked"] == 1.5  # 1.0 + 0.5
        assert track["roi"]["total_profit"] == round(0.54 + (-0.5), 4)

        # By category
        assert track["by_category"]["TOP_ANGLE"]["correct"] == 1
        assert track["by_category"]["LIVE_DOG"]["correct"] == 0

    def test_empty_round(self, tmp_path):
        (tmp_path / "matches").mkdir()
        track = build_round_track_record(tmp_path)
        assert track["total_matches"] == 0
        assert track["resolved_matches"] == 0
