#!/usr/bin/env python3
"""
Validate v1.5 as baseline — compare v1.4 vs v1.5 across all available rounds.

Outputs:
  output/validation/v15_baseline_report.html — HTML audit (3 views)
  output/validation/v15_baseline_data.json   — raw data

Usage:
    python scripts/validate_v15_baseline.py --pilot   # ~25-30 finished games
    python scripts/validate_v15_baseline.py            # all 122 games
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

OUTPUT_DIR = PROJECT_ROOT / "output" / "validation"
ROUNDS_DIR = PROJECT_ROOT / "output" / "rounds"

# League ID mapping
LEAGUE_IDS = {
    "PL": 47, "NL": 57, "PT": 61, "DE": 54,
    "FR": 53, "IT": 55, "ES": 87,
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class MatchInfo:
    match_dir: Path
    match_name: str
    round_label: str
    league: str
    league_id: int
    round_number: int
    has_v14: bool
    has_v15: bool
    has_result: bool
    fixture_id: str


@dataclass
class RoundInfo:
    label: str
    league: str
    league_id: int
    round_number: int
    path: Path
    matches: List[MatchInfo] = field(default_factory=list)
    n_finished: int = 0


@dataclass
class LeanClassification:
    direction: str       # H / D / A
    alignment: str       # clear / leaning / ambiguous
    qualifier: str       # extracted qualifier text


# ── Step 1: Discover rounds ──────────────────────────────────────────────────

def discover_rounds(round_filter: Optional[List[str]] = None) -> List[RoundInfo]:
    """Scan output/rounds/ and build RoundInfo list."""
    rounds = []
    for rdir in sorted(ROUNDS_DIR.iterdir()):
        if not rdir.is_dir():
            continue
        config_path = rdir / "round_config.json"
        if not config_path.exists():
            continue

        config = json.loads(config_path.read_text())
        label = rdir.name
        league = config.get("league", "")
        league_id = config.get("league_id", 0)
        round_number = config.get("round_number", 0)

        if round_filter and label not in round_filter:
            continue

        matches_dir = rdir / "matches"
        if not matches_dir.exists():
            continue

        ri = RoundInfo(
            label=label, league=league, league_id=league_id,
            round_number=round_number, path=rdir,
        )

        for mdir in sorted(matches_dir.iterdir()):
            if not mdir.is_dir():
                continue

            has_v14 = (mdir / "report.json").exists()
            has_v15 = (mdir / "match_intelligence.json").exists()
            has_result = False

            # Check evaluation_record for result
            eval_path = mdir / "evaluation_record.json"
            fixture_id = ""
            if eval_path.exists():
                try:
                    er = json.loads(eval_path.read_text())
                    has_result = er.get("result") is not None
                    fixture_id = str(er.get("match_id", ""))
                except Exception:
                    pass

            # Fallback: get fixture_id from report.json
            if not fixture_id and has_v14:
                try:
                    report = json.loads((mdir / "report.json").read_text())
                    fixture_id = str(report.get("fixture", {}).get("fixture_id", ""))
                except Exception:
                    pass

            mi = MatchInfo(
                match_dir=mdir, match_name=mdir.name,
                round_label=label, league=league, league_id=league_id,
                round_number=round_number, has_v14=has_v14,
                has_v15=has_v15, has_result=has_result,
                fixture_id=fixture_id,
            )
            ri.matches.append(mi)

        ri.n_finished = sum(1 for m in ri.matches if m.has_result)
        rounds.append(ri)

    return rounds


def select_pilot_rounds(rounds: List[RoundInfo], target: int = 25) -> List[RoundInfo]:
    """Select rounds with most finished matches, preferring older rounds."""
    # Filter rounds that have results from DB
    candidates = [r for r in rounds if r.n_finished > 0]
    # Sort by round_number ascending (older first)
    candidates.sort(key=lambda r: (r.round_number, r.league))

    selected = []
    total = 0
    for r in candidates:
        if total >= target:
            break
        selected.append(r)
        total += r.n_finished

    return selected


# ── Step 2: Generate v1.5 where missing ──────────────────────────────────────

def generate_v15_for_match(
    match: MatchInfo, mi_engine, mi_validator, regenerate: bool = False,
) -> bool:
    """Run v1.5 pipeline for a single match. Returns True on success."""
    from intelligence.match_pack_builder import build_match_pack, build_ml_anchor
    from intelligence.match_signals import compute_match_signals
    from evaluation.data_quality import check_match_pack_quality
    from evaluation.trace import PipelineTrace, TraceContext
    from evaluation.rubric import score_pre_match_rubric, compute_confidence_level

    mdir = match.match_dir
    report_path = mdir / "report.json"
    if not report_path.exists():
        return False

    report = json.loads(report_path.read_text())
    home = report["fixture"]["home_team"]
    away = report["fixture"]["away_team"]
    fixture_id = str(report["fixture"]["fixture_id"])
    match_date = report["fixture"].get("match_date", "")

    # Check if already exists and not regenerating
    mi_path = mdir / "match_intelligence.json"
    if mi_path.exists() and not regenerate:
        # Still regenerate evaluation_record to ensure new format
        pass
    elif not mi_path.exists() or regenerate:
        pass  # will generate below

    trace = PipelineTrace(match_id=fixture_id)
    trace.start()

    try:
        # Step 1: Build match pack (or load from cache)
        mp_path = mdir / "match_pack.json"
        if mp_path.exists() and not regenerate:
            match_pack = json.loads(mp_path.read_text())
        else:
            match_pack = build_match_pack(
                home_team=home, away_team=away,
                round_number=match.round_number, league_id=match.league_id,
                league_name=match.league, fixture_id=fixture_id,
                match_date=match_date, trace=trace,
            )
            with open(mp_path, "w") as f:
                json.dump(match_pack, f, indent=2, default=str, ensure_ascii=False)

        # Data quality
        with TraceContext(trace, "data_quality_check", "data_quality") as dq_ctx:
            dq_result = check_match_pack_quality(match_pack)
            dq_ctx.metadata = dq_result.to_dict()

        # ML anchor
        ml_anchor = build_ml_anchor(report)
        ml_path = mdir / "ml_anchor.json"
        if not ml_path.exists():
            with open(ml_path, "w") as f:
                json.dump(ml_anchor, f, indent=2, default=str)

        # Signals
        sig_path = mdir / "match_signals.json"
        if sig_path.exists() and not regenerate:
            signals = json.loads(sig_path.read_text())
        else:
            signals = compute_match_signals(match_pack, ml_anchor)
            with open(sig_path, "w") as f:
                json.dump(signals, f, indent=2, default=str)

        # Confidence level
        confidence_level = compute_confidence_level(
            ml_anchor, signals, dq_result.score,
        )

        # Generate match intelligence (LLM — cached)
        mi_result = mi_engine.generate(
            match_pack=match_pack, ml_anchor=ml_anchor,
            match_signals=signals,
            cache_path=mdir / "match_intelligence.json",
            regenerate=regenerate,
            confidence_level=confidence_level,
            data_warnings=dq_result.warnings if dq_result.warnings else None,
        )

        # Validate
        validation = mi_validator.validate(mi_result, ml_anchor)

        # Rubric
        rubric_result = score_pre_match_rubric(
            mi_result, match_pack, ml_anchor, signals, dq_result.score,
        )

        # ALWAYS rebuild evaluation_record (new format)
        from evaluation.intelligence_validator import build_evaluation_record
        trace_data = trace.to_dict()
        eval_record = build_evaluation_record(
            match_pack, ml_anchor, signals, mi_result, validation,
            rubric_result=rubric_result,
            data_quality_result=dq_result,
            trace_data=trace_data,
        )

        # Preserve existing result if present
        old_eval_path = mdir / "evaluation_record.json"
        if old_eval_path.exists():
            try:
                old_er = json.loads(old_eval_path.read_text())
                if old_er.get("result") is not None:
                    eval_record["result"] = old_er["result"]
                    eval_record["result_added_at"] = old_er.get("result_added_at")
                    eval_record["post_match_rubric"] = old_er.get("post_match_rubric")
            except Exception:
                pass

        with open(old_eval_path, "w") as f:
            json.dump(eval_record, f, indent=2, default=str, ensure_ascii=False)

        # Save trace
        with open(mdir / "trace.json", "w") as f:
            json.dump(trace_data, f, indent=2, default=str)

        return True

    except Exception as e:
        print(f"      FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


# ── Step 3: Backfill results ─────────────────────────────────────────────────

def _load_results_from_db(league_id: int, round_number: int, debug: bool = False) -> Dict[str, Dict]:
    """Load finished results from DB. Returns {fixture_id: result_dict}.

    Handles two score sources:
    1. home_score/away_score columns (populated for some matches)
    2. raw_json->'status'->>'scoreStr' fallback (e.g. "2 - 1")

    Finished statuses: 'finished', 'ft', 'aet' (after extra time).
    """
    from database.config import get_connection

    sql = """
    SELECT provider_match_id, home_team_name, away_team_name,
           home_score, away_score, status, raw_json
    FROM provider_matches
    WHERE round_number = %(rn)s AND league_id = %(lid)s
      AND status IN ('finished', 'ft', 'aet')
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, {"lid": league_id, "rn": round_number})
        rows = cur.fetchall()
        col_names = [desc[0] for desc in cur.description]
    finally:
        conn.close()

    if debug:
        print(f"    DB query: league_id={league_id}, round={round_number}")
        print(f"    Rows returned: {len(rows)}")

    results = {}
    for row in rows:
        rd = dict(zip(col_names, row))
        match_id = str(rd["provider_match_id"])
        hs = rd["home_score"]
        aws = rd["away_score"]

        # Fallback: parse scoreStr from raw_json
        if (hs is None or aws is None) and rd.get("raw_json"):
            raw = rd["raw_json"]
            if isinstance(raw, str):
                import json as _json
                try:
                    raw = _json.loads(raw)
                except Exception:
                    raw = {}
            score_str = ""
            if isinstance(raw, dict):
                score_str = raw.get("status", {}).get("scoreStr", "")
            if score_str and " - " in score_str:
                parts = score_str.split(" - ")
                try:
                    hs = int(parts[0].strip())
                    aws = int(parts[1].strip())
                except ValueError:
                    pass

        if hs is None or aws is None:
            if debug:
                print(f"    SKIP {rd['home_team_name']} vs {rd['away_team_name']}: no score (status={rd['status']})")
            continue

        hs, aws = int(hs), int(aws)
        actual = "H" if hs > aws else ("A" if hs < aws else "D")
        results[match_id] = {
            "actual_result": actual,
            "home_score": hs, "away_score": aws,
            "home_team": rd["home_team_name"],
            "away_team": rd["away_team_name"],
        }

        if debug:
            print(f"    {rd['home_team_name']} vs {rd['away_team_name']}: {hs}-{aws} ({actual})")

    return results


