"""
Daily Board — aggregates all matches in a round into board.json.

Walks round_dir/matches/*, loads cached JSON artifacts, classifies each
match into a board category, and writes a sorted board.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from intelligence.board_classifier import BoardEntry, classify_board_category
from intelligence.decision_engine import make_decision


_CATEGORY_ORDER = ["TOP_ANGLE", "LIVE_DOG", "TRAP_SPOT", "TOO_THIN"]


def _load_json(path: Path) -> Dict[str, Any] | None:
    """Load a JSON file, return None if missing."""
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _reconstruct_decision(
    match_dir: Path,
    ml_anchor: Dict[str, Any],
    signals: Dict[str, Any],
    mi_result: Dict[str, Any],
    report: Dict[str, Any],
) -> Dict[str, Any]:
    """Get decision dict — from MI result, evaluation_record, or reconstruct."""
    # 1. Decision already embedded in MI result
    if mi_result.get("decision"):
        return mi_result["decision"]

    # 2. From evaluation_record.json
    eval_record = _load_json(match_dir / "evaluation_record.json")
    if eval_record and eval_record.get("decision"):
        return eval_record["decision"]

    # 3. Reconstruct from raw data (no LLM needed)
    from evaluation.rubric import compute_confidence_level
    from evaluation.data_quality import DataQualityResult

    confidence_level = mi_result.get("confidence", "Medium")

    # Build a minimal DQ result for make_decision
    class _MinimalDQ:
        score = mi_result.get("integrity_score", 80.0)
        integrity_score = score

    # Build market odds from report
    market_odds = None
    report_fixture = report.get("fixture", {})
    facts = _load_json(match_dir / "facts.json")
    if facts and facts.get("market_odds"):
        market_odds = facts["market_odds"]

    # Load tactical rubric
    tactical_rubric = _load_json(match_dir / "tactical_rubric.json") or {}

    lean_text = mi_result.get("lean", "")
    home = report_fixture.get("home_team", "")
    away = report_fixture.get("away_team", "")

    decision = make_decision(
        ml_anchor, confidence_level, _MinimalDQ(),
        signals, tactical_rubric, market_odds,
        lean_text=lean_text, home_team=home, away_team=away,
    )
    return decision.to_dict()


def build_daily_board(round_dir: Path) -> Dict[str, Any]:
    """
    Build board.json from all match artifacts in a round directory.

    Expects round_dir/matches/*/  with:
      - match_intelligence.json
      - match_signals.json
      - ml_anchor.json
      - report.json
    """
    matches_dir = round_dir / "matches"
    if not matches_dir.exists():
        return {"error": "No matches directory found", "board": []}

    # Load round config for metadata
    config = _load_json(round_dir / "config.json") or {}
    league = config.get("league", "")
    round_number = config.get("round_number", 0)

    entries: List[BoardEntry] = []
    llm_trace_sample: Dict[str, Any] = {}  # capture from first MI for provenance

    for match_dir in sorted(matches_dir.iterdir()):
        if not match_dir.is_dir():
            continue

        # Load required artifacts
        mi_result = _load_json(match_dir / "match_intelligence.json")
        if mi_result is None:
            continue

        # Skip matches where MI was skipped
        mi_status = mi_result.get("mi_status", "")
        if mi_status in ("skip", "skipped"):
            continue

        # Capture LLM trace from first successful MI
        if not llm_trace_sample and mi_result.get("llm_trace"):
            llm_trace_sample = mi_result["llm_trace"]

        signals = _load_json(match_dir / "match_signals.json") or {"signals": {}}
        ml_anchor = _load_json(match_dir / "ml_anchor.json") or {}
        report = _load_json(match_dir / "report.json") or {}

        # Reconstruct decision
        decision = _reconstruct_decision(
            match_dir, ml_anchor, signals, mi_result, report,
        )

        # Enrich MI result with fixture info from report if missing
        if not mi_result.get("home_team"):
            fixture = report.get("fixture", {})
            mi_result["home_team"] = fixture.get("home_team", match_dir.name)
            mi_result["away_team"] = fixture.get("away_team", "")
            mi_result["match_id"] = fixture.get("fixture_id", "")
            mi_result["fixture"] = fixture

        entry = classify_board_category(decision, signals, ml_anchor, mi_result)
        entries.append(entry)

    # Sort: category order first, then clarity_score desc
    entries.sort(
        key=lambda e: (_CATEGORY_ORDER.index(e.category), -e.clarity_score),
    )

    actionable = sum(1 for e in entries if e.category in ("TOP_ANGLE", "LIVE_DOG"))

    board = {
        "schema_version": "1.0",
        "league": league,
        "round_number": round_number,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matches_analyzed": len(entries),
        "actionable_angles": actionable,
        "board": [e.to_dict() for e in entries],
        "llm_trace": llm_trace_sample,
    }

    # Write board.json
    with open(round_dir / "board.json", "w") as f:
        json.dump(board, f, indent=2, ensure_ascii=False)

    return board
