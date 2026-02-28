#!/usr/bin/env python3
"""
Review CLI: read and approve/reject an analysis dossier.

Usage:
    python scripts/review_analysis.py output/analysis_runs/2026-02-24/PL_R27_Everton_vs_Manchester_United/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from pipeline.hashing import compute_file_hash
from pipeline.schema_validator import validate_artifact


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _load_text(path: Path) -> str:
    with open(path) as f:
        return f.read()


def _print_section(title: str) -> None:
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def review_dossier(dossier_dir: Path) -> None:
    """Interactive review of an analysis dossier."""
    facts_path = dossier_dir / "facts.json"
    report_path = dossier_dir / "report.json"
    manifest_path = dossier_dir / "run_manifest.json"
    review_path = dossier_dir / "review.json"

    if not facts_path.exists():
        print(f"ERROR: {facts_path} not found")
        return
    if not report_path.exists():
        print(f"ERROR: {report_path} not found")
        return

    facts = _load_json(facts_path)
    report = _load_json(report_path)
    manifest = _load_json(manifest_path) if manifest_path.exists() else None

    fixture = facts["fixture"]
    print(f"\n{'='*60}")
    print(f"  ANALYSIS DOSSIER REVIEW")
    print(f"  R{fixture['round_number']} | {fixture['home_team']} vs {fixture['away_team']}")
    print(f"  Date: {fixture['match_date']}")
    print(f"  Run: {facts['provenance']['run_id']}")
    print(f"{'='*60}")

    # --- Facts: Probabilities & Prediction ---
    _print_section("PROBABILITIES & PREDICTION")
    probs = facts["ml"]["probabilities"]
    pred = facts["ml"]["prediction"]
    signals = facts["ml"]["signals"]
    print(f"  H {probs['home_win']:.1%}  |  D {probs['draw']:.1%}  |  A {probs['away_win']:.1%}")
    print(f"  Pick: {pred['predicted_result']}  Confidence: {pred['confidence_label']}")
    print(f"  p_max={signals['p_max']:.3f}  margin={signals['margin_top2']:.3f}  entropy={signals['entropy_norm']:.3f}")

    # --- Facts: Drivers ---
    _print_section("DRIVERS")
    for d in facts["ml"]["drivers"]:
        print(f"  {d['feature']:30s}  val={d['value']:+8.2f}  contrib={d['contribution']:+.4f}  dir={d['direction']}")

    # --- Facts: Risk Flags ---
    flags = facts["ml"]["risk_flags"]
    if flags:
        _print_section("RISK FLAGS")
        for f in flags:
            print(f"  - {f}")

    # --- Facts: Validation Checks ---
    _print_section("VALIDATION CHECKS")
    for check in facts["validation_checks"]:
        icon = {"pass": "OK", "warn": "!!", "fail": "XX"}[check["status"]]
        details = f" ({check['details']})" if check.get("details") else ""
        print(f"  [{icon}] {check['name']}{details}")

    # --- Report: Narrative ---
    _print_section("REPORT — Summary")
    print(f"  Headline: {report['summary']['headline']}")
    print(f"  {report['summary']['overview']}")

    _print_section("REPORT — Analysis")
    print(f"  Rationale: {report['analysis']['prediction_rationale']}")
    print(f"\n  Key factors:")
    for kf in report["analysis"]["key_factors"]:
        print(f"    - {kf}")
    print(f"\n  Risks:")
    for r in report["analysis"]["risks"]:
        print(f"    - {r}")
    print(f"\n  Confidence: {report['analysis']['confidence_assessment']}")

    writer = report["writer_metadata"]
    print(f"\n  [Writer: {writer['model']} | mode={writer['generation_mode']} | prompt={writer['prompt_version']}]")

    # --- Drafts ---
    for channel in ["telegram", "x"]:
        draft_path = dossier_dir / "drafts" / f"{channel}.txt"
        meta_path = dossier_dir / "drafts" / f"{channel}.meta.json"
        if draft_path.exists():
            text = _load_text(draft_path)
            meta = _load_json(meta_path) if meta_path.exists() else {}
            _print_section(f"DRAFT — {channel.upper()} ({len(text)} chars, source={meta.get('source', '?')})")
            print(text)

    # --- Manifest ---
    if manifest:
        _print_section("MANIFEST")
        for step in manifest["steps"]:
            print(f"  {step['name']:20s}  {step['status']:6s}  {step['duration_ms']:>6d}ms  {step.get('notes') or ''}")
        if manifest["warnings"]:
            print(f"\n  Warnings: {', '.join(manifest['warnings'])}")
        print(f"\n  Total: {manifest['total_duration_ms']}ms")

    # --- Review Input ---
    print(f"\n{'='*60}")
    print("  REVIEW DECISION")
    print(f"{'='*60}")

    if review_path.exists():
        existing = _load_json(review_path)
        print(f"\n  Existing review: {existing['status']} by {existing['reviewer']} at {existing['reviewed_at']}")
        if existing.get("notes"):
            print(f"  Notes: {existing['notes']}")
        print()

    choice = input("  [A]pprove / [R]eject / [E]dits needed / [Q]uit: ").strip().upper()
    if choice == "Q":
        print("  Exiting without review.")
        return

    status_map = {"A": "approved", "R": "rejected", "E": "needs_changes"}
    status = status_map.get(choice)
    if not status:
        print(f"  Invalid choice: {choice}")
        return

    reviewer = input("  Reviewer name: ").strip() or "anonymous"
    notes = input("  Notes (optional): ").strip()

    review = {
        "schema_version": "1.0",
        "run_id": facts["provenance"]["run_id"],
        "status": status,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": reviewer,
        "notes": notes,
        "hashes": {
            "facts_hash": compute_file_hash(facts_path),
            "report_hash": compute_file_hash(report_path),
        },
    }

    errors = validate_artifact(review, "review")
    if errors:
        print(f"  WARN: review.json has schema violations: {errors[:3]}")

    with open(review_path, "w") as f:
        json.dump(review, f, indent=2, ensure_ascii=False)
    print(f"\n  Review saved: {review_path}")
    print(f"  Status: {status}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Review an analysis dossier")
    parser.add_argument("dossier", type=Path, help="Path to dossier directory")
    args = parser.parse_args()

    if not args.dossier.is_dir():
        print(f"ERROR: {args.dossier} is not a directory")
        return 1

    review_dossier(args.dossier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