def load_all_results(rounds: List[RoundInfo], debug: bool = False) -> Dict[str, Dict]:
    """Load results from DB for all rounds. Returns {fixture_id: result_dict}."""
    all_results: Dict[str, Dict] = {}
    for ri in rounds:
        try:
            results = _load_results_from_db(ri.league_id, ri.round_number, debug=debug)
        except Exception as e:
            print(f"  WARNING: DB query failed for {ri.label}: {e}")
            continue

        if not results:
            print(f"  {ri.label}: no finished matches in DB (league_id={ri.league_id}, round={ri.round_number})")
            continue

        ri.n_finished = len(results)
        print(f"  {ri.label}: {len(results)} finished matches")
        all_results.update(results)

    return all_results


def backfill_all_results(rounds: List[RoundInfo], db_results: Dict[str, Dict]) -> int:
    """Backfill results into evaluation_record.json files. Returns count filled."""
    from evaluation.rubric import score_post_match_rubric

    filled = 0
    for ri in rounds:
        for match in ri.matches:
            eval_path = match.match_dir / "evaluation_record.json"
            if not eval_path.exists():
                continue

            er = json.loads(eval_path.read_text())
            mid = str(er.get("match_id", match.fixture_id))

            if mid not in db_results:
                continue

            result_data = db_results[mid]

            # Skip if already has result
            if er.get("result") is not None:
                match.has_result = True
                continue

            er["result"] = result_data
            er["result_added_at"] = datetime.now(tz=None).isoformat() + "Z"

            # Post-match rubric
            intel_path = match.match_dir / "match_intelligence.json"
            if intel_path.exists():
                intel = json.loads(intel_path.read_text())
                post_rubric = score_post_match_rubric(intel, result_data)
                er["post_match_rubric"] = post_rubric.to_dict()

            eval_path.write_text(
                json.dumps(er, indent=2, ensure_ascii=False, default=str)
            )
            match.has_result = True
            filled += 1

    return filled


# ── Step 4: Lean classification ──────────────────────────────────────────────

# Strong direction keywords
_HOME_STRONG = [
    "home control", "home dominance", "home win", "home edge",
    "home advantage", "host control", "host dominance",
]
_AWAY_STRONG = [
    "away upset", "away win", "away control", "away edge",
    "visitor", "underdog triumph",
]
_DRAW_STRONG = [
    "draw", "stalemate", "share the points", "share points",
    "goalless", "even contest",
]

# Hedge words that downgrade "clear" → "leaning"
_HEDGE_WORDS = [
    "but", "however", "fragile", "slight", "narrow", "if", "unless",
    "edge", "marginal", "concern", "risk", "could", "might",
    "uncertain", "question", "questionable",
]


def classify_lean(lean_text: str, home_team: str = "", away_team: str = "") -> LeanClassification:
    """Classify lean into direction + alignment level."""
    if not lean_text:
        return LeanClassification("H", "ambiguous", "")

    text_lower = lean_text.lower().strip()

    # Replace team names with positional tags for keyword matching
    if home_team:
        text_lower = text_lower.replace(home_team.lower(), "home_team")
    if away_team:
        text_lower = text_lower.replace(away_team.lower(), "away_team")

    # Count direction signals
    home_hits = sum(1 for kw in _HOME_STRONG if kw in text_lower)
    away_hits = sum(1 for kw in _AWAY_STRONG if kw in text_lower)
    draw_hits = sum(1 for kw in _DRAW_STRONG if kw in text_lower)

    # Team-name-based signals (after substitution)
    if "home_team" in text_lower:
        # If home team is mentioned with positive verbs, count as home signal
        home_verbs = ["control", "dominat", "edge", "win", "prevail", "advantage"]
        for v in home_verbs:
            if v in text_lower:
                home_hits += 1
    if "away_team" in text_lower:
        away_verbs = ["control", "dominat", "edge", "win", "prevail", "advantage", "upset"]
        for v in away_verbs:
            if v in text_lower:
                away_hits += 1

    # Also count softer directional words
    home_words = ["home", "host", "favourite", "favorite", "dominat"]
    away_words = ["away", "upset", "underdog", "visitor"]
    draw_words = ["draw", "stalemate", "even", "balanced", "tight", "share"]

    home_soft = sum(1 for w in home_words if w in text_lower)
    away_soft = sum(1 for w in away_words if w in text_lower)
    draw_soft = sum(1 for w in draw_words if w in text_lower)

    # Determine direction
    scores = {"H": home_hits * 2 + home_soft, "A": away_hits * 2 + away_soft, "D": draw_hits * 2 + draw_soft}
    direction = max(scores, key=scores.get)

    # If no signal, default to H (first-mentioned team)
    total_signal = sum(scores.values())
    if total_signal == 0:
        direction = "H"

    # Check for hedge words
    hedge_count = sum(1 for hw in _HEDGE_WORDS if hw in text_lower)

    # Check for contradictory signals
    active_dirs = sum(1 for v in scores.values() if v > 0)

    # Classify alignment
    if active_dirs >= 2 and scores[direction] - sorted(scores.values())[-2] <= 1:
        alignment = "ambiguous"
    elif total_signal == 0:
        alignment = "ambiguous"
    elif hedge_count >= 2:
        alignment = "leaning"
    elif scores[direction] >= 2 and hedge_count == 0:
        alignment = "clear"
    elif scores[direction] >= 1 and hedge_count <= 1:
        alignment = "leaning"
    else:
        alignment = "ambiguous"

    # Extract qualifier (first ~80 chars)
    qualifier = lean_text[:80].strip()

    return LeanClassification(direction=direction, alignment=alignment, qualifier=qualifier)


