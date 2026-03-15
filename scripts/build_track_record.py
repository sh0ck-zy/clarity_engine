#!/usr/bin/env python3
"""
Build Track Record — aggregate prediction results across rounds.

Usage:
    python scripts/build_track_record.py PL_R28          # single round
    python scripts/build_track_record.py --aggregate --league PL  # all rounds
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from evaluation.prediction_tracker import build_round_track_record


def _print_track_record(track: dict, label: str) -> None:
    """Print formatted terminal table."""
    total = track["total_matches"]
    resolved = track["resolved_matches"]
    roi = track["roi"]

    print(f"\nTRACK RECORD | {label} | {total} matches ({resolved} resolved)")

    # Layer hit rates
    by_layer = track.get("by_layer", {})
    parts = []
    for layer in ("ml", "tactical", "engine"):
        info = by_layer.get(layer, {})
        hr = info.get("hit_rate")
        if hr is not None:
            parts.append(f"{layer.upper()} {hr*100:.1f}%")
    if parts:
        print(f"\n  Layer hit rates:  {'  '.join(parts)}")

    # By action
    by_action = track.get("by_action", {})
    print("\n  By action:")
    for action in ("PICK", "LEAN", "WATCHLIST", "NO_BET"):
        a = by_action.get(action, {})
        count = a.get("count", 0)
        if count == 0:
            print(f"    {action:<10} —")
            continue
        correct = a.get("correct", 0)
        pct = correct / count * 100 if count else 0
        staked = a.get("staked", 0)
        profit = a.get("profit", 0)
        if staked > 0:
            roi_pct = a.get("roi_pct", 0)
            sign = "+" if profit >= 0 else ""
            print(
                f"    {action:<10} {correct}/{count}  ({pct:3.0f}%)   "
                f"staked {staked:.1f}u  profit {sign}{profit:.2f}u  ROI {sign}{roi_pct:.0f}%"
            )
        else:
            print(f"    {action:<10} {correct}/{count}  ({pct:3.0f}%)   no stake")

    # By category
    by_category = track.get("by_category", {})
    if by_category:
        print("\n  By category:")
        for cat in ("TOP_ANGLE", "LIVE_DOG", "TRAP_SPOT", "TOO_THIN", "UNCLASSIFIED"):
            c = by_category.get(cat)
            if not c:
                continue
            count = c["count"]
            correct = c["correct"]
            staked = c.get("staked", 0)
            profit = c.get("profit", 0)
            if staked > 0:
                sign = "+" if profit >= 0 else ""
                print(f"    {cat:<12} {correct}/{count}  ({correct/count*100:3.0f}%)   {sign}{profit:.2f}u")
            else:
                print(f"    {cat:<12} {correct}/{count}  ({correct/count*100:3.0f}%)   no stake")

    # Total
    staked = roi.get("total_staked", 0)
    profit = roi.get("total_profit", 0)
    roi_pct = roi.get("roi_pct")
    if staked > 0:
        sign = "+" if profit >= 0 else ""
        print(f"\n  Total: staked {staked:.1f}u | profit {sign}{profit:.2f}u | ROI {sign}{roi_pct:.1f}%")
    else:
        print("\n  Total: no stakes placed")


def single_round(round_label: str) -> None:
    """Build track record for a single round."""
    round_path = PROJECT_ROOT / "output" / "rounds" / round_label
    if not round_path.exists():
        print(f"Round directory not found: {round_path}")
        return

    track = build_round_track_record(round_path)
    track_path = round_path / "track_record.json"
    track_path.write_text(
        json.dumps(track, indent=2, ensure_ascii=False, default=str)
    )
    _print_track_record(track, round_label)


def aggregate(league: str) -> None:
    """Aggregate track records across all rounds for a league."""
    rounds_dir = PROJECT_ROOT / "output" / "rounds"
    if not rounds_dir.exists():
        print(f"Rounds directory not found: {rounds_dir}")
        return

    # Collect all round track records
    round_labels = []
    all_tracks = []
    for rdir in sorted(rounds_dir.iterdir()):
        if not rdir.is_dir() or not rdir.name.startswith(f"{league}_R"):
            continue
        track_path = rdir / "track_record.json"
        if not track_path.exists():
            # Build on the fly
            track = build_round_track_record(rdir)
            track_path.write_text(
                json.dumps(track, indent=2, ensure_ascii=False, default=str)
            )
        else:
            track = json.loads(track_path.read_text())
        all_tracks.append(track)
        round_labels.append(rdir.name)

    if not all_tracks:
        print(f"No rounds found for {league}")
        return

    # Merge
    merged = _merge_tracks(all_tracks)

    # Write aggregate
    out_path = PROJECT_ROOT / "output" / f"track_record_{league}.json"
    out_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False, default=str)
    )

    first_r = round_labels[0].split("_R")[1] if round_labels else "?"
    last_r = round_labels[-1].split("_R")[1] if round_labels else "?"
    _print_track_record(merged, f"{league} | R{first_r}-R{last_r}")
    print(f"\n  Written to {out_path}")


def _merge_tracks(tracks: list) -> dict:
    """Merge multiple round track records into one aggregate."""
    total_matches = sum(t["total_matches"] for t in tracks)
    resolved_matches = sum(t["resolved_matches"] for t in tracks)

    # Merge by_layer
    by_layer = {}
    for layer in ("ml", "tactical", "engine"):
        total = sum(t.get("by_layer", {}).get(layer, {}).get("total", 0) for t in tracks)
        correct = sum(t.get("by_layer", {}).get(layer, {}).get("correct", 0) for t in tracks)
        by_layer[layer] = {
            "total": total,
            "correct": correct,
            "hit_rate": round(correct / total, 4) if total else None,
        }

    # Merge by_action
    by_action = {}
    for action in ("PICK", "LEAN", "WATCHLIST", "NO_BET"):
        count = sum(t.get("by_action", {}).get(action, {}).get("count", 0) for t in tracks)
        correct = sum(t.get("by_action", {}).get(action, {}).get("correct", 0) for t in tracks)
        staked = sum(t.get("by_action", {}).get(action, {}).get("staked", 0) for t in tracks)
        profit = sum(t.get("by_action", {}).get(action, {}).get("profit", 0) for t in tracks)
        by_action[action] = {
            "count": count,
            "correct": correct,
            "staked": round(staked, 2),
            "profit": round(profit, 4),
            "roi_pct": round(profit / staked * 100, 2) if staked else None,
        }

    # Merge by_category
    by_category = {}
    all_cats = set()
    for t in tracks:
        all_cats.update(t.get("by_category", {}).keys())
    for cat in all_cats:
        count = sum(t.get("by_category", {}).get(cat, {}).get("count", 0) for t in tracks)
        correct = sum(t.get("by_category", {}).get(cat, {}).get("correct", 0) for t in tracks)
        staked = sum(t.get("by_category", {}).get(cat, {}).get("staked", 0) for t in tracks)
        profit = sum(t.get("by_category", {}).get(cat, {}).get("profit", 0) for t in tracks)
        by_category[cat] = {
            "count": count,
            "correct": correct,
            "staked": round(staked, 2),
            "profit": round(profit, 4),
        }

    # Merge by_confidence
    by_confidence = {}
    all_confs = set()
    for t in tracks:
        all_confs.update(t.get("by_confidence", {}).keys())
    for conf in all_confs:
        total = sum(t.get("by_confidence", {}).get(conf, {}).get("total", 0) for t in tracks)
        correct = sum(t.get("by_confidence", {}).get(conf, {}).get("correct", 0) for t in tracks)
        by_confidence[conf] = {
            "total": total,
            "correct": correct,
            "hit_rate": round(correct / total, 4) if total else None,
        }

    total_staked = sum(v["staked"] for v in by_action.values())
    total_profit = sum(v["profit"] for v in by_action.values())

    return {
        "total_matches": total_matches,
        "resolved_matches": resolved_matches,
        "by_layer": by_layer,
        "by_action": by_action,
        "by_category": by_category,
        "by_confidence": by_confidence,
        "roi": {
            "total_staked": round(total_staked, 2),
            "total_profit": round(total_profit, 4),
            "roi_pct": round(total_profit / total_staked * 100, 2) if total_staked else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build track record from prediction records")
    parser.add_argument("round", nargs="?", help="Round label (e.g. PL_R28)")
    parser.add_argument("--aggregate", action="store_true", help="Aggregate all rounds")
    parser.add_argument("--league", default="PL", help="League code for aggregation")
    args = parser.parse_args()

    if args.aggregate:
        aggregate(args.league)
    elif args.round:
        single_round(args.round)
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
