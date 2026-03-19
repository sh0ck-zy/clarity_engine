#!/usr/bin/env python3
"""
Publish preview pipeline: predict -> render -> preview -> export.

Human-in-the-loop: generates all predictions, shows editorial classification,
lets you review before exporting final posts.

Usage:
    python scripts/publish_preview.py 27                # preview R27
    python scripts/publish_preview.py 27 --export       # export approved posts
    python scripts/publish_preview.py 27 --all          # include skipped games
    python scripts/publish_preview.py 12 --backtest     # backtest mode (show actuals)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

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
    render_round_telegram,
    validate_report,
)

PUBLISH_LOG_DIR = PROJECT_ROOT / "output" / "publish_log"


def print_scoreboard(
    reports: List[Dict],
    league_id: Optional[int] = None,
) -> None:
    """Print model vs market comparison scoreboard."""
    ref = model_config.BENCHMARK_REF

    # Load market odds for per-match comparison
    market_odds = {}
    if league_id is not None:
        try:
            market_odds = _load_market_odds(league_id=league_id)
        except Exception:
            pass

    print(f"\n{'='*70}")
    print(f"  MODEL vs MARKET  |  {model_config.MODEL_VERSION}  |  "
          f"{len(model_config.FEATURE_COLS)} features")
    print(f"{'='*70}")

    # Benchmark numbers from config
    if ref.get("log_loss"):
        mkt_ll = ref.get("market_log_loss", 0)
        mdl_ll = ref["log_loss"]
        delta = mdl_ll - mkt_ll
        pct = (delta / mkt_ll * 100) if mkt_ll else 0
        direction = "market wins" if delta > 0 else "model wins"

        print(f"  Model log loss:   {mdl_ll:.4f}  "
              f"(R{ref['predict_rounds'][0]}-R{ref['predict_rounds'][-1]}, "
              f"{ref['n_predictions']} preds)")
        print(f"  Market log loss:  {mkt_ll:.4f}  (Bet365 closing)")
        print(f"  Delta:           {delta:+.4f}  ({direction} by {abs(pct):.1f}%)")
        print(f"  Model accuracy:   {ref['accuracy']:.1%}")
        print(f"  Uniform baseline: {ref['uniform_log_loss']:.4f}  "
              f"(model beats by {abs(ref.get('delta_vs_uniform', 0)):.1%})")
    else:
        print("  Benchmark not yet computed — run walk_forward_evaluate()")

    print(f"{'='*70}")

    # Per-match market comparison
    if market_odds and reports:
        print(f"\n  {'MATCH':<45s} {'MODEL':>8s} {'MARKET':>8s} {'DIFF':>8s}")
        print(f"  {'-'*69}")
        for report in reports:
            home = report["fixture"]["home_team"]
            away = report["fixture"]["away_team"]
            p = report["probabilities"]
            pred = report["prediction"]["predicted_result"]

            key = (home, away)
            if key in market_odds:
                mkt_h, mkt_d, mkt_a = market_odds[key]
                # Show the predicted outcome's probability comparison
                if pred == "H":
                    mdl_p, mkt_p, label = p["home_win"], mkt_h, "H"
                elif pred == "A":
                    mdl_p, mkt_p, label = p["away_win"], mkt_a, "A"
                else:
                    mdl_p, mkt_p, label = p["draw"], mkt_d, "D"

                diff = mdl_p - mkt_p
                match_str = f"{home[:20]} vs {away[:20]}"
                print(f"  {match_str:<45s} {mdl_p:>7.1%} {mkt_p:>7.1%} {diff:>+7.1%}  [{label}]")
            else:
                match_str = f"{home[:20]} vs {away[:20]}"
                print(f"  {match_str:<45s} {'—':>8s} {'no odds':>8s}")

        print()


def preview_round(
    reports: List[Dict],
    show_all: bool = False,
    backtest: bool = False,
) -> Dict[str, List[Dict]]:
    """
    Show preview of all predictions with editorial classification.

    Returns dict: {"publish": [...], "watchlist": [...], "skip": [...]}
    """
    buckets: Dict[str, List[Dict]] = {"publish": [], "watchlist": [], "skip": []}

    for report in reports:
        editorial = classify_editorial(report)
        buckets[editorial].append(report)

    # Print preview
    round_num = reports[0]["fixture"]["round_number"] if reports else "?"

    print(f"\n{'='*70}")
    print(f"ROUND {round_num} PREVIEW | {model_config.MODEL_VERSION}")
    print(f"{'='*70}")

    for category in ["publish", "watchlist", "skip"]:
        items = buckets[category]
        if not items and not show_all:
            continue

        icon = {"publish": ">>", "watchlist": "~~", "skip": "  "}[category]
        label = {"publish": "PUBLISH", "watchlist": "WATCHLIST", "skip": "SKIP"}[category]

        if category == "skip" and not show_all:
            print(f"\n  [{label}] {len(items)} games skipped (use --all to see)")
            continue

        print(f"\n  [{label}] ({len(items)} games)")
        print(f"  {'-'*60}")

        for report in items:
            f = report["fixture"]
            p = report["probabilities"]
            pred = report["prediction"]
            rid = report.get("report_id", "???")

            actual_str = ""
            if backtest and report.get("actual_result"):
                correct = "OK" if report.get("result_correct") else "MISS"
                actual_str = f" => {report['actual_result']} [{correct}]"

            print(
                f"  {icon} {f['home_team']:25s} vs {f['away_team']:25s}"
            )
            print(
                f"     H={p['home_win']:.1%}  D={p['draw']:.1%}  A={p['away_win']:.1%}"
                f"  | pick={pred['predicted_result']}"
                f"  conf={pred['confidence']}"
                f"  margin={pred['margin_top2']:.3f}"
                f"{actual_str}"
            )

            flags = report["risk_flags"]
            if flags:
                print(f"     flags: {', '.join(flags)}")

            print(f"     [{rid}]")

    # Summary
    print(f"\n{'='*70}")
    print(f"  Summary: {len(buckets['publish'])} publish, "
          f"{len(buckets['watchlist'])} watchlist, "
          f"{len(buckets['skip'])} skip")

    if backtest:
        all_with_actual = [r for r in reports if r.get("actual_result")]
        if all_with_actual:
            correct = sum(1 for r in all_with_actual if r.get("result_correct"))
            pub_with_actual = [r for r in buckets["publish"] if r.get("actual_result")]
            pub_correct = sum(1 for r in pub_with_actual if r.get("result_correct"))
            print(f"  Backtest: {correct}/{len(all_with_actual)} overall "
                  f"({correct/len(all_with_actual):.0%}), "
                  f"{pub_correct}/{len(pub_with_actual)} published "
                  f"({pub_correct/len(pub_with_actual):.0%})" if pub_with_actual else "")

    print(f"{'='*70}\n")

    return buckets


def export_posts(
    reports: List[Dict],
    buckets: Dict[str, List[Dict]],
    output_dir: Path,
    round_num: int,
) -> None:
    """Export rendered posts and publish log."""
    output_dir.mkdir(parents=True, exist_ok=True)

    publishable = buckets["publish"] + buckets["watchlist"]

    if not publishable:
        print("Nothing to export (no publishable predictions).")
        return

    # Render posts
    telegram_posts = []
    x_posts = []

    for report in publishable:
        editorial = classify_editorial(report)
        tg = render_telegram_post(report, editorial=editorial)
        x = render_x_post(report, editorial=editorial)
        telegram_posts.append({"report_id": report["report_id"], "editorial": editorial, "text": tg})
        x_posts.append({"report_id": report["report_id"], "editorial": editorial, "text": x})

    # Batch telegram message
    batch_tg = render_round_telegram(publishable)

    # Build publish log entry
    log_entry = {
        "round_number": round_num,
        "model_version": model_config.MODEL_VERSION,
        "created_at": datetime.now().isoformat(),
        "editorial_summary": {
            "publish": len(buckets["publish"]),
            "watchlist": len(buckets["watchlist"]),
            "skip": len(buckets["skip"]),
        },
        "posts": {
            "telegram": telegram_posts,
            "x": x_posts,
            "telegram_batch": batch_tg,
        },
        "reports": publishable,
    }

    # Save
    log_path = output_dir / f"R{round_num}_{model_config.MODEL_VERSION}.json"
    with open(log_path, "w") as f:
        json.dump(log_entry, f, indent=2, default=str)
    print(f"Publish log saved: {log_path}")

    # Print final telegram batch
    print(f"\n{'='*70}")
    print("TELEGRAM BATCH (copy-paste ready):")
    print(f"{'='*70}")
    print(batch_tg)
    print(f"{'='*70}")

    # Print X posts
    print(f"\nX POSTS ({len(x_posts)} posts):")
    print(f"{'-'*70}")
    for xp in x_posts:
        print(f"\n[{xp['editorial'].upper()}] ({len(xp['text'])} chars)")
        print(xp["text"])
    print(f"{'-'*70}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Publish preview pipeline ({model_config.MODEL_VERSION})"
    )
    parser.add_argument(
        "round",
        type=int,
        help="Round number to predict and preview",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export rendered posts and publish log",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show skipped games in preview",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Show actual results (for completed rounds)",
    )
    parser.add_argument(
        "--allow-missing-elo",
        action="store_true",
        help="Allow ELO missing rate > 5%%",
    )
    parser.add_argument(
        "--league-id",
        type=int,
        default=None,
        help="provider league ID to filter by (47=PL, 61=Portugal, 268=Brazil)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PUBLISH_LOG_DIR,
        help="Output directory for publish log",
    )

    args = parser.parse_args()

    # Build dataset + predict
    print(f"Motor: {model_config.MODEL_VERSION} | C={model_config.C} | "
          f"Features: {len(model_config.FEATURE_COLS)}")
    print("Building feature dataset...")
    df = build_feature_dataset(allow_missing_elo=args.allow_missing_elo, league_id=args.league_id)

    print(f"Predicting Round {args.round}...")
    reports = predict_round(args.round, df=df)

    # Scoreboard: model vs market
    print_scoreboard(reports, league_id=args.league_id)

    # Preview
    buckets = preview_round(reports, show_all=args.all, backtest=args.backtest)

    # Export if requested
    if args.export:
        export_posts(reports, buckets, args.output_dir, args.round)
    else:
        print("Run with --export to generate final posts and publish log.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