def _is_generic_lean(lean_text: str) -> bool:
    """Check if a lean is too generic to be useful."""
    generic = {"home win", "away win", "draw", "home", "away"}
    return lean_text.lower().strip() in generic or len(lean_text.strip()) < 15


# ── Step 5: Collect match metrics ────────────────────────────────────────────

def collect_match_metrics(match: MatchInfo, db_results: Optional[Dict[str, Dict]] = None) -> Optional[Dict[str, Any]]:
    """Collect all metrics for a single match."""
    mdir = match.match_dir
    m: Dict[str, Any] = {
        "match_name": match.match_name,
        "round_label": match.round_label,
        "league": match.league,
        "fixture_id": match.fixture_id,
    }

    # v1.4 data from report.json
    report_path = mdir / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text())
        pred = report.get("prediction", {})
        m["v14_predicted"] = pred.get("predicted_result", "")
        m["v14_confidence"] = pred.get("confidence", "")
        m["v14_p_max"] = pred.get("p_max", 0)
        probs = report.get("probabilities", {})
        m["v14_prob_H"] = probs.get("home_win", 0)
        m["v14_prob_D"] = probs.get("draw", 0)
        m["v14_prob_A"] = probs.get("away_win", 0)
        m["home_team"] = report.get("fixture", {}).get("home_team", "")
        m["away_team"] = report.get("fixture", {}).get("away_team", "")
    else:
        return None

    # v1.5 data from evaluation_record.json
    eval_path = mdir / "evaluation_record.json"
    if eval_path.exists():
        er = json.loads(eval_path.read_text())
        intel_summary = er.get("intelligence_summary", {})
        m["v15_lean"] = intel_summary.get("lean", "")
        m["v15_confidence"] = intel_summary.get("confidence", "")
        m["v15_key_question"] = intel_summary.get("key_question", "")
        m["v15_n_evidence_for"] = intel_summary.get("n_evidence_for", 0)
        m["v15_n_evidence_against"] = intel_summary.get("n_evidence_against", 0)
        m["v15_n_scenarios"] = intel_summary.get("n_scenarios", 0)

        m["v15_validator_score"] = er.get("validator_score", 0)
        m["v15_validator_issues"] = er.get("validator_issues", [])

        rubric = er.get("rubric_score", 0)
        rubric_details = er.get("rubric_details", {})
        m["v15_rubric_score"] = rubric if isinstance(rubric, (int, float)) else 0
        m["v15_rubric_details"] = rubric_details

        dq = er.get("data_quality", {})
        m["v15_dq_score"] = dq.get("score", 100) if dq else 100
        m["v15_dq_warnings"] = dq.get("warnings", []) if dq else []

        # Result
        result = er.get("result")
        if result:
            m["actual_result"] = result.get("actual_result", "")
            m["home_score"] = result.get("home_score")
            m["away_score"] = result.get("away_score")
        else:
            m["actual_result"] = ""

        # Post-match rubric
        pm = er.get("post_match_rubric", {})
        if pm:
            m["v15_post_rubric_score"] = pm.get("score", 0)
            m["v15_scenario_hit"] = pm.get("scenario_hit", 0)
            m["v15_lean_correct_rubric"] = pm.get("lean_correct", 0)
        else:
            m["v15_post_rubric_score"] = None

        # Consistency
        cc = er.get("consistency_check", {})
        m["v15_ml_lean_alignment"] = cc.get("ml_lean_alignment", None) if cc else None
    else:
        m["v15_lean"] = ""
        m["actual_result"] = ""

    # Fallback: use DB results if eval_record didn't have them
    if not m.get("actual_result") and db_results:
        fid = match.fixture_id or m.get("fixture_id", "")
        if fid in db_results:
            rd = db_results[fid]
            m["actual_result"] = rd["actual_result"]
            m["home_score"] = rd["home_score"]
            m["away_score"] = rd["away_score"]

    # Full intelligence for detail views
    intel_path = mdir / "match_intelligence.json"
    if intel_path.exists():
        intel = json.loads(intel_path.read_text())
        m["v15_main_read"] = intel.get("main_read", "")
        m["v15_scenarios"] = intel.get("scenarios", [])
        m["v15_risks"] = intel.get("risks", [])

        # Count numbers cited in evidence
        all_ev = intel.get("evidence_for", []) + intel.get("evidence_against", [])
        numbers_cited = 0
        for e in all_ev:
            numbers_cited += len(re.findall(r"\d+\.?\d*", e.get("data", "")))
        m["v15_numbers_cited"] = numbers_cited

        # Count player names
        all_text = " ".join([
            intel.get("key_question", ""), intel.get("main_read", ""),
            intel.get("lean", ""),
        ] + [e.get("claim", "") + " " + e.get("data", "") for e in all_ev])
        name_pattern = r"[A-Z][a-zéèêëàâäùûüôöîïñ]+(?:\s+(?:de\s+)?[A-Z][a-zéèêëàâäùûüôöîïñ]+)*"
        names = re.findall(name_pattern, all_text)
        non_names = {
            "Home", "Away", "Draw", "Medium", "High", "Low", "Strong",
            "Moderate", "Weak", "Control", "Transition", "Stalemate",
            "The", "This", "That", "Most", "Score", "First",
        }
        m["v15_player_names_count"] = len({n for n in names if n not in non_names and len(n) > 3})
    else:
        m["v15_main_read"] = ""
        m["v15_numbers_cited"] = 0
        m["v15_player_names_count"] = 0

    # Lean classification
    lean_cls = classify_lean(m.get("v15_lean", ""), m.get("home_team", ""), m.get("away_team", ""))
    m["v15_lean_direction"] = lean_cls.direction
    m["v15_lean_alignment"] = lean_cls.alignment
    m["v15_lean_qualifier"] = lean_cls.qualifier
    m["v15_lean_generic"] = _is_generic_lean(m.get("v15_lean", ""))

    # v1.4 correct?
    actual = m.get("actual_result", "")
    if actual:
        m["v14_correct"] = m.get("v14_predicted", "") == actual
        m["v15_correct"] = lean_cls.direction == actual
    else:
        m["v14_correct"] = None
        m["v15_correct"] = None

    # Scenario hit check
    if actual and m.get("v15_scenarios"):
        most_likely = [s for s in m["v15_scenarios"] if s.get("likelihood") == "most likely"]
        if most_likely:
            from evaluation.rubric import _infer_lean_direction
            ml_dir = _infer_lean_direction(most_likely[0].get("description", ""))
            m["v15_scenario_hit"] = ml_dir == actual
        else:
            m["v15_scenario_hit"] = None
    else:
        m["v15_scenario_hit"] = None

    # Audit hint
    m["audit_hint"] = compute_audit_hint(m)

    return m


def compute_audit_hint(m: Dict) -> str:
    """Generate a short audit hint for quick review."""
    if m.get("v15_dq_score", 100) < 60:
        return "data_issue"
    if m.get("v15_lean_generic"):
        return "generic_read"
    if m.get("v15_lean_alignment") == "clear" and m.get("v15_correct") is False and m.get("actual_result"):
        return "lean_too_strong"
    if m.get("v15_scenario_hit") is False:
        return "scenario_miss"
    if m.get("v14_correct") and not m.get("v15_correct") and m.get("actual_result"):
        return "v14_better_direction"
    if not m.get("v14_correct") and m.get("v15_correct") and m.get("actual_result"):
        return "v15_better_read"
    if m.get("v15_lean_alignment") == "ambiguous":
        return "lean_ambiguous"
    return "ok"


