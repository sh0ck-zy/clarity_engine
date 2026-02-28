"""
Facts builder: assembles a complete facts.json for a single fixture.

facts.json is the audit source of truth for the Analysis Dossier.
All data provenance, features, ML output, and validation checks are recorded here.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from models import config as model_config
from pipeline.hashing import compute_hash

# Feature source mapping: which input produces each derived feature
_FEATURE_SOURCES = {
    "xg_diff_last5_delta": "team_states.xg_diff_last5",
    "form_points_delta": "team_states.form_points",
    "goal_diff_season_delta": "team_states.goal_difference",
    "position_delta": "team_states.position",
    "elo_delta": "elo_cache",
    "home_venue_points": "team_states.home_points",
    "away_venue_points": "team_states.away_points",
}


def build_facts(
    fixture_row: pd.Series,
    audit_result: Dict[str, Any],
    run_id: str,
    team_states: Optional[Dict[str, Any]] = None,
    elo_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build facts.json for a single fixture.

    Args:
        fixture_row: Row from the feature dataset DataFrame.
        audit_result: Output of predict_fixture_with_audit().
        run_id: Unique run identifier.
        team_states: Optional pre-fetched team_states for home/away.
        elo_info: Optional ELO details {pre_match_elo_date, home, away, source, cache_hit}.

    Returns:
        facts dict conforming to facts.schema.json.
    """
    ml_report = audit_result["ml_report"]
    round_number = int(fixture_row["round_number"])
    snapshot_round = round_number - 1

    # --- fixture ---
    match_date = fixture_row["match_date"]
    if isinstance(match_date, pd.Timestamp):
        match_date_str = match_date.isoformat()
    elif isinstance(match_date, datetime):
        match_date_str = match_date.isoformat()
    else:
        match_date_str = str(match_date) + "T00:00:00Z"

    fixture = {
        "fixture_id": str(fixture_row["fotmob_match_id"]),
        "competition": "Premier League",
        "season": "2025/26",
        "round_number": round_number,
        "match_date": match_date_str,
        "home_team": str(fixture_row["home_team_name"]),
        "away_team": str(fixture_row["away_team_name"]),
    }

    # --- inputs.deterministic ---
    if team_states:
        ts_home = team_states.get("home", {})
        ts_away = team_states.get("away", {})
    else:
        ts_home = _extract_team_state_from_row(fixture_row, "home")
        ts_away = _extract_team_state_from_row(fixture_row, "away")

    deterministic = {
        "team_states": {
            "snapshot_round": snapshot_round,
            "home": ts_home,
            "away": ts_away,
        },
        "h2h": None,
        "key_players": None,
        "injuries": None,
    }

    # --- inputs.non_deterministic ---
    if elo_info:
        elo_block = elo_info
    else:
        elo_block = _build_elo_block(fixture_row)

    non_deterministic = {
        "elo": elo_block,
        "odds": None,
    }

    # --- inputs.unavailable ---
    unavailable = [
        {"field": "h2h", "reason": "deferred_to_v1_1"},
        {"field": "key_players", "reason": "deferred_to_v1_1"},
        {"field": "injuries", "reason": "deferred_to_v1_1"},
        {"field": "odds", "reason": "no_source_integrated_in_analysis_dossier_v1"},
        {"field": "press_conference_quotes", "reason": "not_collected_in_v1"},
        {"field": "probable_lineups", "reason": "no_provider_integrated"},
    ]

    # --- derived.features ---
    raw_features = audit_result["raw_features"]
    features = []
    for name in model_config.FEATURE_COLS:
        source = _FEATURE_SOURCES.get(name, f"team_states.round_{snapshot_round}")
        val = raw_features.get(name)
        features.append({
            "name": name,
            "value": val,
            "source": source if name != "elo_delta" else f"clubelo@{_elo_date_str(fixture_row)}",
        })

    # --- derived.scaling ---
    scaling_params = audit_result["scaling_params"]
    scaled_features = audit_result["scaled_features"]
    scaling = []
    for name in model_config.FEATURE_COLS:
        sp = scaling_params.get(name, {})
        scaling.append({
            "feature": name,
            "mean": sp.get("mean", 0.0),
            "scale": sp.get("scale", 1.0),
            "scaled_value": scaled_features.get(name),
        })

    # --- ml ---
    report_pred = ml_report["prediction"]
    ml_block = {
        "model": {
            "name": "logistic_regression_multinomial",
            "version": model_config.MODEL_VERSION,
            "feature_subset": "COMPACT_CORE",
            "C": model_config.C,
            "random_state": model_config.RANDOM_STATE,
        },
        "probabilities": {
            "home_win": ml_report["probabilities"]["home_win"],
            "draw": ml_report["probabilities"]["draw"],
            "away_win": ml_report["probabilities"]["away_win"],
        },
        "prediction": {
            "predicted_result": report_pred["predicted_result"],
            "confidence_label": report_pred["confidence"],
        },
        "signals": {
            "p_max": report_pred["p_max"],
            "margin_top2": report_pred["margin_top2"],
            "entropy_norm": report_pred["entropy_norm"],
        },
        "drivers": audit_result["drivers_directional"],
        "risk_flags": ml_report["risk_flags"],
        "training_context": {
            "train_size": audit_result["train_size"],
            "train_rounds": audit_result["train_rounds"],
        },
    }

    # --- validation_checks ---
    probs = ml_block["probabilities"]
    prob_sum = probs["home_win"] + probs["draw"] + probs["away_win"]
    prob_map = {"H": probs["home_win"], "D": probs["draw"], "A": probs["away_win"]}
    argmax_cls = max(prob_map, key=prob_map.get)

    checks = [
        {
            "name": "prob_sum",
            "status": "pass" if abs(prob_sum - 1.0) < 0.02 else "fail",
            "details": f"{prob_sum:.4f}",
        },
        {
            "name": "argmax_matches_prediction",
            "status": "pass" if argmax_cls == ml_block["prediction"]["predicted_result"] else "fail",
            "details": argmax_cls,
        },
        {
            "name": "team_state_snapshot_round",
            "status": "pass",
            "details": f"used round {snapshot_round} for round {round_number} fixture",
        },
        {
            "name": "elo_available",
            "status": "pass" if not fixture_row.get("elo_missing_any", 0) else "fail",
            "details": "home+away present" if not fixture_row.get("elo_missing_any", 0) else "elo missing",
        },
        {
            "name": "training_size_minimum",
            "status": "pass" if audit_result["train_size"] >= 60 else "warn",
            "details": f"{audit_result['train_size']} >= 60" if audit_result["train_size"] >= 60 else f"{audit_result['train_size']} < 60",
        },
        {
            "name": "h2h_available",
            "status": "warn",
            "details": "deferred_to_v1_1",
        },
        {
            "name": "odds_available",
            "status": "warn",
            "details": "not integrated in dossier v1",
        },
    ]

    # --- provenance ---
    now = datetime.now(timezone.utc).isoformat()
    det_sources = ["postgres.fotmob_matches", "postgres.team_states"]
    non_det_sources = []
    if elo_block is not None:
        non_det_sources.append("clubelo_cache")

    provenance = {
        "run_id": run_id,
        "created_at": now,
        "facts_hash": "",  # placeholder for self-hash
        "data_snapshot_round": snapshot_round,
        "deterministic_sources": det_sources,
        "non_deterministic_sources": non_det_sources,
    }

    # --- assemble ---
    facts = {
        "schema_version": "1.0",
        "fixture": fixture,
        "inputs": {
            "deterministic": deterministic,
            "non_deterministic": non_deterministic,
            "unavailable": unavailable,
        },
        "derived": {
            "features": features,
            "scaling": scaling,
        },
        "ml": ml_block,
        "validation_checks": checks,
        "provenance": provenance,
    }

    # Self-hash
    facts["provenance"]["facts_hash"] = compute_hash(
        facts, self_hash_path=["provenance", "facts_hash"]
    )

    return facts


