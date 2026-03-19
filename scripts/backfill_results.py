#!/usr/bin/env python3
"""
Backfill Results — fill actual results into evaluation_record.json files.

v1.7: Extracts actual match facts, runs post-match rubric scoring with
decision quality, and prints round summary.

Usage:
    python scripts/backfill_results.py PL_R28
    python scripts/backfill_results.py PL_R28 --league-id 47
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from evaluation.rubric import score_post_match_rubric


def _load_results(league_id: int, round_number: int) -> dict:
    """Load actual results from DB. Returns {fixture_id: result_dict}."""
    from database.config import get_connection

    sql = """
    SELECT
        provider_match_id,
        home_team_name,
        away_team_name,
        home_score,
        away_score,
        status,
        stats,
        events
    FROM provider_matches
    WHERE round_number = %(rn)s AND league_id = %(lid)s AND status = 'finished'
    """
    conn = get_connection()
    try:
        import pandas as pd
        df = pd.read_sql(sql, conn, params={"lid": league_id, "rn": round_number})
    finally:
        conn.close()

    results = {}
    for _, row in df.iterrows():
        try:
            hs = int(row["home_score"]) if row["home_score"] is not None and not (isinstance(row["home_score"], float) and row["home_score"] != row["home_score"]) else None
            aws = int(row["away_score"]) if row["away_score"] is not None and not (isinstance(row["away_score"], float) and row["away_score"] != row["away_score"]) else None
        except (ValueError, TypeError):
            continue

        if hs is None or aws is None:
            continue

        if hs > aws:
            actual = "H"
        elif hs < aws:
            actual = "A"
        else:
            actual = "D"

        # Extract actual facts from stats/events
        facts = extract_actual_facts(
            row["provider_match_id"], hs, aws, actual,
            row.get("stats"), row.get("events"),
        )

        results[str(row["provider_match_id"])] = {
            "actual_result": actual,
            "home_score": hs,
            "away_score": aws,
            "home_team": row["home_team_name"],
            "away_team": row["away_team_name"],
            **facts,
        }

    return results


def extract_actual_facts(
    match_id, home_score: int, away_score: int, actual_result: str,
    stats_json=None, events_json=None,
) -> dict:
    """Extract simple post-match facts from DB data."""
    facts = {
        "first_goal_team": None,
        "possession_winner": "even",
        "actual_home_xg": None,
        "actual_away_xg": None,
        "goals_by_phase": {"0_30": 0, "30_60": 0, "60_90": 0},
        "game_character": "tight" if home_score + away_score < 3 else "open",
    }

    # Parse stats for xG and possession
    if stats_json:
        stats = stats_json if isinstance(stats_json, (list, dict)) else _safe_json(stats_json)
        if stats:
            parsed = _parse_match_stats(stats)
            if parsed.get("xg_home") is not None:
                facts["actual_home_xg"] = parsed["xg_home"]
            if parsed.get("xg_away") is not None:
                facts["actual_away_xg"] = parsed["xg_away"]
            poss_h = parsed.get("possession_home")
            poss_a = parsed.get("possession_away")
            if poss_h is not None and poss_a is not None:
                if poss_h > poss_a + 3:
                    facts["possession_winner"] = "home"
                elif poss_a > poss_h + 3:
                    facts["possession_winner"] = "away"

    # Parse events for first goal and goal phases
    if events_json:
        events = events_json if isinstance(events_json, list) else _safe_json(events_json)
        if isinstance(events, list):
            goals = _extract_goals(events)
            if goals:
                facts["first_goal_team"] = goals[0]["team"]
                for g in goals:
                    minute = g.get("minute", 0)
                    if minute <= 30:
                        facts["goals_by_phase"]["0_30"] += 1
                    elif minute <= 60:
                        facts["goals_by_phase"]["30_60"] += 1
                    else:
                        facts["goals_by_phase"]["60_90"] += 1

    return facts


def _safe_json(val):
    """Safely parse JSON string."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return None


def _parse_match_stats(stats) -> dict:
    """Parse stats JSON for xG and possession (handles both list and dict formats)."""
    result = {"xg_home": None, "xg_away": None, "possession_home": None, "possession_away": None}

    # Normalize to list of categories
    categories = []
    if isinstance(stats, list):
        categories = stats
    elif isinstance(stats, dict):
        periods = stats.get("Periods", {})
        all_period = periods.get("All", {})
        categories = all_period.get("stats", [])

    # Build flat lookup
    for category in categories:
        if not isinstance(category, dict):
            continue
        for stat in category.get("stats", []):
            if not isinstance(stat, dict):
                continue
            key = stat.get("key")
            vals = stat.get("stats", [])
            if key and isinstance(vals, list) and len(vals) >= 2:
                try:
                    if key == "expected_goals":
                        result["xg_home"] = float(vals[0])
                        result["xg_away"] = float(vals[1])
                    elif key == "BallPossesion":
                        result["possession_home"] = float(vals[0])
                        result["possession_away"] = float(vals[1])
                except (ValueError, TypeError):
                    pass

    return result