# ── Step 6: Compute aggregates ───────────────────────────────────────────────

def compute_aggregates(metrics: List[Dict]) -> Dict[str, Any]:
    """Compute aggregate statistics across all matches."""
    agg: Dict[str, Any] = {}
    n = len(metrics)
    if n == 0:
        return agg

    # Matches with results
    with_results = [m for m in metrics if m.get("actual_result")]
    n_results = len(with_results)

    # Only count matches with v1.5 data for reading quality
    v15_metrics = [m for m in metrics if m.get("v15_lean")]
    n_v15 = len(v15_metrics)

    # ── Reading quality (v1.5 only) ──
    rq: Dict[str, Any] = {"n_v15": n_v15}
    rubric_scores = [m["v15_rubric_score"] for m in v15_metrics if m.get("v15_rubric_score")]
    validator_scores = [m["v15_validator_score"] for m in v15_metrics if m.get("v15_validator_score")]
    rq["rubric_pre_match_avg"] = round(_avg(rubric_scores), 1)
    rq["validator_avg"] = round(_avg(validator_scores), 1)
    rq["avg_player_names"] = round(_avg([m.get("v15_player_names_count", 0) for m in v15_metrics]), 1)
    rq["avg_numbers_cited"] = round(_avg([m.get("v15_numbers_cited", 0) for m in v15_metrics]), 1)

    # Lean distribution (only v1.5 matches)
    alignments = [m.get("v15_lean_alignment", "") for m in v15_metrics]
    rq["pct_clear_leans"] = round(100 * alignments.count("clear") / max(n_v15, 1), 1)
    rq["pct_leaning_leans"] = round(100 * alignments.count("leaning") / max(n_v15, 1), 1)
    rq["pct_ambiguous_leans"] = round(100 * alignments.count("ambiguous") / max(n_v15, 1), 1)
    rq["pct_generic_leans"] = round(100 * sum(1 for m in v15_metrics if m.get("v15_lean_generic")) / max(n_v15, 1), 1)

    # DQ warnings
    all_dq_warnings = []
    for m in v15_metrics:
        all_dq_warnings.extend(m.get("v15_dq_warnings", []))
    rq["dq_warnings_total"] = len(all_dq_warnings)
    rq["avg_dq_score"] = round(_avg([m.get("v15_dq_score", 100) for m in v15_metrics]), 1)

    # Per-league breakdown
    leagues = sorted(set(m["league"] for m in metrics))
    rq["per_league"] = {}
    for league in leagues:
        lm = [m for m in v15_metrics if m["league"] == league]
        rq["per_league"][league] = {
            "n": len(lm),
            "rubric_avg": round(_avg([m["v15_rubric_score"] for m in lm if m.get("v15_rubric_score")]), 1),
            "validator_avg": round(_avg([m["v15_validator_score"] for m in lm if m.get("v15_validator_score")]), 1),
        }

    agg["reading_quality"] = rq

    # ── Directional accuracy ──
    da: Dict[str, Any] = {}
    if n_results > 0:
        da["n_with_results"] = n_results
        da["v14_accuracy"] = round(100 * sum(1 for m in with_results if m.get("v14_correct")) / n_results, 1)
        da["v15_accuracy"] = round(100 * sum(1 for m in with_results if m.get("v15_correct")) / n_results, 1)

        # Clear-only accuracy
        clear_with_results = [m for m in with_results if m.get("v15_lean_alignment") == "clear"]
        if clear_with_results:
            da["v15_accuracy_clear_only"] = round(
                100 * sum(1 for m in clear_with_results if m.get("v15_correct")) / len(clear_with_results), 1
            )
            da["n_clear"] = len(clear_with_results)
        else:
            da["v15_accuracy_clear_only"] = None
            da["n_clear"] = 0

        # Leaning accuracy
        leaning_with_results = [m for m in with_results if m.get("v15_lean_alignment") == "leaning"]
        if leaning_with_results:
            da["v15_accuracy_leaning"] = round(
                100 * sum(1 for m in leaning_with_results if m.get("v15_correct")) / len(leaning_with_results), 1
            )
            da["n_leaning"] = len(leaning_with_results)
        else:
            da["v15_accuracy_leaning"] = None
            da["n_leaning"] = 0

        # Hit rate by confidence (5 buckets)
        conf_buckets = ["High", "Medium-High", "Medium", "Medium-Low", "Low"]
        da["hit_rate_by_confidence"] = {}
        for cb in conf_buckets:
            bucket = [m for m in with_results if m.get("v15_confidence") == cb]
            if bucket:
                da["hit_rate_by_confidence"][cb] = {
                    "n": len(bucket),
                    "accuracy": round(100 * sum(1 for m in bucket if m.get("v15_correct")) / len(bucket), 1),
                }

        # Scenario most likely hit rate
        scenario_matches = [m for m in with_results if m.get("v15_scenario_hit") is not None]
        if scenario_matches:
            da["scenario_most_likely_hit_rate"] = round(
                100 * sum(1 for m in scenario_matches if m["v15_scenario_hit"]) / len(scenario_matches), 1
            )
        else:
            da["scenario_most_likely_hit_rate"] = None

        # Divergence analysis
        divergent = [m for m in with_results if m.get("v14_predicted") != m.get("v15_lean_direction")]
        da["n_divergent"] = len(divergent)
        if divergent:
            da["divergent_v14_correct"] = sum(1 for m in divergent if m.get("v14_correct"))
            da["divergent_v15_correct"] = sum(1 for m in divergent if m.get("v15_correct"))
        else:
            da["divergent_v14_correct"] = 0
            da["divergent_v15_correct"] = 0

        # Per-league
        da["per_league"] = {}
        for league in leagues:
            lm = [m for m in with_results if m["league"] == league]
            if lm:
                da["per_league"][league] = {
                    "n": len(lm),
                    "v14_accuracy": round(100 * sum(1 for m in lm if m.get("v14_correct")) / len(lm), 1),
                    "v15_accuracy": round(100 * sum(1 for m in lm if m.get("v15_correct")) / len(lm), 1),
                }

        # Experimental: risk materialization proxy
        risk_matches = [m for m in with_results if m.get("v15_post_rubric_score") is not None]
        if risk_matches:
            da["experimental_risk_materialization_avg"] = round(
                _avg([m["v15_post_rubric_score"] for m in risk_matches]), 1
            )

    agg["directional_accuracy"] = da

    # ── Draft executive summary ──
    agg["draft_executive_summary"] = _build_draft_summary(agg, n, n_results)

    # ── Next lever ──
    agg["recommended_next_lever"] = _compute_next_lever(agg, metrics)

    return agg


def _avg(vals: list) -> float:
    nums = [v for v in vals if v is not None and isinstance(v, (int, float))]
    return sum(nums) / len(nums) if nums else 0.0


