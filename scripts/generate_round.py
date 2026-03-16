#!/usr/bin/env python3
"""
Generate all analyses for a round into the round-based folder structure.

Usage:
    python scripts/generate_round.py 28
    python scripts/generate_round.py 28 --league PL --league-id 47
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from models import config as model_config
from models.feature_builder import build_feature_dataset, _load_market_odds
from models.probabilistic import predict_round
from renderers.match_renderer import (
    classify_editorial,
    render_telegram_post,
    render_x_post,
)
from utils.round_io import (
    match_folder_name,
    round_dir,
    write_round_config,
    write_round_status,
    write_review,
)


# Raw team stats columns from the feature builder SQL
_HOME_STATS_COLS = {
    "home_position": "position",
    "home_goal_diff": "goal_difference",
    "home_form_points": "form_points",
    "home_xg_diff_last5": "xg_diff_last5",
    "home_venue_points": "venue_points",
    "home_played": "played",
    "home_clean_sheets_last5": "clean_sheets_last5",
}

_AWAY_STATS_COLS = {
    "away_position": "position",
    "away_goal_diff": "goal_difference",
    "away_form_points": "form_points",
    "away_xg_diff_last5": "xg_diff_last5",
    "away_venue_points": "venue_points",
    "away_played": "played",
    "away_clean_sheets_last5": "clean_sheets_last5",
}


def _load_raw_stats(league_id: int, round_number: int) -> pd.DataFrame:
    """Load raw team stats from DB for a specific round (for facts.json)."""
    from database.config import get_connection

    sql = """
    SELECT
        m.fotmob_match_id,
        m.home_team_name, m.away_team_name,
        h.position AS home_position,
        h.goal_difference AS home_goal_diff,
        h.form_points AS home_form_points,
        h.xg_diff_last5 AS home_xg_diff_last5,
        h.home_points AS home_venue_points,
        h.played AS home_played,
        h.clean_sheets_last5 AS home_clean_sheets_last5,
        a.position AS away_position,
        a.goal_difference AS away_goal_diff,
        a.form_points AS away_form_points,
        a.xg_diff_last5 AS away_xg_diff_last5,
        a.away_points AS away_venue_points,
        a.played AS away_played,
        a.clean_sheets_last5 AS away_clean_sheets_last5
    FROM fotmob_matches m
    JOIN team_states h ON h.team_id = m.home_team_id AND h.round_number = m.round_number - 1
        AND h.league_id = %(lid)s
    JOIN team_states a ON a.team_id = m.away_team_id AND a.round_number = m.round_number - 1
        AND a.league_id = %(lid)s
    WHERE m.round_number = %(rn)s AND m.league_id = %(lid)s
    """
    conn = get_connection()
    try:
        return pd.read_sql(sql, conn, params={"lid": league_id, "rn": round_number})
    finally:
        conn.close()


def _extract_facts(
    raw_row: Optional[pd.Series],
    df_row: pd.Series,
    report: Dict,
    market_odds: Dict,
) -> Dict:
    """Build facts.json content for a match."""
    home = report["fixture"]["home_team"]
    away = report["fixture"]["away_team"]

    # Raw team stats
    home_stats = {}
    away_stats = {}
    if raw_row is not None:
        for col, label in _HOME_STATS_COLS.items():
            val = raw_row.get(col)
            home_stats[label] = _safe_val(val)
        for col, label in _AWAY_STATS_COLS.items():
            val = raw_row.get(col)
            away_stats[label] = _safe_val(val)

    # ELO from the feature DataFrame
    elo_delta = _safe_val(df_row.get("elo_delta"))
    # We don't have raw ELOs in the df, but we have the delta
    home_stats["elo_delta_vs_opponent"] = elo_delta

    # Computed features (the 8 model features)
    features = {}
    for col in model_config.FEATURE_COLS:
        features[col] = _safe_val(df_row.get(col))

    # Market odds
    mkt = {}
    key = (home, away)
    if key in market_odds:
        mkt_h, mkt_d, mkt_a, raw_h, raw_d, raw_a = market_odds[key]
        mkt = {
            "prob_H": round(mkt_h, 4),
            "prob_D": round(mkt_d, 4),
            "prob_A": round(mkt_a, 4),
            "odds_H": round(raw_h, 2),
            "odds_D": round(raw_d, 2),
            "odds_A": round(raw_a, 2),
            "source": "Bet365",
            "price_source": "decimal_odds",
        }

    return {
        "fixture_id": report["fixture"]["fixture_id"],
        "round_number": report["fixture"]["round_number"],
        "match_date": report["fixture"]["match_date"],
        "home_team": home,
        "away_team": away,
        "home_stats": home_stats,
        "away_stats": away_stats,
        "computed_features": features,
        "market_odds": mkt if mkt else None,
        "elo_missing": bool(df_row.get("elo_missing_any", 0)),
    }


def _build_board(rdir: Path) -> None:
    """Build daily board from cached MI artifacts (no LLM calls)."""
    from intelligence.daily_board import build_daily_board
    from renderers.board_telegram import render_board_telegram

    print("\n  Building daily board...")
    board = build_daily_board(rdir)
    if board.get("error"):
        print(f"  Board: {board['error']}")
        return

    board_tg = render_board_telegram(board)
    (rdir / "board_telegram.txt").write_text(board_tg)

    actionable = board.get("actionable_angles", 0)
    print(f"  Board: {board['matches_analyzed']} analyzed, {actionable} actionable")


def _safe_val(v):
    """Convert numpy/pandas types to JSON-safe Python types."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        if np.isnan(v):
            return None
        return round(float(v), 4)
    if isinstance(v, float) and np.isnan(v):
        return None
    return v


