"""
Tests for board classifier, daily board builder, and board telegram renderer.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from intelligence.board_classifier import BoardEntry, classify_board_category, _compute_clarity_score
from intelligence.daily_board import build_daily_board
from renderers.board_telegram import render_board_telegram


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_decision(action="PICK", direction="H", confidence="High", edge=0.05,
                   ml_dir="H", tac_dir="H"):
    return {
        "action": action,
        "direction": direction,
        "reasoning": [],
        "edge_vs_market": edge,
        "directions": {
            "ml_anchor": ml_dir,
            "tactical_read": tac_dir,
            "final_decision": direction,
            "override_reason": None,
        },
    }


def _make_signals(upset=False, fragile=False, draw_pressure=False):
    return {
        "signals": {
            "upset_potential": upset,
            "fragile_home_edge": fragile,
            "draw_pressure_risk": draw_pressure,
            "home_territorial_edge": False,
            "away_transition_threat": False,
        }
    }


def _make_ml_anchor(predicted="H", margin=0.15, entropy=0.85):
    return {
        "predicted_result": predicted,
        "probabilities": {"H": 0.45, "D": 0.30, "A": 0.25},
        "signals": {
            "margin_top2": margin,
            "entropy_norm": entropy,
        },
    }


def _make_mi_result(home="Liverpool", away="Spurs", confidence="High",
                    lean="Liverpool's press creates overloads",
                    core_read="High press vs fragile spine"):
    return {
        "match_id": "12345",
        "home_team": home,
        "away_team": away,
        "fixture": {"fixture_id": "12345", "home_team": home, "away_team": away},
        "confidence": confidence,
        "lean": lean,
        "core_read": core_read,
        "mi_status": "ready",
    }


# ---------------------------------------------------------------------------
# Board classifier tests
# ---------------------------------------------------------------------------

class TestBoardClassifier:

    def test_top_angle(self):
        decision = _make_decision(action="PICK", edge=0.05, confidence="High")
        mi = _make_mi_result(confidence="High")
        entry = classify_board_category(decision, _make_signals(), _make_ml_anchor(), mi)
        assert entry.category == "TOP_ANGLE"
        assert entry.clarity_score > 70

    def test_top_angle_needs_edge(self):
        decision = _make_decision(action="PICK", edge=0.02, confidence="High")
        mi = _make_mi_result(confidence="High")
        entry = classify_board_category(decision, _make_signals(), _make_ml_anchor(), mi)
        assert entry.category != "TOP_ANGLE"

    def test_live_dog(self):
        decision = _make_decision(action="LEAN", direction="A",
                                  ml_dir="H", tac_dir="A")
        signals = _make_signals(upset=True)
        ml = _make_ml_anchor(predicted="H")
        mi = _make_mi_result(confidence="Medium-High")
        entry = classify_board_category(decision, signals, ml, mi)
        assert entry.category == "LIVE_DOG"

    def test_live_dog_needs_divergence(self):
        decision = _make_decision(action="LEAN", direction="H",
                                  ml_dir="H", tac_dir="H")
        signals = _make_signals(upset=True)
        ml = _make_ml_anchor(predicted="H")
        mi = _make_mi_result()
        entry = classify_board_category(decision, signals, ml, mi)
        assert entry.category != "LIVE_DOG"

    def test_trap_spot_divergence(self):
        decision = _make_decision(action="WATCHLIST", direction="D",
                                  ml_dir="H", tac_dir="D")
        mi = _make_mi_result(confidence="Medium")
        entry = classify_board_category(decision, _make_signals(), _make_ml_anchor(), mi)
        assert entry.category == "TRAP_SPOT"

    def test_trap_spot_draw_pressure(self):
        decision = _make_decision(action="WATCHLIST", direction="H",
                                  ml_dir="H", tac_dir="H")
        signals = _make_signals(draw_pressure=True)
        mi = _make_mi_result(confidence="Medium")
        entry = classify_board_category(decision, signals, _make_ml_anchor(), mi)
        assert entry.category == "TRAP_SPOT"

    def test_too_thin_default(self):
        decision = _make_decision(action="NO_BET", direction=None, edge=None)
        mi = _make_mi_result(confidence="Low")
        entry = classify_board_category(decision, _make_signals(), _make_ml_anchor(), mi)
        assert entry.category == "TOO_THIN"

    def test_to_dict_roundtrip(self):
        decision = _make_decision()
        mi = _make_mi_result()
        entry = classify_board_category(decision, _make_signals(), _make_ml_anchor(), mi)
        d = entry.to_dict()
        assert d["category"] in ("TOP_ANGLE", "LIVE_DOG", "TRAP_SPOT", "TOO_THIN")
        assert isinstance(d["clarity_score"], int)


class TestClarityScore:

    def test_high_confidence_high_edge(self):
        score = _compute_clarity_score("High", 0.06, False, 0, 0.85)
        assert score == 95  # 50 + 20 + 15 + 10

    def test_medium_confidence(self):
        score = _compute_clarity_score("Medium", 0.03, False, 0, 0.90)
        assert score == 78  # 50 + 10 + 8 + 10

    def test_penalties(self):
        score = _compute_clarity_score("High", 0.01, True, 3, 1.0)
        # 50 + 20 + 0 + 0 - 10 - 15 = 45
        assert score == 45

    def test_clamped_to_range(self):
        score = _compute_clarity_score("Low", None, True, 5, 1.0)
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# Daily board tests
# ---------------------------------------------------------------------------

class TestDailyBoard:

    def _create_mock_round(self, tmp: Path, matches: list[dict]):
        """Create a mock round directory with match artifacts."""
        config = {"league": "PL", "round_number": 30}
        (tmp / "config.json").write_text(json.dumps(config))

        matches_dir = tmp / "matches"
        for m in matches:
            name = m["name"]
            mdir = matches_dir / name
            mdir.mkdir(parents=True)

            if m.get("mi"):
                (mdir / "match_intelligence.json").write_text(json.dumps(m["mi"]))
            if m.get("signals"):
                (mdir / "match_signals.json").write_text(json.dumps(m["signals"]))
            if m.get("ml_anchor"):
                (mdir / "ml_anchor.json").write_text(json.dumps(m["ml_anchor"]))
            if m.get("report"):
                (mdir / "report.json").write_text(json.dumps(m["report"]))

    def test_board_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._create_mock_round(tmp, [{
                "name": "Liverpool_vs_Spurs",
                "mi": _make_mi_result() | {"decision": _make_decision()},
                "signals": _make_signals(),
                "ml_anchor": _make_ml_anchor(),
                "report": {"fixture": {"fixture_id": "1", "home_team": "Liverpool",
                                       "away_team": "Spurs", "round_number": 30}},
            }])

            board = build_daily_board(tmp)
            assert board["schema_version"] == "1.0"
            assert board["league"] == "PL"
            assert board["round_number"] == 30
            assert board["matches_analyzed"] == 1
            assert len(board["board"]) == 1
            assert "category" in board["board"][0]

    def test_skipped_matches_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._create_mock_round(tmp, [{
                "name": "Arsenal_vs_Everton",
                "mi": {"mi_status": "skip", "reason": "bad data"},
                "signals": _make_signals(),
                "ml_anchor": _make_ml_anchor(),
                "report": {},
            }])

            board = build_daily_board(tmp)
            assert board["matches_analyzed"] == 0

    def test_board_sorting(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._create_mock_round(tmp, [
                {
                    "name": "Match_A",
                    "mi": _make_mi_result("A", "B", confidence="Low") | {
                        "decision": _make_decision(action="NO_BET", direction=None, edge=None)
                    },
                    "signals": _make_signals(),
                    "ml_anchor": _make_ml_anchor(),
                    "report": {"fixture": {"fixture_id": "1", "home_team": "A",
                                           "away_team": "B", "round_number": 30}},
                },
                {
                    "name": "Match_B",
                    "mi": _make_mi_result("C", "D", confidence="High") | {
                        "decision": _make_decision(action="PICK", edge=0.06)
                    },
                    "signals": _make_signals(),
                    "ml_anchor": _make_ml_anchor(),
                    "report": {"fixture": {"fixture_id": "2", "home_team": "C",
                                           "away_team": "D", "round_number": 30}},
                },
            ])

            board = build_daily_board(tmp)
            categories = [e["category"] for e in board["board"]]
            assert categories[0] == "TOP_ANGLE"
            assert categories[-1] == "TOO_THIN"

    def test_writes_board_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._create_mock_round(tmp, [{
                "name": "Test_Match",
                "mi": _make_mi_result() | {"decision": _make_decision()},
                "signals": _make_signals(),
                "ml_anchor": _make_ml_anchor(),
                "report": {"fixture": {"fixture_id": "1", "home_team": "Liverpool",
                                       "away_team": "Spurs", "round_number": 30}},
            }])

            build_daily_board(tmp)
            assert (tmp / "board.json").exists()


# ---------------------------------------------------------------------------
# Telegram renderer tests
# ---------------------------------------------------------------------------

class TestBoardTelegram:

    def test_renders_header(self):
        board = {
            "league": "PL",
            "round_number": 30,
            "date": "2026-03-14",
            "matches_analyzed": 10,
            "actionable_angles": 2,
            "board": [],
        }
        text = render_board_telegram(board)
        assert "CLARITY BOARD" in text
        assert "PL R30" in text
        assert "10 analyzed" in text
        assert "2 actionable" in text
        assert "[v1.8-board]" in text

    def test_full_treatment_for_top_angle(self):
        board = {
            "league": "PL", "round_number": 30, "date": "2026-03-14",
            "matches_analyzed": 1, "actionable_angles": 1,
            "board": [{
                "category": "TOP_ANGLE",
                "home_team": "Liverpool",
                "away_team": "Spurs",
                "action": "PICK",
                "direction": "H",
                "confidence": "High",
                "edge": 0.083,
                "core_read": "Liverpool press creates overloads",
                "clarity_score": 78,
                "directions": {},
            }],
        }
        text = render_board_telegram(board)
        assert "[TARGET]" in text
        assert "Liverpool vs Spurs" in text
        assert "PICK" in text
        assert "Score: 78" in text

    def test_compact_treatment_for_trap(self):
        board = {
            "league": "PL", "round_number": 30, "date": "2026-03-14",
            "matches_analyzed": 1, "actionable_angles": 0,
            "board": [{
                "category": "TRAP_SPOT",
                "home_team": "Arsenal",
                "away_team": "Everton",
                "action": "WATCHLIST",
                "direction": "H",
                "confidence": "Medium",
                "edge": None,
                "core_read": "Draw gravity is real",
                "clarity_score": 45,
                "directions": {"ml_anchor": "D", "tactical_read": "H"},
            }],
        }
        text = render_board_telegram(board)
        assert "[TRAP]" in text
        assert "ML->" in text

    def test_too_thin_collapsed(self):
        board = {
            "league": "PL", "round_number": 30, "date": "2026-03-14",
            "matches_analyzed": 4, "actionable_angles": 0,
            "board": [
                {"category": "TOO_THIN", "home_team": "A", "away_team": "B",
                 "action": "NO_BET", "direction": None, "confidence": "Low",
                 "edge": None, "core_read": "", "clarity_score": 30, "directions": {}},
                {"category": "TOO_THIN", "home_team": "C", "away_team": "D",
                 "action": "NO_BET", "direction": None, "confidence": "Low",
                 "edge": None, "core_read": "", "clarity_score": 30, "directions": {}},
                {"category": "TOO_THIN", "home_team": "E", "away_team": "F",
                 "action": "NO_BET", "direction": None, "confidence": "Low",
                 "edge": None, "core_read": "", "clarity_score": 30, "directions": {}},
            ],
        }
        text = render_board_telegram(board)
        assert "TOO THIN:" in text
        assert "+1 more" in text


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