def _build_draft_summary(agg: Dict, n: int, n_results: int) -> Dict[str, Any]:
    """Build draft executive summary with explicit supporting metrics."""
    summary: Dict[str, Any] = {
        "title": "DRAFT — Executive Summary (requires human review)",
        "sample_size": n,
        "matches_with_results": n_results,
    }

    da = agg.get("directional_accuracy", {})
    rq = agg.get("reading_quality", {})

    # Question 1: Does v1.5 read games better than v1.4 predicts?
    q1: Dict[str, Any] = {"question": "Does v1.5 read games better than v1.4 predicts?"}
    v14_acc = da.get("v14_accuracy")
    v15_acc = da.get("v15_accuracy")
    if v14_acc is not None and v15_acc is not None:
        diff = v15_acc - v14_acc
        if abs(diff) < 3:
            q1["answer"] = f"Data suggests comparable performance (v1.4: {v14_acc}%, v1.5: {v15_acc}%, diff: {diff:+.1f}pp). Based on {n_results} matches."
        elif diff > 0:
            q1["answer"] = f"Data suggests v1.5 reads slightly better (v1.4: {v14_acc}%, v1.5: {v15_acc}%, diff: {diff:+.1f}pp). Based on {n_results} matches."
        else:
            q1["answer"] = f"Data suggests v1.4 predicts directionally better (v1.4: {v14_acc}%, v1.5: {v15_acc}%, diff: {diff:+.1f}pp). Based on {n_results} matches."
    else:
        q1["answer"] = "Insufficient data to compare."
    q1["supporting_metrics"] = {"v14_accuracy": v14_acc, "v15_accuracy": v15_acc, "n": n_results}
    summary["q1_direction"] = q1

    # Question 2: Is v1.5 reading quality sufficient?
    q2: Dict[str, Any] = {"question": "Is v1.5 reading quality sufficient?"}
    rubric_avg = rq.get("rubric_pre_match_avg", 0)
    validator_avg = rq.get("validator_avg", 0)
    q2["answer"] = (
        f"Rubric avg: {rubric_avg}/100, Validator avg: {validator_avg}/100. "
        f"Generic leans: {rq.get('pct_generic_leans', 0)}%, "
        f"Ambiguous leans: {rq.get('pct_ambiguous_leans', 0)}%. "
        f"Based on {n} matches."
    )
    q2["supporting_metrics"] = {
        "rubric_avg": rubric_avg, "validator_avg": validator_avg,
        "pct_generic": rq.get("pct_generic_leans"), "pct_ambiguous": rq.get("pct_ambiguous_leans"),
    }
    summary["q2_quality"] = q2

    # Question 3: Is confidence well-calibrated?
    q3: Dict[str, Any] = {"question": "Is confidence well-calibrated?"}
    cal = da.get("hit_rate_by_confidence", {})
    cal_parts = []
    for level in ["High", "Medium-High", "Medium", "Medium-Low", "Low"]:
        if level in cal:
            cal_parts.append(f"{level}: {cal[level]['accuracy']}% (n={cal[level]['n']})")
    q3["answer"] = "; ".join(cal_parts) if cal_parts else "Insufficient data."
    q3["supporting_metrics"] = cal
    summary["q3_calibration"] = q3

    # Question 4: Where should we invest next?
    q4: Dict[str, Any] = {"question": "Where should we invest next?"}
    lever = agg.get("recommended_next_lever", {})
    q4["answer"] = lever.get("rationale", "See next_lever section.")
    q4["supporting_metrics"] = lever.get("supporting_metrics", {})
    summary["q4_next_lever"] = q4

    # Confidence in conclusion
    if n_results >= 80:
        summary["confidence_in_conclusion"] = "moderate (80+ matches, but single time window)"
    elif n_results >= 40:
        summary["confidence_in_conclusion"] = "low-moderate (40-80 matches)"
    elif n_results >= 20:
        summary["confidence_in_conclusion"] = "low (20-40 matches — directional only)"
    else:
        summary["confidence_in_conclusion"] = "very low (<20 matches — not statistically meaningful)"

    return summary


def _compute_next_lever(agg: Dict, metrics: List[Dict]) -> Dict[str, Any]:
    """Compute recommended next lever with supporting metrics."""
    rq = agg.get("reading_quality", {})
    da = agg.get("directional_accuracy", {})

    avg_numbers = rq.get("avg_numbers_cited", 0)
    pct_dq_warnings = 100 * rq.get("dq_warnings_total", 0) / max(len(metrics), 1)
    pct_ambiguous = rq.get("pct_ambiguous_leans", 0)
    pct_generic = rq.get("pct_generic_leans", 0)
    v14_acc = da.get("v14_accuracy", 0)
    v15_acc_clear = da.get("v15_accuracy_clear_only", 0)

    hypotheses = []

    # Data/features lever
    data_metrics = {"avg_numbers_cited": avg_numbers, "pct_dq_warnings": round(pct_dq_warnings, 1), "avg_dq_score": rq.get("avg_dq_score")}
    if avg_numbers < 5 or pct_dq_warnings > 30:
        hypotheses.append({
            "area": "data/features",
            "rationale": f"Low data citation (avg {avg_numbers} numbers/match) or high DQ warnings ({pct_dq_warnings:.0f}%) suggest data gaps limit reading quality.",
            "supporting_metrics": data_metrics,
            "priority": 1,
        })
    else:
        hypotheses.append({
            "area": "data/features",
            "rationale": "Data foundation appears adequate but could always improve.",
            "supporting_metrics": data_metrics,
            "priority": 3,
        })

    # ML lever
    ml_metrics = {"v14_accuracy": v14_acc, "v15_accuracy_clear": v15_acc_clear}
    if v14_acc and v15_acc_clear and v14_acc > (v15_acc_clear or 0) + 5:
        hypotheses.append({
            "area": "reasoning/prompt/LLM",
            "rationale": f"ML (v1.4) outperforms clear v1.5 leans by {v14_acc - (v15_acc_clear or 0):.1f}pp, suggesting the reasoning layer degrades directional signal.",
            "supporting_metrics": ml_metrics,
            "priority": 1,
        })
    else:
        hypotheses.append({
            "area": "ML",
            "rationale": "ML anchor appears well-utilized by the reasoning layer.",
            "supporting_metrics": ml_metrics,
            "priority": 3,
        })

    # Reasoning/prompt lever
    reasoning_metrics = {"pct_ambiguous": pct_ambiguous, "pct_generic": pct_generic}
    if pct_ambiguous > 25 or pct_generic > 20:
        hypotheses.append({
            "area": "reasoning/prompt/LLM",
            "rationale": f"High ambiguous ({pct_ambiguous:.0f}%) or generic ({pct_generic:.0f}%) leans indicate the LLM often hedges instead of committing to a read.",
            "supporting_metrics": reasoning_metrics,
            "priority": 1,
        })
    else:
        hypotheses.append({
            "area": "reasoning/prompt/LLM",
            "rationale": "Lean quality appears reasonable.",
            "supporting_metrics": reasoning_metrics,
            "priority": 3,
        })

    # Calibration lever
    cal = da.get("hit_rate_by_confidence", {})
    high_acc = cal.get("High", {}).get("accuracy")
    low_acc = cal.get("Low", {}).get("accuracy")
    cal_metrics = {"high_accuracy": high_acc, "low_accuracy": low_acc}
    if high_acc is not None and low_acc is not None and low_acc > high_acc:
        hypotheses.append({
            "area": "ML thresholds",
            "rationale": f"Inverted calibration: High confidence ({high_acc}%) worse than Low ({low_acc}%). Confidence thresholds need recalibration.",
            "supporting_metrics": cal_metrics,
            "priority": 1,
        })

    # Sort by priority and pick
    hypotheses.sort(key=lambda h: h["priority"])
    recommended = hypotheses[0] if hypotheses else {"area": "unknown", "rationale": "Insufficient data"}
    alternatives = hypotheses[1:]

    return {
        "area": recommended["area"],
        "rationale": recommended["rationale"],
        "supporting_metrics": recommended.get("supporting_metrics", {}),
        "alternative_hypotheses": [
            {"area": h["area"], "rationale": h["rationale"], "supporting_metrics": h.get("supporting_metrics", {})}
            for h in alternatives
        ],
    }


# ── Step 7: Generate HTML ────────────────────────────────────────────────────

