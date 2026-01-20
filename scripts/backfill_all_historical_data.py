#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


@dataclass(frozen=True)
class StageResult:
    name: str
    success: bool
    detail: str


STAGE_SEQUENCE = [
    "fbref",
    "transfermarkt",
    "odds",
    "features",
    "validation",
]

STAGE_LABELS = {
    "fbref": "FBref scrape",
    "transfermarkt": "Transfermarkt import",
    "odds": "Odds download",
    "features": "Feature derivation",
    "validation": "Data validation",
}


def _normalize_stage(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _season_start_year(value: str) -> int:
    text = str(value).strip()
    if text.isdigit():
        if len(text) == 4:
            if text.startswith("20"):
                return int(text)
            return 2000 + int(text[:2])
        if len(text) == 2:
            return 2000 + int(text)
    raise ValueError(f"Invalid season value: {value}")


def _season_code(value: str) -> str:
    start_year = _season_start_year(value)
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def _run_command(label: str, args: list[str]) -> StageResult:
    command_str = " ".join(args)
    print(f"-> {label}: {command_str}")
    result = subprocess.run(args, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        return StageResult(label, False, f"Exit code {result.returncode}")
    return StageResult(label, True, "ok")


def _run_fbref(season_codes: list[str]) -> StageResult:
    args = [
        sys.executable,
        str(SCRIPTS_DIR / "scrape_fbref_historical.py"),
        "--seasons",
        *season_codes,
    ]
    return _run_command(STAGE_LABELS["fbref"], args)


def _run_transfermarkt() -> StageResult:
    args = [
        sys.executable,
        str(SCRIPTS_DIR / "import_transfermarkt_dataset.py"),
    ]
    return _run_command(STAGE_LABELS["transfermarkt"], args)


def _run_odds(season_codes: list[str]) -> StageResult:
    args = [
        sys.executable,
        str(SCRIPTS_DIR / "download_odds_historical.py"),
        "--seasons",
        *season_codes,
    ]
    return _run_command(STAGE_LABELS["odds"], args)


def _run_features(season_years: list[int]) -> StageResult:
    for season in season_years:
        args = [
            sys.executable,
            str(SCRIPTS_DIR / "derive_match_features.py"),
            "--season",
            str(season),
        ]
        result = _run_command(f"{STAGE_LABELS['features']} ({season})", args)
        if not result.success:
            return result
    return StageResult(STAGE_LABELS["features"], True, "ok")


def _run_validation(season_years: list[int], detailed: bool) -> list[StageResult]:
    results: list[StageResult] = []
    for season in season_years:
        output_path = PROJECT_ROOT / f"data_completeness_report_{season}.json"
        args = [
            sys.executable,
            str(SCRIPTS_DIR / "validate_data_completeness.py"),
            "--season",
            str(season),
            "--output",
            str(output_path),
        ]
        if detailed:
            args.append("--detailed")
        results.append(
            _run_command(f"{STAGE_LABELS['validation']} ({season})", args)
        )
    return results


def _load_completeness_summary(path: Path) -> Optional[dict[str, float]]:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return {
        "fixtures": payload.get("fixtures", {}).get("coverage", 0.0),
        "team_match_stats": payload.get("team_match_stats", {}).get("coverage", 0.0),
        "lineups": payload.get("lineups", {}).get("coverage", 0.0),
        "player_market_values": payload.get("player_market_values", {}).get(
            "coverage", 0.0
        ),
        "odds": payload.get("odds", {}).get("coverage", 0.0),
    }


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full historical backfill pipeline.",
    )
    parser.add_argument(
        "--seasons",
        nargs="*",
        default=["2021", "2022", "2023", "2024"],
        help="Season start years or season codes (default: 2021 2022 2023 2024).",
    )
    parser.add_argument(
        "--skip-scraping",
        action="store_true",
        help="Skip FBref + Transfermarkt scraping/import stages.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run validation only (skips all ingestion stages).",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Resume from a stage (fbref, transfermarkt, odds, features, validation).",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Include detailed missing samples in validation output.",
    )
    return parser.parse_args(list(argv))


def _filter_stages(args: argparse.Namespace) -> list[str]:
    stages = list(STAGE_SEQUENCE)
    if args.validate_only:
        return ["validation"]
    if args.skip_scraping:
        stages = [stage for stage in stages if stage not in {"fbref", "transfermarkt"}]
    if args.resume:
        resume = _normalize_stage(args.resume)
        if resume not in stages:
            raise ValueError(
                f"Resume stage '{args.resume}' not available after filters: {', '.join(stages)}"
            )
        start_index = stages.index(resume)
        stages = stages[start_index:]
    return stages


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)

    try:
        season_years = [_season_start_year(value) for value in args.seasons]
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    season_codes = [_season_code(value) for value in args.seasons]
    try:
        stages = _filter_stages(args)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Historical Backfill Orchestrator")
    print(f"Seasons: {', '.join(str(year) for year in season_years)}")
    print(f"Season codes: {', '.join(season_codes)}")
    print(f"Stages: {', '.join(stages)}")

    results: list[StageResult] = []
    validation_reports: dict[int, Optional[dict[str, float]]] = {}

    for stage in stages:
        label = STAGE_LABELS.get(stage, stage)
        print(f"\n== Stage: {label} ==")
        if stage == "fbref":
            results.append(_run_fbref(season_codes))
        elif stage == "transfermarkt":
            results.append(_run_transfermarkt())
        elif stage == "odds":
            results.append(_run_odds(season_codes))
        elif stage == "features":
            results.append(_run_features(season_years))
        elif stage == "validation":
            validation_results = _run_validation(season_years, args.detailed)
            results.extend(validation_results)
            for season in season_years:
                report_path = PROJECT_ROOT / f"data_completeness_report_{season}.json"
                validation_reports[season] = _load_completeness_summary(report_path)
        else:
            results.append(StageResult(label, False, "Unknown stage"))

        if results and not results[-1].success:
            print(f"Stage failed: {results[-1].name} ({results[-1].detail})")
            break

    print("\nFinal Report")
    for result in results:
        status = "OK" if result.success else "FAIL"
        print(f" {status} {result.name}: {result.detail}")

    if validation_reports:
        print("\nCompleteness Summary")
        for season, summary in validation_reports.items():
            if not summary:
                print(f" - {season}: report unavailable")
                continue
            print(
                " - {season}: fixtures={fixtures:.1%}, team_stats={team_match_stats:.1%}, "
                "lineups={lineups:.1%}, market_values={player_market_values:.1%}, odds={odds:.1%}".format(
                    season=season,
                    fixtures=summary["fixtures"],
                    team_match_stats=summary["team_match_stats"],
                    lineups=summary["lineups"],
                    player_market_values=summary["player_market_values"],
                    odds=summary["odds"],
                )
            )

    errors = [result for result in results if not result.success]
    if errors:
        print("\nErrors")
        for result in errors:
            print(f" - {result.name}: {result.detail}")
        return 1

    print("\nBackfill pipeline complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
