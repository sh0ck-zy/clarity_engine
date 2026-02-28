#!/usr/bin/env python3
"""
Analysis Dossier pipeline: generates a complete auditable dossier per fixture.

Usage:
    python scripts/analyse_fixture.py --round 27 --match "Everton vs Manchester United"
    python scripts/analyse_fixture.py --round 27   # all fixtures in the round
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from models import config as model_config
from models.feature_builder import build_feature_dataset
from models.probabilistic import predict_fixture_with_audit
from pipeline.facts_builder import build_facts
from pipeline.report_writer import write_report
from pipeline.draft_formatter import format_draft
from pipeline.run_manifest import RunManifest
from pipeline.schema_validator import validate_artifact

OUTPUT_DIR = PROJECT_ROOT / "output" / "analysis_runs"


def _sanitize_name(name: str) -> str:
    """Sanitize a string for use in directory names."""
    return re.sub(r"[^\w\-]", "_", name.replace(" ", "_"))


def _fixture_ref(row) -> str:
    home = _sanitize_name(row["home_team_name"])
    away = _sanitize_name(row["away_team_name"])
    return f"PL_R{int(row['round_number'])}_{home}_vs_{away}"


def _resolve_fixtures(df, round_number: int, match_filter: str | None):
    """Find fixture rows matching the round and optional team filter."""
    round_df = df[df["round_number"] == round_number]
    if round_df.empty:
        raise ValueError(f"No fixtures found for round {round_number}")

    if match_filter:
        q = match_filter.lower()
        mask = (
            round_df["home_team_name"].str.lower().str.contains(q, na=False)
            | round_df["away_team_name"].str.lower().str.contains(q, na=False)
        )
        round_df = round_df[mask]
        if round_df.empty:
            raise ValueError(f"No fixtures matching '{match_filter}' in round {round_number}")

    return round_df.reset_index(drop=True)


def _save_json(data: dict, path: Path) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def _save_text(text: str, path: Path) -> None:
    with open(path, "w") as f:
        f.write(text)


def _validate_and_warn(data: dict, schema_name: str, label: str) -> list[str]:
    """Validate against schema and print warnings."""
    errors = validate_artifact(data, schema_name)
    if errors:
        print(f"  WARN: {label} has {len(errors)} schema violation(s):")
        for e in errors[:5]:
            print(f"    - {e}")
    return errors


def analyse_fixture(fixture_row, df, output_base: Path) -> Path:
    """Run the full analysis pipeline for a single fixture."""
    ref = _fixture_ref(fixture_row)
    run_id = f"run_{uuid.uuid4()}"
    today = date.today().isoformat()
    output_dir = output_base / today / ref
    output_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir = output_dir / "drafts"
    drafts_dir.mkdir(exist_ok=True)

    manifest = RunManifest(fixture_ref=ref, run_id=run_id)

    home = fixture_row["home_team_name"]
    away = fixture_row["away_team_name"]
    rnd = int(fixture_row["round_number"])
    print(f"\n{'='*60}")
    print(f"  R{rnd} | {home} vs {away}")
    print(f"  Run: {run_id}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}")

    # --- Step 1: Build facts ---
    manifest.step_start("build_facts")
    try:
        print("\n  [1/3] Building facts...")
        audit = predict_fixture_with_audit(fixture_row, df)
        facts = build_facts(fixture_row, audit, run_id)
        _validate_and_warn(facts, "facts", "facts.json")
        _save_json(facts, output_dir / "facts.json")
        print(f"  facts.json saved ({facts['provenance']['facts_hash'][:20]}...)")
        manifest.step_end("build_facts", "ok")
    except Exception as e:
        manifest.step_end("build_facts", "error", notes=str(e))
        manifest.add_error(f"build_facts: {e}")
        raise

    # --- Step 2: Write report ---
    manifest.step_start("write_report")
    try:
        print("\n  [2/3] Writing report...")
        report = write_report(facts)
        _validate_and_warn(report, "report", "report.json")
        _save_json(report, output_dir / "report.json")
        mode = report["writer_metadata"]["generation_mode"]
        print(f"  report.json saved (mode={mode})")
        manifest.step_end("write_report", "ok", notes=f"writer_model={report['writer_metadata']['model']}")
    except Exception as e:
        manifest.step_end("write_report", "error", notes=str(e))
        manifest.add_error(f"write_report: {e}")
        raise

    # --- Step 3: Format drafts ---
    manifest.step_start("format_drafts")
    try:
        print("\n  [3/3] Formatting drafts...")
        draft_notes = []
        for channel in ["telegram", "x"]:
            text, meta = format_draft(report, facts, channel, run_id)
            _save_text(text, drafts_dir / f"{channel}.txt")
            _save_json(meta, drafts_dir / f"{channel}.meta.json")
            _validate_and_warn(meta, "draft_meta", f"{channel}.meta.json")
            draft_notes.append(f"{channel}={meta['source']}")
            print(f"  {channel}.txt saved ({meta['char_count']} chars, source={meta['source']})")

        manifest.step_end("format_drafts", "ok", notes=",".join(draft_notes))
    except Exception as e:
        manifest.step_end("format_drafts", "error", notes=str(e))
        manifest.add_error(f"format_drafts: {e}")
        raise

    # --- Finalize manifest ---
    manifest_data = manifest.finalize(output_dir)
    _validate_and_warn(manifest_data, "run_manifest", "run_manifest.json")
    manifest.save(output_dir / "run_manifest.json", manifest_data)
    print(f"\n  run_manifest.json saved (total: {manifest_data['total_duration_ms']}ms)")

    # --- Summary ---
    probs = facts["ml"]["probabilities"]
    pred = facts["ml"]["prediction"]
    signals = facts["ml"]["signals"]
    print(f"\n  SUMMARY")
    print(f"  H={probs['home_win']:.0%}  D={probs['draw']:.0%}  A={probs['away_win']:.0%}")
    print(f"  Pick: {pred['predicted_result']}  Conf: {pred['confidence_label']}")
    print(f"  p_max={signals['p_max']:.3f}  margin={signals['margin_top2']:.3f}  entropy={signals['entropy_norm']:.3f}")
    if facts["ml"]["risk_flags"]:
        print(f"  Flags: {', '.join(facts['ml']['risk_flags'])}")
    if manifest_data["warnings"]:
        print(f"  Warnings: {', '.join(manifest_data['warnings'])}")
    print(f"{'='*60}\n")

    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Analysis Dossier pipeline ({model_config.MODEL_VERSION})"
    )
    parser.add_argument("--round", type=int, required=True, help="Round number")
    parser.add_argument("--match", type=str, default=None, help="Filter by team name substring")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Base output directory")
    parser.add_argument("--allow-missing-elo", action="store_true", help="Allow ELO missing rate > 5%%")

    args = parser.parse_args()

    print(f"Motor: {model_config.MODEL_VERSION} | C={model_config.C} | Features: {len(model_config.FEATURE_COLS)}")
    print("Building feature dataset...")
    df = build_feature_dataset(allow_missing_elo=args.allow_missing_elo)

    fixtures = _resolve_fixtures(df, args.round, args.match)
    print(f"\n{len(fixtures)} fixture(s) to analyse in Round {args.round}")

    output_dirs = []
    for i in range(len(fixtures)):
        row = fixtures.iloc[i]
        try:
            out = analyse_fixture(row, df, args.output_dir)
            output_dirs.append(out)
        except Exception as e:
            print(f"\nERROR analysing {row['home_team_name']} vs {row['away_team_name']}: {e}")

    print(f"\nDone. {len(output_dirs)}/{len(fixtures)} dossier(s) generated.")
    for d in output_dirs:
        print(f"  {d}")

    return 0 if len(output_dirs) == len(fixtures) else 1


if __name__ == "__main__":
    raise SystemExit(main())