def _extract_goals(events: list) -> list:
    """Extract goal events with minute and team side."""
    goals = []
    for event in events:
        if not isinstance(event, dict):
            continue
        # provider events have type "Goal" or similar
        event_type = event.get("type", "")
        if "Goal" in str(event_type) or event.get("isGoal"):
            minute = event.get("time", event.get("minute", 0))
            if isinstance(minute, str):
                minute = int(re.findall(r"\d+", minute)[0]) if re.findall(r"\d+", minute) else 0
            team = "home" if event.get("isHome", True) else "away"
            goals.append({"minute": minute, "team": team})
    return sorted(goals, key=lambda x: x["minute"])


def _score_decision_quality(
    decision: Optional[dict], actual_result: str,
) -> float:
    """Score decision quality: PICK + right = 100, PICK + wrong = 0, NO_BET = 50."""
    if not decision:
        return 50.0

    action = decision.get("action", "NO_BET")
    direction = decision.get("direction")

    correct = (direction == actual_result) if direction else False

    if action == "PICK":
        return 100.0 if correct else 0.0
    if action == "LEAN":
        return 80.0 if correct else 20.0
    if action == "WATCHLIST":
        return 50.0  # neutral — we didn't commit
    # NO_BET
    return 50.0


def backfill_round(round_label: str, league_id: int = 47) -> None:
    """
    Backfill results for a round.

    round_label: e.g. "PL_R28"
    """
    match = re.match(r"([A-Z]+)_R(\d+)", round_label)
    if not match:
        print(f"Invalid round label: {round_label} (expected format: PL_R28)")
        return

    league = match.group(1)
    round_number = int(match.group(2))

    round_path = PROJECT_ROOT / "output" / "rounds" / round_label / "matches"
    if not round_path.exists():
        print(f"Round directory not found: {round_path}")
        return

    # Load results from DB
    print(f"Loading results for {round_label} (league_id={league_id})...")
    try:
        results = _load_results(league_id, round_number)
    except Exception as e:
        print(f"Failed to load results: {e}")
        return

    print(f"  Found {len(results)} completed matches")

    if not results:
        print("  No completed matches to backfill")
        return

    # Summary accumulators
    total = 0
    direction_correct = 0
    total_post_score = 0.0
    confidence_scores = []
    game_char_correct = 0
    decision_counts = {"PICK": [0, 0], "LEAN": [0, 0], "WATCHLIST": [0, 0], "NO_BET": [0, 0]}

    # Process each match folder
    filled = 0
    for match_dir in sorted(round_path.iterdir()):
        if not match_dir.is_dir():
            continue

        eval_path = match_dir / "evaluation_record.json"
        if not eval_path.exists():
            continue

        eval_record = json.loads(eval_path.read_text())
        match_id = str(eval_record.get("match_id", ""))

        if match_id not in results:
            print(f"  {match_dir.name}: no result found")
            continue

        result_data = results[match_id]

        # Skip if already backfilled
        if eval_record.get("result") is not None:
            print(f"  {match_dir.name}: already has result")
            continue

        # Fill result
        eval_record["result"] = result_data
        eval_record["result_added_at"] = datetime.utcnow().isoformat() + "Z"

        # Run post-match rubric
        intel_path = match_dir / "match_intelligence.json"
        if intel_path.exists():
            intelligence = json.loads(intel_path.read_text())

            # Score decision quality
            decision = intelligence.get("decision")
            decision_score = _score_decision_quality(decision, result_data["actual_result"])
            result_data["decision_quality"] = decision_score

            post_rubric = score_post_match_rubric(intelligence, result_data)
            eval_record["post_match_rubric"] = post_rubric.to_dict()

            # Accumulate summary stats
            total += 1
            lean_dir = eval_record.get("post_match_rubric", {}).get("details", {}).get("lean_direction")
            if lean_dir == result_data["actual_result"]:
                direction_correct += 1
            total_post_score += post_rubric.score
            confidence_scores.append(post_rubric.confidence_calibration)

            # Game character
            mi_game_char = _infer_game_character(intelligence)
            actual_game_char = result_data.get("game_character")
            if mi_game_char and actual_game_char and mi_game_char == actual_game_char:
                game_char_correct += 1

            # Decision tracking
            if decision:
                action = decision.get("action", "NO_BET")
                direction = decision.get("direction")
                correct = (direction == result_data["actual_result"]) if direction else False
                if action in decision_counts:
                    decision_counts[action][0] += 1  # total
                    if correct:
                        decision_counts[action][1] += 1  # correct

            print(
                f"  {match_dir.name}: {result_data['actual_result']} "
                f"(post-match: {post_rubric.score:.1f}"
                f", decision: {decision.get('action', '?') if decision else 'N/A'})"
            )
        else:
            print(f"  {match_dir.name}: {result_data['actual_result']} (no intelligence)")

        # Write back
        eval_path.write_text(
            json.dumps(eval_record, indent=2, ensure_ascii=False, default=str)
        )

        # Resolve prediction record if it exists
        pred_path = match_dir / "prediction_record.json"
        if pred_path.exists():
            from evaluation.prediction_tracker import resolve_prediction
            pred_rec = json.loads(pred_path.read_text())
            pred_rec = resolve_prediction(
                pred_rec,
                result_data["actual_result"],
                result_data["home_score"],
                result_data["away_score"],
            )
            pred_path.write_text(
                json.dumps(pred_rec, indent=2, ensure_ascii=False, default=str)
            )

        filled += 1

    print(f"\nBackfilled {filled} matches")

    # Build track record for this round
    if filled > 0:
        from evaluation.prediction_tracker import build_round_track_record
        track = build_round_track_record(round_path.parent)
        track_path = round_path.parent / "track_record.json"
        track_path.write_text(
            json.dumps(track, indent=2, ensure_ascii=False, default=str)
        )
        _print_pnl_summary(track)

    # Print round summary
    if total > 0:
        print(f"\n{round_label} Post-Match Summary:")
        print(f"  Direction accuracy: {direction_correct}/{total} ({direction_correct/total*100:.0f}%)")
        print(f"  Avg post-match score: {total_post_score/total:.1f}/100")
        if confidence_scores:
            avg_conf = sum(confidence_scores) / len(confidence_scores)
            print(f"  Confidence calibration: {avg_conf:.0f}/100")
        print(f"  Game character accuracy: {game_char_correct}/{total} ({game_char_correct/total*100:.0f}%)")

        # Decision summary
        parts = []
        for action in ("PICK", "LEAN", "WATCHLIST", "NO_BET"):
            t, c = decision_counts[action]
            if t > 0:
                parts.append(f"{action}: {c}/{t} correct")
        if parts:
            print(f"  Decisions: {' | '.join(parts)}")