def generate_round(
    round_number: int,
    league: str = "PL",
    league_id: int = 47,
    season: str = "2025/26",
    intelligence: bool = False,
    mi_model: str = "gpt-4o",
    regenerate: bool = False,
    rerender: bool = False,
    board_only: bool = False,
) -> Path:
    """Generate all round artifacts. Returns the round directory path."""
    print(f"Motor: {model_config.MODEL_VERSION} | C={model_config.C} | "
          f"Features: {len(model_config.FEATURE_COLS)}")

    # 1. Build feature dataset
    print("Building feature dataset...")
    df = build_feature_dataset(league_id=league_id, allow_missing_elo=True)

    # 2. Predict round
    print(f"Predicting Round {round_number}...")
    reports = predict_round(round_number, df=df)
    print(f"  {len(reports)} match predictions generated")

    # 3. Load market odds
    market_odds = {}
    try:
        market_odds = _load_market_odds(league_id=league_id)
        print(f"  Market odds loaded: {len(market_odds)} matches")
    except Exception:
        print("  No market odds available")

    # 4. Load raw stats for facts.json
    try:
        raw_df = _load_raw_stats(league_id, round_number)
        print(f"  Raw team stats loaded: {len(raw_df)} matches")
    except Exception:
        raw_df = pd.DataFrame()
        print("  Could not load raw team stats")

    # 5. Create round directory
    rdir = round_dir(league, round_number)
    rdir.mkdir(parents=True, exist_ok=True)

    write_round_config(rdir, league, league_id, round_number, season,
                       model_config.MODEL_VERSION, len(reports))
    write_round_status(rdir, status="draft")

    # Board-only mode: regenerate board from cached MI, no LLM calls
    if board_only:
        _build_board(rdir)
        return rdir

    # 6. Get round rows from feature DataFrame
    round_df = df[df["round_number"] == round_number].copy()

    # 7. Write per-match artifacts
    for report in reports:
        home = report["fixture"]["home_team"]
        away = report["fixture"]["away_team"]
        fixture_id = report["fixture"]["fixture_id"]

        # Match folder
        folder = match_folder_name(home, away)
        match_dir = rdir / "matches" / folder
        match_dir.mkdir(parents=True, exist_ok=True)

        # Find DataFrame row for this match
        df_match = round_df[round_df["fotmob_match_id"].astype(str) == str(fixture_id)]
        df_row = df_match.iloc[0] if len(df_match) > 0 else pd.Series()

        # Find raw stats row
        raw_match = raw_df[raw_df["fotmob_match_id"].astype(str) == str(fixture_id)] if len(raw_df) > 0 else pd.DataFrame()
        raw_row = raw_match.iloc[0] if len(raw_match) > 0 else None

        # facts.json
        facts = _extract_facts(raw_row, df_row, report, market_odds)
        with open(match_dir / "facts.json", "w") as f:
            json.dump(facts, f, indent=2, default=str)

        # report.json
        with open(match_dir / "report.json", "w") as f:
            json.dump(report, f, indent=2, default=str)

        # review.json (initial)
        write_review(match_dir, status="pending")

        # drafts
        drafts_dir = match_dir / "drafts"
        drafts_dir.mkdir(exist_ok=True)

        editorial = classify_editorial(report)
        tg = render_telegram_post(report, editorial=editorial)
        x = render_x_post(report, editorial=editorial)

        with open(drafts_dir / "telegram.txt", "w") as f:
            f.write(tg)
        with open(drafts_dir / "x.txt", "w") as f:
            f.write(x)

    # 8. Rerender-only mode: re-render telegram from existing MI JSONs
    if rerender:
        from intelligence.match_intelligence import render_intelligence_text
        from intelligence.telegram_renderer import render_telegram_v15

        print("\n  Re-rendering telegram drafts from cached MI...")
        for report in reports:
            home = report["fixture"]["home_team"]
            away = report["fixture"]["away_team"]
            folder = match_folder_name(home, away)
            match_dir = rdir / "matches" / folder
            mi_path = match_dir / "match_intelligence.json"
            if not mi_path.exists():
                print(f"  {home} vs {away}: no MI, skipping")
                continue
            mi_result = json.loads(mi_path.read_text())

            # Re-render plaintext
            mi_text = render_intelligence_text(mi_result)
            with open(match_dir / "match_intelligence.txt", "w") as f:
                f.write(mi_text)

            # Re-render telegram
            drafts_dir = match_dir / "drafts"
            drafts_dir.mkdir(exist_ok=True)
            tg = render_telegram_v15(mi_result, report)
            with open(drafts_dir / "telegram_v15.txt", "w") as f:
                f.write(tg)

            print(f"  {home} vs {away}: re-rendered")

        print(f"\n  Re-rendered {len(reports)} matches")
        return rdir

    # 9. v1.6 Match Intelligence Engine (if --intelligence)
    if intelligence:
        print("\n" + "=" * 60)
        print("  v1.8 MATCH INTELLIGENCE ENGINE")
        print("=" * 60)

        from intelligence.match_pack_builder import build_match_pack, build_ml_anchor
        from intelligence.match_signals import compute_match_signals
        from intelligence.tactical_rubric import build_tactical_rubric
        from intelligence.match_intelligence import (
            MatchIntelligenceEngine,
            render_intelligence_text,
        )
        from intelligence.telegram_renderer import render_telegram_v15
        from evaluation.intelligence_validator import (
            IntelligenceValidator,
            build_evaluation_record,
        )
        from evaluation.data_quality import check_match_pack_quality
        from evaluation.trace import PipelineTrace, TraceContext
        from evaluation.rubric import score_pre_match_rubric, compute_confidence_level
        from intelligence.decision_engine import make_decision

        mi_engine = MatchIntelligenceEngine(model=mi_model)
        mi_validator = IntelligenceValidator()

        for report in reports:
            home = report["fixture"]["home_team"]
            away = report["fixture"]["away_team"]
            fixture_id = report["fixture"]["fixture_id"]
            match_date = report["fixture"].get("match_date", "")
            folder = match_folder_name(home, away)
            match_dir = rdir / "matches" / folder

            print(f"\n  {home} vs {away}")

            # Initialize trace
            trace = PipelineTrace(match_id=str(fixture_id))
            trace.start()

            try:
                # Step 1: Build match pack (no LLM, with trace)
                print("    Building match pack...")
                match_pack = build_match_pack(
                    home_team=home,
                    away_team=away,
                    round_number=round_number,
                    league_id=league_id,
                    league_name=league,
                    fixture_id=str(fixture_id),
                    match_date=match_date,
                    trace=trace,
                )
                with open(match_dir / "match_pack.json", "w") as f:
                    json.dump(match_pack, f, indent=2, default=str, ensure_ascii=False)

                # Step 1b: Data quality checks
                with TraceContext(trace, "data_quality_check", "data_quality") as dq_ctx:
                    dq_result = check_match_pack_quality(match_pack)
                    dq_ctx.metadata = dq_result.to_dict()
                    if dq_result.warnings:
                        for w in dq_result.warnings:
                            dq_ctx.warnings.append(w.get("issue", str(w)))

                mi_status = dq_result.mi_status
                if dq_result.warnings:
                    print(f"    Data quality: completeness={dq_result.completeness_score:.0f} "
                          f"integrity={dq_result.integrity_score:.0f} "
                          f"({len(dq_result.warnings)} issues, "
                          f"{len(dq_result.critical_flags)} critical) "
                          f"→ MI: {mi_status.upper()}")
                    for w in dq_result.warnings[:3]:
                        print(f"      - {w.get('issue', w)}")
                    if dq_result.critical_flags:
                        print(f"    Critical flags: {', '.join(dq_result.critical_flags)}")

                # Gate: skip MI if data is too broken (binary READY/SKIP)
                if mi_status == "skip":
                    print(f"    SKIP: data integrity too low "
                          f"(completeness={dq_result.completeness_score:.0f}, "
                          f"integrity={dq_result.integrity_score:.0f})")
                    skip_record = {
                        "schema_version": "1.7",
                        "match_id": str(fixture_id),
                        "mi_status": "skip",
                        "reason": f"completeness={dq_result.completeness_score:.0f}, "
                                  f"integrity={dq_result.integrity_score:.0f}",
                        "data_quality": dq_result.to_dict(),
                    }
                    with open(match_dir / "match_intelligence.json", "w") as f:
                        json.dump(skip_record, f, indent=2, ensure_ascii=False)
                    continue

                # Step 2: Build ML anchor (reshape report)
                ml_anchor = build_ml_anchor(report)
                with open(match_dir / "ml_anchor.json", "w") as f:
                    json.dump(ml_anchor, f, indent=2, default=str)

                # Step 3: Compute match signals (no LLM)
                print("    Computing signals...")
                with TraceContext(trace, "compute_match_signals", "signal") as sig_ctx:
                    signals = compute_match_signals(match_pack, ml_anchor)
                with open(match_dir / "match_signals.json", "w") as f:
                    json.dump(signals, f, indent=2, default=str)

                # Step 3b: Build tactical rubric (v1.6 — no LLM)
                print("    Building tactical rubric...")
                with TraceContext(trace, "build_tactical_rubric", "rubric") as rub_tac_ctx:
                    tactical_rubric = build_tactical_rubric(match_pack, ml_anchor)
                with open(match_dir / "tactical_rubric.json", "w") as f:
                    json.dump(tactical_rubric, f, indent=2, default=str, ensure_ascii=False)

                # Attach rubric to match_pack for reference
                match_pack["tactical_rubric"] = tactical_rubric

                # Step 3c: Compute deterministic confidence level
                confidence_level = compute_confidence_level(
                    ml_anchor, signals, dq_result.score
                )
                print(f"    Confidence: {confidence_level}")

                # Step 4: Generate match intelligence (LLM with thinking)
                print(f"    Reading the game [{mi_model}]...")

                mi_failed = False
                try:
                    with TraceContext(trace, "llm_generate", "llm") as llm_ctx:
                        mi_result = mi_engine.generate(
                            match_pack=match_pack,
                            ml_anchor=ml_anchor,
                            match_signals=signals,
                            tactical_rubric=tactical_rubric,
                            cache_path=match_dir / "match_intelligence.json",
                            regenerate=regenerate,
                            confidence_level=confidence_level,
                            data_warnings=dq_result.warnings if dq_result.warnings else None,
                        )
                        llm_trace = mi_result.get("_llm_trace", {})
                        llm_ctx.metadata = llm_trace
                except Exception as mi_err:
                    print(f"    MI failed ({mi_err}), running decision engine without narrative")
                    mi_failed = True
                    mi_result = {
                        "schema_version": "1.8",
                        "mi_status": "degraded",
                        "reason": str(mi_err),
                        "lean": "",
                        "confidence": confidence_level,
                    }

                # Annotate MI result with data quality status
                mi_result["mi_status"] = "degraded" if mi_failed else mi_status
                mi_result["completeness_score"] = round(dq_result.completeness_score, 1)
                mi_result["integrity_score"] = round(dq_result.integrity_score, 1)
                mi_result["critical_data_flags"] = dq_result.critical_flags

                # Step 5: Validate
                if not mi_failed:
                    with TraceContext(trace, "validate", "validator") as val_ctx:
                        validation = mi_validator.validate(mi_result, ml_anchor)
                        val_ctx.metadata = {"score": validation.score}
                    print(f"    Validator score: {validation.score:.1f}/100"
                          f" ({'PASS' if validation.score >= 60 else 'FAIL'})")
                    if validation.issues:
                        for issue in validation.issues[:3]:
                            print(f"      - [{issue['check']}] {issue['issue']}")
                else:
                    validation = type("V", (), {"score": 0, "issues": [], "components": {}})()

                # Step 5b: Rubric scoring
                if not mi_failed:
                    with TraceContext(trace, "rubric_scoring", "validator") as rub_ctx:
                        rubric_result = score_pre_match_rubric(
                            mi_result, match_pack, ml_anchor, signals, dq_result.score
                        )
                        rub_ctx.metadata = {"score": rubric_result.score}
                    print(f"    Rubric score: {rubric_result.score:.1f}/100")
                else:
                    rubric_result = type("R", (), {"score": 0, "to_dict": lambda self: {}})()
                    print("    Rubric: skipped (no MI)")

                # Step 5c: Decision layer (post-MI, does NOT gate MI)
                # Build market odds for this match
                match_market = None
                mkt_key = (home, away)
                if mkt_key in market_odds:
                    mkt_h, mkt_d, mkt_a, raw_h, raw_d, raw_a = market_odds[mkt_key]
                    match_market = {
                        "prob_H": mkt_h, "prob_D": mkt_d, "prob_A": mkt_a,
                        "odds_H": raw_h, "odds_D": raw_d, "odds_A": raw_a,
                    }

                lean_text = mi_result.get("lean", "")
                decision = make_decision(
                    ml_anchor, confidence_level, dq_result,
                    signals, tactical_rubric, match_market,
                    lean_text=lean_text,
                    home_team=home,
                    away_team=away,
                )
                mi_result["decision"] = decision.to_dict()
                mi_result["directions"] = decision.directions
                print(f"    Decision: {decision.action}"
                      f" {decision.direction or ''}"
                      f" — {decision.reasoning[0] if decision.reasoning else ''}")

                # Step 5d: Write-back enriched MI (decision, directions, DQ fields)
                save_mi = {k: v for k, v in mi_result.items() if not k.startswith("_")}
                with open(match_dir / "match_intelligence.json", "w") as f:
                    json.dump(save_mi, f, indent=2, default=str, ensure_ascii=False)

                # Step 6: Render plaintext
                mi_text = render_intelligence_text(mi_result)
                with open(match_dir / "match_intelligence.txt", "w") as f:
                    f.write(mi_text)

                # Step 7: Evaluation record (enriched)
                trace_data = trace.to_dict()
                eval_record = build_evaluation_record(
                    match_pack, ml_anchor, signals, mi_result, validation,
                    rubric_result=rubric_result,
                    data_quality_result=dq_result,
                    trace_data=trace_data,
                )
                with open(match_dir / "evaluation_record.json", "w") as f:
                    json.dump(eval_record, f, indent=2, default=str, ensure_ascii=False)

                # Step 7a: Prediction record
                from evaluation.prediction_tracker import build_prediction_record
                pred_record = build_prediction_record(match_dir, round_config={
                    "league": league, "round_number": round_number,
                    "model_version": model_config.MODEL_VERSION,
                })
                with open(match_dir / "prediction_record.json", "w") as f:
                    json.dump(pred_record, f, indent=2, default=str, ensure_ascii=False)

                # Step 7b: Save trace
                with open(match_dir / "trace.json", "w") as f:
                    json.dump(trace_data, f, indent=2, default=str)

                # Step 8: Telegram draft
                drafts_dir = match_dir / "drafts"
                drafts_dir.mkdir(exist_ok=True)
                tg_v15 = render_telegram_v15(mi_result, report)
                with open(drafts_dir / "telegram_v15.txt", "w") as f:
                    f.write(tg_v15)

                print(f"    Done: {mi_result.get('lean', '?')}")

            except Exception as e:
                print(f"    FAILED: {e}")
                import traceback
                traceback.print_exc()
                # Save partial trace even on failure
                try:
                    with open(match_dir / "trace.json", "w") as f:
                        json.dump(trace.to_dict(), f, indent=2, default=str)
                except Exception:
                    pass

        print("\n  Match Intelligence complete for all matches")

    # 9b. Build daily board
    _build_board(rdir)

    # 9c. Patch board_category + clarity_score into prediction records
    board_path = rdir / "board.json"
    if board_path.exists():
        board_data = json.loads(board_path.read_text())
        for entry in board_data.get("matches", []):
            mid = str(entry.get("match_id", ""))
            cat = entry.get("category")
            cs = entry.get("clarity_score")
            # Find the match dir for this match_id
            matches_path = rdir / "matches"
            if matches_path.exists():
                for md in matches_path.iterdir():
                    pred_p = md / "prediction_record.json"
                    if not pred_p.exists():
                        continue
                    pr = json.loads(pred_p.read_text())
                    if pr.get("match_id") == mid:
                        pr["board_category"] = cat
                        pr["clarity_score"] = cs
                        with open(pred_p, "w") as f:
                            json.dump(pr, f, indent=2, default=str, ensure_ascii=False)
                        break

    # 10. Print summary
    print(f"\nRound generated: {rdir}")
    print(f"  {len(reports)} matches")

    # Editorial summary
    editorial_counts = {"publish": 0, "watchlist": 0, "skip": 0}
    for report in reports:
        ed = classify_editorial(report)
        editorial_counts[ed] += 1

    print(f"  Editorial: {editorial_counts['publish']} publish, "
          f"{editorial_counts['watchlist']} watchlist, "
          f"{editorial_counts['skip']} skip")

    # Scoreboard
    ref = model_config.BENCHMARK_REF
    if ref.get("log_loss") and ref.get("market_log_loss"):
        delta = ref["log_loss"] - ref["market_log_loss"]
        direction = "market wins" if delta > 0 else "model wins"
        print(f"\n  Model vs Market: {ref['log_loss']:.4f} vs {ref['market_log_loss']:.4f} "
              f"({direction} by {abs(delta / ref['market_log_loss'] * 100):.1f}%)")

    return rdir


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Generate round analyses ({model_config.MODEL_VERSION})"
    )
    parser.add_argument("round", type=int, help="Round number")
    parser.add_argument("--league", default="PL", help="League short name (default: PL)")
    parser.add_argument("--league-id", type=int, default=47,
                        help="FotMob league ID (47=PL, 61=Portugal, 268=Brazil)")
    parser.add_argument("--season", default="2025/26", help="Season (default: 2025/26)")
    parser.add_argument("--intelligence", action="store_true",
                        help="Use v1.5 Match Intelligence Engine (game reading)")
    parser.add_argument("--mi-model", default="gpt-5.4",
                        help="LLM model for Match Intelligence (default: gpt-5.4). "
                        "Supports: gpt-5.4, gpt-4o, gpt-4.1, claude-opus-4-6, claude-sonnet-4-6, o3")
    parser.add_argument("--regenerate", action="store_true",
                        help="Force regenerate (skip cache)")
    parser.add_argument("--rerender", action="store_true",
                        help="Re-render telegram/plaintext from cached MI (no LLM calls)")
    parser.add_argument("--board-only", action="store_true",
                        help="Regenerate board from cached MI (no LLM calls)")
    parser.add_argument("--publish", action="store_true",
                        help="Restart telegram bot after generation (docker)")

    args = parser.parse_args()

    generate_round(
        args.round,
        league=args.league,
        league_id=args.league_id,
        season=args.season,
        intelligence=args.intelligence,
        mi_model=args.mi_model,
        regenerate=args.regenerate,
        rerender=args.rerender,
        board_only=args.board_only,
    )

    if args.publish or args.rerender:
        import subprocess
        print("\n  Restarting telegram bot...")
        subprocess.run(
            ["docker", "compose", "restart", "telegram-bot"],
            cwd="/Users/joao/Projects/clarity-odds-core",
        )
        print("  Bot restarted.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
