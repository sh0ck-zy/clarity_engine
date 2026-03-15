"""
Prediction Tracker — build, resolve, and aggregate prediction records.

Pure functions, no LLM, no DB access. All data comes from existing JSON files.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_json(path: Path) -> Dict[str, Any] | None:
    """Load a JSON file, return None if missing."""
    if not path.exists():
        return None
    return json.loads(path.read_text())


def build_prediction_record(
    match_dir: Path,
    board_entry: Optional[Dict] = None,
    round_config: Optional[Dict] = None,
) -> dict:
    """
    Build a prediction record from cached match artifacts.

    Reads ml_anchor.json, match_intelligence.json, facts.json,
    evaluation_record.json from match_dir.
    """
    from intelligence.decision_engine import infer_lean_direction

    rc = round_config or {}

    # Load artifacts
    ml_anchor = _load_json(match_dir / "ml_anchor.json")
    mi = _load_json(match_dir / "match_intelligence.json")
    facts = _load_json(match_dir / "facts.json")
    eval_rec = _load_json(match_dir / "evaluation_record.json")
    board = board_entry or _load_json(match_dir / "board_entry.json")

    # Fixture metadata
    fixture = {}
    if eval_rec:
        fix = eval_rec.get("fixture", eval_rec)
        fixture = {
            "home_team": fix.get("home_team", ""),
            "away_team": fix.get("away_team", ""),
            "round": fix.get("round_number", rc.get("round_number")),
            "league": fix.get("league", rc.get("league")),
            "match_date": fix.get("match_date", ""),
        }

    match_id = ""
    if eval_rec:
        match_id = str(eval_rec.get("match_id", ""))

    # ML layer
    ml_layer = None
    if ml_anchor:
        probs = ml_anchor.get("probabilities", {})
        direction = ml_anchor.get("predicted_result", ml_anchor.get("direction", ""))
        margin = ml_anchor.get("margin", 0.0)
        entropy = ml_anchor.get("entropy", None)
        ml_layer = {
            "direction": direction,
            "probabilities": {
                "H": probs.get("H", 0.0),
                "D": probs.get("D", 0.0),
                "A": probs.get("A", 0.0),
            },
            "margin": margin,
            "entropy": entropy,
        }

    # Tactical layer — infer direction from lean text
    tactical_layer = None
    if mi:
        lean_text = mi.get("lean", "")
        if lean_text:
            home = fixture.get("home_team", "")
            away = fixture.get("away_team", "")
            tac_dir = infer_lean_direction(lean_text, home, away)
            tactical_layer = {"direction": tac_dir, "source": "lean_text_inferred"}

    # Engine layer — from decision dict in MI
    engine_layer = None
    if mi and mi.get("decision"):
        dec = mi["decision"]
        engine_layer = {
            "action": dec.get("action", "NO_BET"),
            "direction": dec.get("direction"),
            "confidence": dec.get("confidence_level", dec.get("confidence")),
            "edge_vs_market": dec.get("edge_vs_market"),
            "override_reason": dec.get("override_reason"),
        }

    # Odds snapshot
    odds_snapshot = _build_odds_snapshot(facts)

    # Board info
    board_category = None
    clarity_score = None
    board_version = None
    if board:
        board_category = board.get("category", board.get("board_category"))
        clarity_score = board.get("clarity_score")
        board_version = board.get("schema_version")

    # Provenance
    engine_version = "unknown"
    if eval_rec:
        engine_version = eval_rec.get("method_version", "unknown")
    provenance = {
        "model_version": rc.get("model_version", "unknown"),
        "engine_version": engine_version,
        "board_version": board_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "schema_version": "1.0",
        "match_id": match_id,
        "fixture": fixture,
        "provenance": provenance,
        "predictions": {
            "ml_layer": ml_layer,
            "tactical_layer": tactical_layer,
            "engine_layer": engine_layer,
        },
        "odds_snapshot": odds_snapshot,
        "board_category": board_category,
        "clarity_score": clarity_score,
        "resolution": None,
    }


def _build_odds_snapshot(facts: Optional[Dict]) -> Optional[Dict]:
    """Build odds snapshot from facts.json market_odds."""
    if not facts:
        return None
    mkt = facts.get("market_odds")
    if not mkt:
        return None

    has_decimal = all(
        mkt.get(k) is not None for k in ("odds_H", "odds_D", "odds_A")
    )
    has_probs = all(
        mkt.get(k) is not None for k in ("prob_H", "prob_D", "prob_A")
    )

    if not has_decimal and not has_probs:
        return None

    if has_decimal:
        return {
            "market": "1X2",
            "source": mkt.get("source", "Bet365"),
            "odds_H": mkt["odds_H"],
            "odds_D": mkt["odds_D"],
            "odds_A": mkt["odds_A"],
            "prob_H": mkt.get("prob_H", round(1 / mkt["odds_H"], 4)),
            "prob_D": mkt.get("prob_D", round(1 / mkt["odds_D"], 4)),
            "prob_A": mkt.get("prob_A", round(1 / mkt["odds_A"], 4)),
            "price_source": mkt.get("price_source", "decimal_odds"),
        }
    else:
        # Only implied probs — reconstruct decimal odds
        prob_h = mkt["prob_H"]
        prob_d = mkt["prob_D"]
        prob_a = mkt["prob_A"]
        return {
            "market": "1X2",
            "source": mkt.get("source", "Bet365"),
            "odds_H": round(1 / prob_h, 2) if prob_h else None,
            "odds_D": round(1 / prob_d, 2) if prob_d else None,
            "odds_A": round(1 / prob_a, 2) if prob_a else None,
            "prob_H": prob_h,
            "prob_D": prob_d,
            "prob_A": prob_a,
            "price_source": "implied_from_probability",
        }


def resolve_prediction(
    prediction: dict,
    actual_result: str,
    home_score: int,
    away_score: int,
) -> dict:
    """
    Fill resolution into a prediction record. Idempotent — only fills if null.

    Returns the prediction dict with resolution filled.
    """
    if prediction.get("resolution") is not None:
        return prediction

    preds = prediction.get("predictions", {})
    odds = prediction.get("odds_snapshot")

    # Layer correctness
    ml_correct = None
    tactical_correct = None
    engine_correct = None

    ml = preds.get("ml_layer")
    if ml and ml.get("direction"):
        ml_correct = ml["direction"] == actual_result

    tac = preds.get("tactical_layer")
    if tac and tac.get("direction"):
        tactical_correct = tac["direction"] == actual_result

    eng = preds.get("engine_layer")
    if eng and eng.get("direction"):
        engine_correct = eng["direction"] == actual_result

    # PnL — flat-stake 1X2
    pnl = _compute_pnl(eng, odds, actual_result)

    prediction["resolution"] = {
        "actual_result": actual_result,
        "home_score": home_score,
        "away_score": away_score,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "layers": {
            "ml_correct": ml_correct,
            "tactical_correct": tactical_correct,
            "engine_correct": engine_correct,
        },
        "pnl": pnl,
    }

    return prediction


def _compute_pnl(
    engine_layer: Optional[Dict],
    odds_snapshot: Optional[Dict],
    actual_result: str,
) -> Dict:
    """Compute flat-stake PnL for a single prediction."""
    if not engine_layer:
        return {"stake": 0, "profit": 0.0, "note": "no_engine_layer"}

    action = engine_layer.get("action", "NO_BET")
    direction = engine_layer.get("direction")

    if action not in ("PICK", "LEAN"):
        return {"stake": 0, "profit": 0.0, "note": "no_stake"}

    if not odds_snapshot or not direction:
        return {"stake": 0, "profit": 0.0, "note": "no_odds"}

    # Get the decimal odds for the picked direction
    price_source = odds_snapshot.get("price_source", "decimal_odds")
    if price_source == "decimal_odds":
        odds_val = odds_snapshot.get(f"odds_{direction}")
    else:
        prob_val = odds_snapshot.get(f"prob_{direction}")
        odds_val = (1 / prob_val) if prob_val else None

    if not odds_val:
        return {"stake": 0, "profit": 0.0, "note": "no_odds_for_direction"}

    stake = 1.0 if action == "PICK" else 0.5
    correct = direction == actual_result
    profit = round((odds_val - 1) * stake, 4) if correct else round(-stake, 4)

    return {
        "stake": stake,
        "profit": profit,
        "odds_used": round(odds_val, 2),
        "correct": correct,
    }


def build_round_track_record(round_dir: Path) -> dict:
    """
    Walk round_dir/matches/*/prediction_record.json, aggregate resolved matches.
    """
    matches_dir = round_dir / "matches"
    if not matches_dir.exists():
        # round_dir might already be the matches parent
        if (round_dir / "prediction_record.json").exists():
            matches_dir = round_dir.parent / "matches"
        else:
            matches_dir = round_dir

    records = []
    for match_dir in sorted(matches_dir.iterdir()):
        if not match_dir.is_dir():
            continue
        pred_path = match_dir / "prediction_record.json"
        if pred_path.exists():
            records.append(json.loads(pred_path.read_text()))

    total = len(records)
    resolved = [r for r in records if r.get("resolution") is not None]

    # Layer hit rates
    by_layer = {}
    for layer_key in ("ml_correct", "tactical_correct", "engine_correct"):
        vals = [
            r["resolution"]["layers"][layer_key]
            for r in resolved
            if r["resolution"]["layers"].get(layer_key) is not None
        ]
        correct = sum(1 for v in vals if v)
        by_layer[layer_key.replace("_correct", "")] = {
            "total": len(vals),
            "correct": correct,
            "hit_rate": round(correct / len(vals), 4) if vals else None,
        }

    # By action
    by_action = {}
    for action in ("PICK", "LEAN", "WATCHLIST", "NO_BET"):
        matches = [
            r for r in resolved
            if r.get("predictions", {}).get("engine_layer", {}).get("action") == action
        ]
        pnls = [r["resolution"]["pnl"] for r in matches]
        correct = sum(1 for p in pnls if p.get("correct"))
        staked = sum(p.get("stake", 0) for p in pnls)
        profit = sum(p.get("profit", 0) for p in pnls)
        by_action[action] = {
            "count": len(matches),
            "correct": correct,
            "staked": round(staked, 2),
            "profit": round(profit, 4),
            "roi_pct": round(profit / staked * 100, 2) if staked else None,
        }

    # By category
    by_category = {}
    for cat in ("TOP_ANGLE", "LIVE_DOG", "TRAP_SPOT", "TOO_THIN", "UNCLASSIFIED"):
        matches = [
            r for r in resolved
            if (r.get("board_category") or "UNCLASSIFIED") == cat
        ]
        if not matches:
            continue
        pnls = [r["resolution"]["pnl"] for r in matches]
        correct = sum(1 for p in pnls if p.get("correct"))
        staked = sum(p.get("stake", 0) for p in pnls)
        profit = sum(p.get("profit", 0) for p in pnls)
        by_category[cat] = {
            "count": len(matches),
            "correct": correct,
            "staked": round(staked, 2),
            "profit": round(profit, 4),
        }

    # By confidence
    by_confidence = {}
    for r in resolved:
        eng = r.get("predictions", {}).get("engine_layer", {})
        conf = eng.get("confidence", "Unknown")
        if conf not in by_confidence:
            by_confidence[conf] = {"total": 0, "correct": 0}
        by_confidence[conf]["total"] += 1
        layers = r["resolution"]["layers"]
        if layers.get("engine_correct"):
            by_confidence[conf]["correct"] += 1
    for conf, vals in by_confidence.items():
        vals["hit_rate"] = (
            round(vals["correct"] / vals["total"], 4) if vals["total"] else None
        )

    # Overall ROI
    total_staked = sum(v["staked"] for v in by_action.values())
    total_profit = sum(v["profit"] for v in by_action.values())

    return {
        "total_matches": total,
        "resolved_matches": len(resolved),
        "by_layer": by_layer,
        "by_action": by_action,
        "by_category": by_category,
        "by_confidence": by_confidence,
        "roi": {
            "total_staked": round(total_staked, 2),
            "total_profit": round(total_profit, 4),
            "roi_pct": round(total_profit / total_staked * 100, 2) if total_staked else None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
