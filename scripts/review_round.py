#!/usr/bin/env python3
"""
Review and approve a generated round.

Interactive CLI dashboard for reviewing match analyses before publishing.

Usage:
    python scripts/review_round.py PL_R28
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
from utils.round_io import read_round_status, update_round_status, read_review, write_review

ROUNDS_DIR = PROJECT_ROOT / "output" / "rounds"


def _load_round(round_dir: Path) -> Dict:
    """Load all round data into memory."""
    config_path = round_dir / "round_config.json"
    status_path = round_dir / "round_status.json"
    quality_path = round_dir / "quality_report.json"

    data = {
        "dir": round_dir,
        "config": {},
        "status": {},
        "quality": {},
        "matches": [],
    }

    if config_path.exists():
        with open(config_path) as f:
            data["config"] = json.load(f)

    if status_path.exists():
        data["status"] = read_round_status(round_dir)

    if quality_path.exists():
        with open(quality_path) as f:
            data["quality"] = json.load(f)

    matches_dir = round_dir / "matches"
    if matches_dir.exists():
        for md in sorted(matches_dir.iterdir()):
            if not md.is_dir():
                continue
            match = {"dir": md, "name": md.name}

            rp = md / "report.json"
            if rp.exists():
                with open(rp) as f:
                    match["report"] = json.load(f)

            fp = md / "facts.json"
            if fp.exists():
                with open(fp) as f:
                    match["facts"] = json.load(f)

            qp = md / "quality_checks.json"
            if qp.exists():
                with open(qp) as f:
                    match["quality"] = json.load(f)

            match["review"] = read_review(md)

            tp = md / "drafts" / "telegram.txt"
            if tp.exists():
                match["telegram"] = tp.read_text()

            xp = md / "drafts" / "x.txt"
            if xp.exists():
                match["x_post"] = xp.read_text()

            data["matches"].append(match)

    return data


def _print_dashboard(data: Dict) -> None:
    """Print the review dashboard."""
    cfg = data["config"]
    status = data["status"]
    quality = data.get("quality", {})
    matches = data["matches"]

    n_approved = sum(1 for m in matches if m.get("review", {}).get("status") == "approved")
    n_total = len(matches)
    mean_mis = quality.get("mean_mis", "?")
    mis_str = f"{mean_mis:.0%}" if isinstance(mean_mis, float) else str(mean_mis)

    print(f"\n{'='*70}")
    print(f" {cfg.get('league', '?')} ROUND {cfg.get('round_number', '?')} "
          f"| {cfg.get('model_version', '?')} | REVIEW DASHBOARD")
    print(f" Status: {status.get('status', '?').upper()} "
          f"| {n_approved}/{n_total} approved "
          f"| Avg MIS: {mis_str}")
    print(f"{'='*70}\n")

    # Scoreboard
    ref = model_config.BENCHMARK_REF
    if ref.get("log_loss") and ref.get("market_log_loss"):
        delta = ref["log_loss"] - ref["market_log_loss"]
        direction = "market" if delta > 0 else "model"
        print(f" Model: {ref['log_loss']:.4f}  Market: {ref['market_log_loss']:.4f}  "
              f"({direction} wins by {abs(delta / ref['market_log_loss'] * 100):.1f}%)\n")

    print(f" {'#':<3s} {'Match':<35s} {'H':>6s} {'D':>6s} {'A':>6s} "
          f"{'Pick':>5s} {'Conf':>6s} {'MIS':>5s} {'Status':>10s}")
    print(f" {'-'*80}")

    for i, m in enumerate(matches, 1):
        report = m.get("report", {})
        p = report.get("probabilities", {})
        pred = report.get("prediction", {})
        quality = m.get("quality", {})
        review = m.get("review", {})

        name = m["name"].replace("_", " ")
        h = f"{p.get('home_win', 0):.1%}" if p else "?"
        d = f"{p.get('draw', 0):.1%}" if p else "?"
        a = f"{p.get('away_win', 0):.1%}" if p else "?"
        pick = pred.get("predicted_result", "?")
        conf = pred.get("confidence", "?")
        mis = f"{quality.get('mis_score', 0):.0%}" if quality else "?"
        rev_status = review.get("status", "pending")

        icon = {"approved": "+", "rejected": "x", "pending": " "}.get(rev_status, " ")

        print(f" {i:<3d} {name:<35s} {h:>6s} {d:>6s} {a:>6s} "
              f"{pick:>5s} {conf:>6s} {mis:>5s} [{icon}] {rev_status}")

    print(f"\n{'='*70}")
    print(f" Commands:")
    print(f"   <N>          Show match details (e.g., '1')")
    print(f"   approve <N>  Approve match N")
    print(f"   reject <N>   Reject match N")
    print(f"   note <N> <text>  Add review note")
    print(f"   approve all  Approve all passing matches (MIS >= threshold)")
    print(f"   status       Refresh dashboard")
    print(f"   q            Quit")
    print(f"{'='*70}\n")


def _show_match(match: Dict, index: int) -> None:
    """Print detailed view of a single match."""
    report = match.get("report", {})
    facts = match.get("facts", {})
    quality = match.get("quality", {})
    review = match.get("review", {})

    fixture = report.get("fixture", {})
    probs = report.get("probabilities", {})
    pred = report.get("prediction", {})
    drivers = report.get("drivers", [])
    flags = report.get("risk_flags", [])

    print(f"\n{'='*70}")
    print(f" MATCH {index}: {fixture.get('home_team', '?')} vs {fixture.get('away_team', '?')}")
    print(f" Round {fixture.get('round_number')} | {fixture.get('match_date')}")
    print(f"{'='*70}")

    # Probabilities
    print(f"\n PREDICTION:")
    print(f"   H={probs.get('home_win', 0):.1%}  "
          f"D={probs.get('draw', 0):.1%}  "
          f"A={probs.get('away_win', 0):.1%}")
    print(f"   Pick: {pred.get('predicted_result')}  "
          f"Confidence: {pred.get('confidence')}  "
          f"Margin: {pred.get('margin_top2', 0):.3f}  "
          f"Entropy: {pred.get('entropy_norm', 0):.3f}")

    if flags:
        print(f"   Flags: {', '.join(flags)}")

    # Actual result if available
    if report.get("actual_result"):
        correct = "CORRECT" if report.get("result_correct") else "WRONG"
        print(f"   Actual: {report['actual_result']} [{correct}]")

    # Drivers
    print(f"\n DRIVERS (top {len(drivers)}):")
    for d in drivers:
        direction_icon = "+" if d["direction"] == "for" else "-"
        print(f"   {direction_icon} {d['feature']:<30s} value={d['value']:<10.2f} "
              f"contribution={d['contribution']:.4f}")

    # Facts
    if facts:
        print(f"\n FACTS:")
        hs = facts.get("home_stats", {})
        aws = facts.get("away_stats", {})
        if hs or aws:
            print(f"   {'Stat':<25s} {'Home':>10s} {'Away':>10s}")
            print(f"   {'-'*45}")
            all_keys = sorted(set(list(hs.keys()) + list(aws.keys())))
            for key in all_keys:
                hv = hs.get(key, "—")
                av = aws.get(key, "—")
                hv_str = f"{hv}" if hv is not None else "—"
                av_str = f"{av}" if av is not None else "—"
                print(f"   {key:<25s} {hv_str:>10s} {av_str:>10s}")

        features = facts.get("computed_features", {})
        if features:
            print(f"\n   Model features:")
            for k, v in features.items():
                print(f"     {k:<30s} = {v}")

        mkt = facts.get("market_odds")
        if mkt:
            print(f"\n   Market odds ({mkt.get('source', '?')}):")
            print(f"     H={mkt['prob_H']:.1%}  D={mkt['prob_D']:.1%}  A={mkt['prob_A']:.1%}")
        else:
            print(f"\n   Market odds: not available")

    # Quality
    if quality:
        print(f"\n MIS SCORE: {quality.get('mis_score', 0):.0%}")
        for comp_name, comp in quality.get("breakdown", {}).items():
            score = comp.get("score", 0)
            issues = comp.get("issues", [])
            status = "OK" if score >= 0.7 else "LOW"
            print(f"   {comp_name:<25s} {score:.0%} [{status}]")
            for issue in issues:
                print(f"     - {issue}")

    # Telegram draft
    tg = match.get("telegram", "")
    if tg:
        print(f"\n TELEGRAM DRAFT:")
        print(f"   {'-'*50}")
        for line in tg.split("\n"):
            print(f"   {line}")
        print(f"   {'-'*50}")

    # X draft
    xp = match.get("x_post", "")
    if xp:
        print(f"\n X POST ({len(xp)} chars):")
        print(f"   {'-'*50}")
        for line in xp.split("\n"):
            print(f"   {line}")
        print(f"   {'-'*50}")

    # Review status
    print(f"\n REVIEW: {review.get('status', 'pending')}")
    if review.get("notes"):
        print(f"   Notes: {review['notes']}")
    print()


def _approve_match(data: Dict, index: int) -> None:
    """Approve a single match."""
    match = data["matches"][index]
    write_review(match["dir"], status="approved", reviewed_at=datetime.now().isoformat())
    match["review"] = read_review(match["dir"])
    name = match["name"].replace("_", " ")
    print(f"  Approved: {name}")


def _reject_match(data: Dict, index: int) -> None:
    """Reject a single match."""
    match = data["matches"][index]
    write_review(match["dir"], status="rejected", reviewed_at=datetime.now().isoformat())
    match["review"] = read_review(match["dir"])
    name = match["name"].replace("_", " ")
    print(f"  Rejected: {name}")


def _add_note(data: Dict, index: int, note: str) -> None:
    """Add a review note to a match."""
    match = data["matches"][index]
    current = read_review(match["dir"])
    existing = current.get("notes", "")
    new_notes = f"{existing}\n{note}".strip() if existing else note
    write_review(match["dir"], status=current.get("status", "pending"),
                 notes=new_notes, reviewed_at=datetime.now().isoformat())
    match["review"] = read_review(match["dir"])
    print(f"  Note added to {match['name'].replace('_', ' ')}")


def _approve_all(data: Dict, threshold: float = 0.70) -> None:
    """Approve all matches with MIS >= threshold."""
    approved = 0
    for match in data["matches"]:
        quality = match.get("quality", {})
        mis = quality.get("mis_score", 0)
        review = match.get("review", {})
        if mis >= threshold and review.get("status") != "approved":
            write_review(match["dir"], status="approved", reviewed_at=datetime.now().isoformat())
            match["review"] = read_review(match["dir"])
            approved += 1
    print(f"  Approved {approved} matches (MIS >= {threshold:.0%})")

    # Update round status
    n_approved = sum(1 for m in data["matches"] if m.get("review", {}).get("status") == "approved")
    n_total = len(data["matches"])
    if n_approved == n_total:
        update_round_status(data["dir"], status="approved", approved_at=datetime.now().isoformat())
        data["status"] = read_round_status(data["dir"])
        print(f"  Round status: APPROVED ({n_approved}/{n_total})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Review and approve a generated round")
    parser.add_argument("round_name", help="Round folder name (e.g., PL_R28)")

    args = parser.parse_args()

    rdir = ROUNDS_DIR / args.round_name
    if not rdir.exists():
        print(f"Round directory not found: {rdir}")
        return 1

    data = _load_round(rdir)
    _print_dashboard(data)

    # Interactive loop
    while True:
        try:
            cmd = input("review> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not cmd:
            continue

        if cmd.lower() in ("q", "quit", "exit"):
            break

        if cmd.lower() == "status":
            data = _load_round(rdir)
            _print_dashboard(data)
            continue

        # approve all
        if cmd.lower() == "approve all":
            _approve_all(data)
            continue

        # approve N
        parts = cmd.split(maxsplit=2)
        if parts[0].lower() == "approve" and len(parts) >= 2:
            try:
                idx = int(parts[1]) - 1
                if 0 <= idx < len(data["matches"]):
                    _approve_match(data, idx)
                else:
                    print(f"  Invalid match number. Use 1-{len(data['matches'])}")
            except ValueError:
                print(f"  Usage: approve <N>")
            continue

        # reject N
        if parts[0].lower() == "reject" and len(parts) >= 2:
            try:
                idx = int(parts[1]) - 1
                if 0 <= idx < len(data["matches"]):
                    _reject_match(data, idx)
                else:
                    print(f"  Invalid match number. Use 1-{len(data['matches'])}")
            except ValueError:
                print(f"  Usage: reject <N>")
            continue

        # note N <text>
        if parts[0].lower() == "note" and len(parts) >= 3:
            try:
                idx = int(parts[1]) - 1
                note_text = parts[2]
                if 0 <= idx < len(data["matches"]):
                    _add_note(data, idx, note_text)
                else:
                    print(f"  Invalid match number. Use 1-{len(data['matches'])}")
            except ValueError:
                print(f"  Usage: note <N> <text>")
            continue

        # Show match by number
        try:
            idx = int(cmd) - 1
            if 0 <= idx < len(data["matches"]):
                _show_match(data["matches"][idx], idx + 1)
            else:
                print(f"  Invalid match number. Use 1-{len(data['matches'])}")
        except ValueError:
            print(f"  Unknown command: {cmd}")
            print(f"  Try: <N>, approve <N>, reject <N>, note <N> <text>, approve all, status, q")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