def generate_html_report(
    metrics: List[Dict], aggregates: Dict, rounds_summary: List[Dict], timestamp: str,
) -> str:
    """Generate standalone HTML audit report with 3 views."""
    da = aggregates.get("directional_accuracy", {})
    rq = aggregates.get("reading_quality", {})
    summary = aggregates.get("draft_executive_summary", {})
    lever = aggregates.get("recommended_next_lever", {})

    with_results = [m for m in metrics if m.get("actual_result")]

    # Top 10 best / worst reads
    scored = [m for m in with_results if m.get("v15_rubric_score")]
    best = sorted([m for m in scored if m.get("v15_correct")], key=lambda x: -x.get("v15_rubric_score", 0))[:10]
    worst = sorted([m for m in scored if m.get("v15_correct") is False], key=lambda x: x.get("v15_validator_score", 0))[:10]

    # Divergences
    divergent = [m for m in with_results if m.get("v14_predicted") != m.get("v15_lean_direction")]

    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>v1.5 Baseline Validation — {timestamp}</title>
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; padding: 20px; line-height: 1.5; }}
    h1 {{ font-size: 1.6em; margin-bottom: 10px; }}
    h2 {{ font-size: 1.3em; margin: 25px 0 10px; border-bottom: 2px solid #ddd; padding-bottom: 5px; }}
    h3 {{ font-size: 1.1em; margin: 15px 0 8px; }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    .nav {{ background: #2c3e50; padding: 12px 20px; border-radius: 6px; margin-bottom: 20px; }}
    .nav a {{ color: #ecf0f1; text-decoration: none; margin-right: 25px; font-weight: 500; }}
    .nav a:hover {{ color: #3498db; }}
    .card {{ background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .draft-banner {{ background: #fff3cd; border: 2px solid #ffc107; padding: 12px 20px; border-radius: 6px; margin-bottom: 16px; font-weight: bold; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.85em; }}
    th, td {{ padding: 6px 10px; border: 1px solid #ddd; text-align: left; }}
    th {{ background: #f8f9fa; font-weight: 600; position: sticky; top: 0; }}
    tr:nth-child(even) {{ background: #f9f9fa; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: 600; }}
    .badge-green {{ background: #d4edda; color: #155724; }}
    .badge-red {{ background: #f8d7da; color: #721c24; }}
    .badge-gray {{ background: #e2e3e5; color: #383d41; }}
    .badge-yellow {{ background: #fff3cd; color: #856404; }}
    .badge-blue {{ background: #cce5ff; color: #004085; }}
    .metric {{ display: inline-block; margin: 4px 8px 4px 0; padding: 4px 10px; background: #e8f4fd; border-radius: 4px; font-size: 0.9em; }}
    .metric strong {{ color: #2c3e50; }}
    details {{ margin: 4px 0; }}
    details summary {{ cursor: pointer; color: #3498db; font-size: 0.85em; }}
    details summary:hover {{ text-decoration: underline; }}
    .detail-content {{ padding: 8px; background: #f8f9fa; border-radius: 4px; margin-top: 4px; font-size: 0.85em; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    @media (max-width: 900px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
    .hint {{ font-size: 0.75em; padding: 1px 6px; border-radius: 3px; }}
    .hint-ok {{ background: #d4edda; }}
    .hint-data_issue {{ background: #f8d7da; }}
    .hint-generic_read {{ background: #fff3cd; }}
    .hint-lean_too_strong {{ background: #f8d7da; }}
    .hint-scenario_miss {{ background: #fff3cd; }}
    .hint-v14_better_direction {{ background: #f8d7da; }}
    .hint-v15_better_read {{ background: #d4edda; }}
    .hint-lean_ambiguous {{ background: #e2e3e5; }}
    .pct-bar {{ display: inline-block; height: 14px; border-radius: 3px; vertical-align: middle; }}
</style>
</head>
<body>
<div class="container">

<h1>v1.5 Baseline Validation Report</h1>
<p style="color:#666; margin-bottom:10px;">Generated: {timestamp} &middot; {len(metrics)} matches &middot; {len(with_results)} with results</p>

<nav class="nav">
    <a href="#method-view">Method View</a>
    <a href="#match-view">Match View</a>
    <a href="#diff-view">Diff View</a>
</nav>

<div class="draft-banner">
    ⚠ DRAFT — Executive Summary (requires human review)
</div>

<div class="card">
    <h3>{summary.get('q1_direction', {}).get('question', '')}</h3>
    <p>{summary.get('q1_direction', {}).get('answer', '')}</p>
    <h3 style="margin-top:12px">{summary.get('q2_quality', {}).get('question', '')}</h3>
    <p>{summary.get('q2_quality', {}).get('answer', '')}</p>
    <h3 style="margin-top:12px">{summary.get('q3_calibration', {}).get('question', '')}</h3>
    <p>{summary.get('q3_calibration', {}).get('answer', '')}</p>
    <h3 style="margin-top:12px">{summary.get('q4_next_lever', {}).get('question', '')}</h3>
    <p>{summary.get('q4_next_lever', {}).get('answer', '')}</p>
    <p style="margin-top:12px; font-style:italic; color:#666;">Confidence in conclusion: {summary.get('confidence_in_conclusion', 'unknown')}</p>
</div>

<!-- ═══════════ METHOD VIEW ═══════════ -->
<h2 id="method-view">1. Method View</h2>

<div class="grid-2">
<div class="card">
    <h3>Reading Quality (v1.5)</h3>
    <div class="metric"><strong>Rubric avg:</strong> {rq.get('rubric_pre_match_avg', 0)}/100</div>
    <div class="metric"><strong>Validator avg:</strong> {rq.get('validator_avg', 0)}/100</div>
    <div class="metric"><strong>Avg players cited:</strong> {rq.get('avg_player_names', 0)}</div>
    <div class="metric"><strong>Avg numbers cited:</strong> {rq.get('avg_numbers_cited', 0)}</div>
    <div class="metric"><strong>DQ score avg:</strong> {rq.get('avg_dq_score', 0)}/100</div>
    <div class="metric"><strong>DQ warnings:</strong> {rq.get('dq_warnings_total', 0)}</div>
    <h4 style="margin-top:12px;">Lean Distribution</h4>
    <div class="metric"><strong>Clear:</strong> {rq.get('pct_clear_leans', 0)}%</div>
    <div class="metric"><strong>Leaning:</strong> {rq.get('pct_leaning_leans', 0)}%</div>
    <div class="metric"><strong>Ambiguous:</strong> {rq.get('pct_ambiguous_leans', 0)}%</div>
    <div class="metric"><strong>Generic:</strong> {rq.get('pct_generic_leans', 0)}%</div>
</div>

<div class="card">
    <h3>Directional Accuracy</h3>
    <div class="metric"><strong>v1.4 accuracy:</strong> {da.get('v14_accuracy', 'N/A')}%</div>
    <div class="metric"><strong>v1.5 accuracy:</strong> {da.get('v15_accuracy', 'N/A')}%</div>
    <div class="metric"><strong>v1.5 clear-only:</strong> {da.get('v15_accuracy_clear_only', 'N/A')}% (n={da.get('n_clear', 0)})</div>
    <div class="metric"><strong>v1.5 leaning:</strong> {da.get('v15_accuracy_leaning', 'N/A')}% (n={da.get('n_leaning', 0)})</div>
    <div class="metric"><strong>Scenario hit rate:</strong> {da.get('scenario_most_likely_hit_rate', 'N/A')}%</div>
    <h4 style="margin-top:12px;">Divergences</h4>
    <div class="metric"><strong>Total divergent:</strong> {da.get('n_divergent', 0)}</div>
    <div class="metric"><strong>v1.4 correct (in divergent):</strong> {da.get('divergent_v14_correct', 0)}</div>
    <div class="metric"><strong>v1.5 correct (in divergent):</strong> {da.get('divergent_v15_correct', 0)}</div>
</div>
</div>

<div class="card">
    <h3>Confidence Calibration</h3>
    <table>
    <tr><th>Confidence Level</th><th>N</th><th>v1.5 Accuracy</th></tr>
    {_html_calibration_rows(da.get('hit_rate_by_confidence', {}))}
    </table>
</div>

<div class="card">
    <h3>Per-League Breakdown</h3>
    <table>
    <tr><th>League</th><th>N</th><th>v1.4 Acc</th><th>v1.5 Acc</th><th>Rubric Avg</th><th>Validator Avg</th></tr>
    {_html_league_rows(da.get('per_league', {}), rq.get('per_league', {}))}
    </table>
</div>

<div class="card">
    <h3>Recommended Next Lever (draft)</h3>
    <p><strong>Area:</strong> {lever.get('area', 'N/A')}</p>
    <p>{lever.get('rationale', '')}</p>
    <p style="margin-top:8px; font-size:0.9em; color:#666;">
        Supporting: {json.dumps(lever.get('supporting_metrics', {}), default=str)}
    </p>
    {_html_alternative_levers(lever.get('alternative_hypotheses', []))}
</div>

<!-- ═══════════ MATCH VIEW ═══════════ -->
<h2 id="match-view">2. Match View</h2>

<div class="card" style="overflow-x:auto;">
<table>
<tr>
    <th>Round</th><th>Match</th>
    <th>v1.4 Pred</th><th>v1.4 Conf</th>
    <th>v1.5 Lean</th><th>Lean Class</th><th>v1.5 Conf</th>
    <th>Rubric</th><th>Validator</th><th>DQ</th>
    <th>Actual</th><th>v1.4 ✓</th><th>v1.5 ✓</th>
    <th>Hint</th>
</tr>
{_html_match_rows(metrics)}
</table>
</div>

<!-- ═══════════ DIFF VIEW ═══════════ -->
<h2 id="diff-view">3. Diff View</h2>

<div class="card">
    <h3>Top 10 Best v1.5 Reads (high rubric + correct)</h3>
    {_html_read_table(best, "best")}
</div>

<div class="card">
    <h3>Top 10 Worst v1.5 Reads (wrong direction)</h3>
    {_html_read_table(worst, "worst")}
</div>

<div class="card">
    <h3>Divergences — v1.4 vs v1.5 disagreed</h3>
    {_html_divergence_table(divergent)}
</div>

</div><!-- container -->
</body>
</html>"""

    return html


def _html_calibration_rows(cal: Dict) -> str:
    rows = []
    for level in ["High", "Medium-High", "Medium", "Medium-Low", "Low"]:
        if level in cal:
            b = cal[level]
            rows.append(f"<tr><td>{level}</td><td>{b['n']}</td><td>{b['accuracy']}%</td></tr>")
        else:
            rows.append(f"<tr><td>{level}</td><td>0</td><td>—</td></tr>")
    return "\n".join(rows)


def _html_league_rows(da_league: Dict, rq_league: Dict) -> str:
    rows = []
    all_leagues = sorted(set(list(da_league.keys()) + list(rq_league.keys())))
    for league in all_leagues:
        d = da_league.get(league, {})
        r = rq_league.get(league, {})
        rows.append(
            f"<tr><td>{league}</td>"
            f"<td>{d.get('n', r.get('n', 0))}</td>"
            f"<td>{d.get('v14_accuracy', '—')}%</td>"
            f"<td>{d.get('v15_accuracy', '—')}%</td>"
            f"<td>{r.get('rubric_avg', '—')}</td>"
            f"<td>{r.get('validator_avg', '—')}</td></tr>"
        )
    return "\n".join(rows)


def _html_alternative_levers(alternatives: List[Dict]) -> str:
    if not alternatives:
        return ""
    html = "<h4 style='margin-top:12px;'>Alternative Hypotheses</h4><ul>"
    for a in alternatives:
        html += f"<li><strong>{a['area']}</strong>: {a['rationale']}</li>"
    html += "</ul>"
    return html


def _html_match_rows(metrics: List[Dict]) -> str:
    rows = []
    for m in metrics:
        actual = m.get("actual_result", "")
        v14_ok = m.get("v14_correct")
        v15_ok = m.get("v15_correct")

        v14_badge = _correct_badge(v14_ok)
        v15_badge = _correct_badge(v15_ok)
        actual_display = actual if actual else "—"

        alignment = m.get("v15_lean_alignment", "")
        alignment_badge = {
            "clear": '<span class="badge badge-green">CLEAR ✓</span>',
            "leaning": '<span class="badge badge-yellow">LEAN ~</span>',
            "ambiguous": '<span class="badge badge-gray">AMB ?</span>',
        }.get(alignment, "")

        hint = m.get("audit_hint", "ok")
        hint_cls = f"hint hint-{hint}"

        lean_text = _escape(m.get("v15_lean", ""))
        lean_display = lean_text[:60] + "…" if len(lean_text) > 60 else lean_text

        # Expandable detail
        detail = ""
        kq = m.get("v15_key_question", "")
        mr = m.get("v15_main_read", "")
        if kq or mr:
            detail = (
                f'<details><summary>detail</summary>'
                f'<div class="detail-content">'
                f'<strong>Key Q:</strong> {_escape(kq)}<br>'
                f'<strong>Read:</strong> {_escape(mr)}'
                f'</div></details>'
            )

        rows.append(
            f"<tr>"
            f"<td>{m.get('round_label', '')}</td>"
            f"<td>{m.get('home_team', '')} vs {m.get('away_team', '')}{detail}</td>"
            f"<td>{m.get('v14_predicted', '')}</td>"
            f"<td>{m.get('v14_confidence', '')}</td>"
            f"<td title=\"{_escape(lean_text)}\">{lean_display}</td>"
            f"<td>{alignment_badge} {m.get('v15_lean_direction', '')}</td>"
            f"<td>{m.get('v15_confidence', '')}</td>"
            f"<td>{m.get('v15_rubric_score', '—')}</td>"
            f"<td>{m.get('v15_validator_score', '—')}</td>"
            f"<td>{m.get('v15_dq_score', '—')}</td>"
            f"<td><strong>{actual_display}</strong></td>"
            f"<td>{v14_badge}</td>"
            f"<td>{v15_badge}</td>"
            f"<td><span class=\"{hint_cls}\">{hint}</span></td>"
            f"</tr>"
        )
    return "\n".join(rows)


def _correct_badge(val) -> str:
    if val is True:
        return '<span class="badge badge-green">✓</span>'
    elif val is False:
        return '<span class="badge badge-red">✗</span>'
    return '<span class="badge badge-gray">—</span>'


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _html_read_table(matches: List[Dict], kind: str) -> str:
    if not matches:
        return "<p>No matches to show.</p>"

    rows = []
    for m in matches:
        lean = _escape(m.get("v15_lean", ""))
        kq = _escape(m.get("v15_key_question", ""))
        v14_pred = m.get("v14_predicted", "")
        actual = m.get("actual_result", "")
        rubric = m.get("v15_rubric_score", "—")
        validator = m.get("v15_validator_score", "—")

        rows.append(
            f"<tr>"
            f"<td>{m.get('round_label', '')}</td>"
            f"<td>{m.get('home_team', '')} vs {m.get('away_team', '')}</td>"
            f"<td>{lean}</td>"
            f"<td>{kq}</td>"
            f"<td>{v14_pred}</td>"
            f"<td><strong>{actual}</strong></td>"
            f"<td>{rubric}</td><td>{validator}</td>"
            f"</tr>"
        )

    return (
        "<table>"
        "<tr><th>Round</th><th>Match</th><th>v1.5 Lean</th><th>Key Q</th>"
        "<th>v1.4</th><th>Actual</th><th>Rubric</th><th>Validator</th></tr>"
        + "\n".join(rows)
        + "</table>"
    )


def _html_divergence_table(divergent: List[Dict]) -> str:
    if not divergent:
        return "<p>No divergences found.</p>"

    rows = []
    for m in divergent:
        v14_ok = _correct_badge(m.get("v14_correct"))
        v15_ok = _correct_badge(m.get("v15_correct"))
        rows.append(
            f"<tr>"
            f"<td>{m.get('round_label', '')}</td>"
            f"<td>{m.get('home_team', '')} vs {m.get('away_team', '')}</td>"
            f"<td>{m.get('v14_predicted', '')}</td>"
            f"<td>{m.get('v15_lean_direction', '')} ({m.get('v15_lean_alignment', '')})</td>"
            f"<td><strong>{m.get('actual_result', '')}</strong></td>"
            f"<td>{v14_ok}</td>"
            f"<td>{v15_ok}</td>"
            f"<td><span class=\"hint hint-{m.get('audit_hint', 'ok')}\">{m.get('audit_hint', 'ok')}</span></td>"
            f"</tr>"
        )

    return (
        "<table>"
        "<tr><th>Round</th><th>Match</th><th>v1.4 Pred</th><th>v1.5 Lean</th>"
        "<th>Actual</th><th>v1.4 ✓</th><th>v1.5 ✓</th><th>Hint</th></tr>"
        + "\n".join(rows)
        + "</table>"
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate v1.5 as baseline")
    parser.add_argument("--pilot", action="store_true", help="Pilot mode: ~25-30 finished games")
    parser.add_argument("--rounds", nargs="+", help="Specific round labels (e.g. PL_R30 NL_R27)")
    parser.add_argument("--regenerate", action="store_true", help="Force regenerate v1.5 artefacts")
    parser.add_argument("--skip-generate", action="store_true", help="Skip v1.5 generation, use existing")
    parser.add_argument("--mi-model", default="gpt-4o", help="LLM model (default: gpt-4o)")
    parser.add_argument("--debug", action="store_true", help="Print DB queries and debug info")
    args = parser.parse_args()

    timestamp = datetime.now(tz=None).strftime("%Y-%m-%d %H:%M UTC")
    print(f"v1.5 Baseline Validation — {timestamp}")
    print("=" * 60)

    # Step 1: Discover
    print("\n[1/6] Discovering rounds...")
    round_filter = args.rounds if args.rounds else None
    all_rounds = discover_rounds(round_filter=round_filter)
    total_matches = sum(len(r.matches) for r in all_rounds)
    print(f"  Found {len(all_rounds)} rounds, {total_matches} matches")

    for r in all_rounds:
        v15_count = sum(1 for m in r.matches if m.has_v15)
        result_count = sum(1 for m in r.matches if m.has_result)
        print(f"  {r.label}: {len(r.matches)} matches, {v15_count} with v1.5, {result_count} with results (eval_record)")

    if not all_rounds:
        if round_filter:
            print(f"\n  ERROR: No rounds found matching {round_filter}")
            print(f"  Available: {[d.name for d in ROUNDS_DIR.iterdir() if d.is_dir()]}")
        return 1

    # For pilot mode, query DB first to find which rounds have results
    if args.pilot:
        print("\n  Querying DB for finished rounds...")
        db_available = False
        for r in all_rounds:
            try:
                results = _load_results_from_db(r.league_id, r.round_number, debug=args.debug)
                r.n_finished = len(results)
                db_available = True
                status = f"{len(results)} finished" if results else "no results"
                print(f"    {r.label}: {status}")
            except Exception as e:
                print(f"    {r.label}: DB error — {e}")

        if not db_available:
            print("\n  ERROR: DB unavailable — cannot auto-select pilot rounds.")
            print("  Use --rounds PL_R30 NL_R27 to select manually.")
            return 1

        rounds = select_pilot_rounds(all_rounds, target=25)
        if not rounds:
            print("\n  ERROR: No rounds with finished results found in DB.")
            print("  Available rounds with results:")
            for r in all_rounds:
                if r.n_finished > 0:
                    print(f"    {r.label}: {r.n_finished} finished")
            print("  Use --rounds to select manually.")
            return 1

        n_pilot = sum(len(r.matches) for r in rounds)
        n_finished = sum(r.n_finished for r in rounds)
        print(f"\n  PILOT MODE: selected {len(rounds)} rounds, {n_pilot} matches, {n_finished} with results")
    else:
        rounds = all_rounds

    # Step 2: Generate v1.5 where missing
    if not args.skip_generate:
        print("\n[2/6] Generating v1.5 where missing...")
        from intelligence.match_intelligence import MatchIntelligenceEngine
        from evaluation.intelligence_validator import IntelligenceValidator

        mi_engine = MatchIntelligenceEngine(model=args.mi_model)
        mi_validator = IntelligenceValidator()

        generated = 0
        skipped = 0
        failed = 0
        for ri in rounds:
            for match in ri.matches:
                if not match.has_v14:
                    continue
                if match.has_v15 and not args.regenerate:
                    # Still ensure evaluation_record is in new format
                    eval_path = match.match_dir / "evaluation_record.json"
                    if eval_path.exists():
                        er = json.loads(eval_path.read_text())
                        if er.get("schema_version") == "1.5":
                            skipped += 1
                            continue

                print(f"  {match.round_label}/{match.match_name}...", end=" ", flush=True)
                ok = generate_v15_for_match(match, mi_engine, mi_validator, regenerate=args.regenerate)
                if ok:
                    match.has_v15 = True
                    generated += 1
                    print("OK")
                else:
                    failed += 1
                    print("FAIL")

        print(f"  Generated: {generated}, Skipped: {skipped}, Failed: {failed}")
    else:
        print("\n[2/6] Skipping v1.5 generation (--skip-generate)")

    # Step 3: Load results from DB + backfill into eval records
    print("\n[3/6] Loading results from DB...")
    db_results: Dict[str, Dict] = {}
    try:
        db_results = load_all_results(rounds, debug=args.debug)
        print(f"  Total results from DB: {len(db_results)}")
    except Exception as e:
        print(f"  WARNING: DB unavailable: {e}")
        print("  Results unavailable — accuracy metrics will be empty.")

    if db_results:
        print("  Backfilling into evaluation records...")
        filled = backfill_all_results(rounds, db_results)
        print(f"  Backfilled {filled} new results into eval records")

    # Step 4: Collect metrics
    print("\n[4/6] Collecting match metrics...")
    metrics = []
    for ri in rounds:
        for match in ri.matches:
            if not match.has_v14:
                continue
            m = collect_match_metrics(match, db_results=db_results)
            if m:
                metrics.append(m)

    print(f"  Collected {len(metrics)} match metrics")
    with_results = sum(1 for m in metrics if m.get("actual_result"))
    print(f"  {with_results} with actual results")

    # Step 5: Aggregates
    print("\n[5/6] Computing aggregates...")
    aggregates = compute_aggregates(metrics)

    # Rounds summary
    rounds_summary = [
        {"label": r.label, "league": r.league, "n_matches": len(r.matches), "n_finished": r.n_finished}
        for r in rounds
    ]

    # Step 6: Generate outputs
    print("\n[6/6] Generating reports...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON data
    data = {
        "timestamp": timestamp,
        "rounds_summary": rounds_summary,
        "aggregates": aggregates,
        "matches": metrics,
    }
    data_path = OUTPUT_DIR / "v15_baseline_data.json"
    with open(data_path, "w") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)
    print(f"  Data: {data_path}")

    # HTML report
    html = generate_html_report(metrics, aggregates, rounds_summary, timestamp)
    html_path = OUTPUT_DIR / "v15_baseline_report.html"
    with open(html_path, "w") as f:
        f.write(html)
    print(f"  HTML: {html_path}")

    # Quick summary
    da = aggregates.get("directional_accuracy", {})
    print(f"\n{'=' * 60}")
    print(f"SUMMARY ({len(metrics)} matches, {with_results} with results)")
    print(f"  v1.4 accuracy: {da.get('v14_accuracy', 'N/A')}%")
    print(f"  v1.5 accuracy: {da.get('v15_accuracy', 'N/A')}%")
    print(f"  v1.5 clear-only: {da.get('v15_accuracy_clear_only', 'N/A')}%")
    print(f"  Next lever: {aggregates.get('recommended_next_lever', {}).get('area', 'N/A')}")
    print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