def _infer_game_character(intelligence: dict) -> Optional[str]:
    """Infer predicted game character from MI."""
    scenarios = intelligence.get("scenarios", [])
    main_read = intelligence.get("main_read", "").lower()

    # Look for open/tight language
    open_words = ["open", "goals", "attacking", "high-scoring"]
    tight_words = ["tight", "low-scoring", "defensive", "cagey", "close"]

    open_score = sum(1 for w in open_words if w in main_read)
    tight_score = sum(1 for w in tight_words if w in main_read)

    if open_score > tight_score:
        return "open"
    if tight_score > open_score:
        return "tight"
    return None


def _print_pnl_summary(track: dict) -> None:
    """Print PnL summary from track record."""
    roi = track.get("roi", {})
    by_action = track.get("by_action", {})

    parts = []
    for action in ("PICK", "LEAN"):
        a = by_action.get(action, {})
        if a.get("count", 0) > 0:
            profit = a["profit"]
            sign = "+" if profit >= 0 else ""
            parts.append(f"{action} {a['correct']}/{a['count']} {sign}{profit:.2f}u")

    if parts:
        print(f"  ROI: {' | '.join(parts)}")

    staked = roi.get("total_staked", 0)
    profit = roi.get("total_profit", 0)
    roi_pct = roi.get("roi_pct")
    if staked > 0:
        sign = "+" if profit >= 0 else ""
        print(f"  Total staked: {staked:.1f}u | profit: {sign}{profit:.2f}u | ROI: {roi_pct:.1f}%")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill actual results into evaluation records")
    parser.add_argument("round", help="Round label (e.g. PL_R28)")
    parser.add_argument("--league-id", type=int, default=47, help="provider league ID")
    args = parser.parse_args()

    backfill_round(args.round, league_id=args.league_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