def _extract_team_state_from_row(row: pd.Series, side: str) -> Dict[str, Any]:
    """Extract team state fields from the DataFrame row (best-effort from available columns)."""
    prefix = "home" if side == "home" else "away"
    state = {}

    col_map = {
        "position": f"{prefix}_position",
        "goal_difference": f"{prefix}_goal_diff",
        "form_points": f"{prefix}_form_points",
        "xg_for_last5": f"{prefix}_xg_for_last5",
        "xg_against_last5": f"{prefix}_xg_against_last5",
        "xg_diff_last5": f"{prefix}_xg_diff_last5",
    }

    if side == "home":
        col_map["home_points"] = "home_venue_points"
    else:
        col_map["away_points"] = "away_venue_points"

    for key, col in col_map.items():
        val = row.get(col)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            state[key] = _safe_numeric(val)

    return state


def _build_elo_block(row: pd.Series) -> Optional[Dict[str, Any]]:
    """Build ELO info block from DataFrame row."""
    elo_missing = bool(row.get("elo_missing_any", 0))

    match_date = row["match_date"]
    if isinstance(match_date, pd.Timestamp):
        elo_date = (match_date - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        elo_date = str(match_date)[:10]

    # We can infer individual ELOs from the delta + one side if needed,
    # but the DataFrame doesn't always carry them. If home_elo/away_elo
    # columns exist, use them; otherwise mark as null.
    home_elo = row.get("home_elo")
    away_elo = row.get("away_elo")
    if home_elo is not None and not pd.isna(home_elo):
        home_elo = round(float(home_elo), 1)
    else:
        home_elo = None
    if away_elo is not None and not pd.isna(away_elo):
        away_elo = round(float(away_elo), 1)
    else:
        away_elo = None

    return {
        "pre_match_elo_date": elo_date,
        "home": home_elo,
        "away": away_elo,
        "source": "ClubELO",
        "cache_hit": True,
    }


def _elo_date_str(row: pd.Series) -> str:
    """Get ELO pre-match date string."""
    match_date = row["match_date"]
    if isinstance(match_date, pd.Timestamp):
        return (match_date - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return str(match_date)[:10]


def _safe_numeric(val: Any) -> Any:
    """Convert numpy/pandas numeric to Python native."""
    if hasattr(val, "item"):
        return val.item()
    return val
