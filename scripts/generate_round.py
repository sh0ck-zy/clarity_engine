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
        mkt_h, mkt_d, mkt_a = market_odds[key]
        mkt = {
            "prob_H": round(mkt_h, 4),
            "prob_D": round(mkt_d, 4),
            "prob_A": round(mkt_a, 4),
            "source": "Bet365",
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

    # 8. v1.5 Match Intelligence Engine (if --intelligence)
    if intelligence:
        print("\n" + "=" * 60)
        print("  v1.5 MATCH INTELLIGENCE ENGINE")
        print("=" * 60)

        from intelligence.match_pack_builder import build_match_pack, build_ml_anchor
        from intelligence.match_signals import compute_match_signals
        from intelligence.match_intelligence import (
            MatchIntelligenceEngine,
            render_intelligence_text,
        )
        from intelligence.telegram_renderer import render_telegram_v15
        from evaluation.intelligence_validator import (
            IntelligenceValidator,
            build_evaluation_record,
        )

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

            try:
                # Step 1: Build match pack (no LLM)
                print("    Building match pack...")
                match_pack = build_match_pack(
                    home_team=home,
                    away_team=away,
                    round_number=round_number,
                    league_id=league_id,
                    league_name=league,
                    fixture_id=str(fixture_id),
                    match_date=match_date,
                )
                with open(match_dir / "match_pack.json", "w") as f:
                    json.dump(match_pack, f, indent=2, default=str, ensure_ascii=False)

                # Step 2: Build ML anchor (reshape report)
                ml_anchor = build_ml_anchor(report)
                with open(match_dir / "ml_anchor.json", "w") as f:
                    json.dump(ml_anchor, f, indent=2, default=str)

                # Step 3: Compute match signals (no LLM)
                print("    Computing signals...")
                signals = compute_match_signals(match_pack, ml_anchor)
                with open(match_dir / "match_signals.json", "w") as f:
                    json.dump(signals, f, indent=2, default=str)

                # Step 4: Generate match intelligence (LLM)
                print("    Reading the game...")
                mi_result = mi_engine.generate(
                    match_pack=match_pack,
                    ml_anchor=ml_anchor,
                    match_signals=signals,
                    cache_path=match_dir / "match_intelligence.json",
                    regenerate=regenerate,
                )

                # Step 5: Validate
                validation = mi_validator.validate(mi_result, ml_anchor)
                print(f"    Validator score: {validation.score:.1f}/100"
                      f" ({'PASS' if validation.score >= 60 else 'FAIL'})")
                if validation.issues:
                    for issue in validation.issues[:3]:
                        print(f"      - [{issue['check']}] {issue['issue']}")

                # Step 6: Render plaintext
                mi_text = render_intelligence_text(mi_result)
                with open(match_dir / "match_intelligence.txt", "w") as f:
                    f.write(mi_text)

                # Step 7: Evaluation record
                eval_record = build_evaluation_record(
                    match_pack, ml_anchor, signals, mi_result, validation
                )
                with open(match_dir / "evaluation_record.json", "w") as f:
                    json.dump(eval_record, f, indent=2, default=str, ensure_ascii=False)

                # Step 8: v1.5 Telegram draft
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

        print("\n  Match Intelligence complete for all matches")

    # 9. Print summary
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
    parser.add_argument("--mi-model", default="gpt-4o",
                        help="LLM model for Match Intelligence (default: gpt-4o)")
    parser.add_argument("--regenerate", action="store_true",
                        help="Force regenerate (skip cache)")

    args = parser.parse_args()

    generate_round(
        args.round,
        league=args.league,
        league_id=args.league_id,
        season=args.season,
        intelligence=args.intelligence,
        mi_model=args.mi_model,
        regenerate=args.regenerate,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
