from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.validation.action_extractor import Action, extract_action
from src.validation.engine import ValidationEngine, ValidationRecord
from src.validation.report_schema import (
    CalibrationStats,
    NarrativeMetrics,
    Outcome,
    OutcomeMetrics,
    ValidationReport,
)


@dataclass(frozen=True)
class ValidationRow:
    fixture_id: str
    home_team: str
    away_team: str
    prompt_version: str
    confidence: Optional[int]
    predicted_score: Optional[str]
    full_json: Dict[str, Any]
    narrative_score: Optional[int]
    score_accuracy: Optional[bool]
    tip_accuracy: Optional[bool]
    actual_home: Optional[int]
    actual_away: Optional[int]


def _parse_full_json(value: object) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return {}


def _parse_predicted_outcome(score: Optional[str]) -> Optional[Outcome]:
    if not score:
        return None
    if not isinstance(score, str):
        return None
    try:
        parts = score.split("-")
        if len(parts) != 2:
            return None
        home = int(parts[0].strip())
        away = int(parts[1].strip())
    except (ValueError, TypeError):
        return None
    return _outcome_from_scores(home, away)


def _outcome_from_scores(home: Optional[int], away: Optional[int]) -> Optional[Outcome]:
    if home is None or away is None:
        return None
    if home > away:
        return Outcome.HOME
    if home < away:
        return Outcome.AWAY
    return Outcome.DRAW


def _extract_narrative_text(full_json: Dict[str, Any]) -> str:
    narrative = full_json.get("narrative")
    pieces: List[str] = []
    if isinstance(narrative, dict):
        for value in narrative.values():
            if isinstance(value, str):
                pieces.append(value)
    elif isinstance(narrative, str):
        pieces.append(narrative)

    for key in ("analysis", "summary", "headline"):
        value = full_json.get(key)
        if isinstance(value, str):
            pieces.append(value)

    return " ".join(piece.strip() for piece in pieces if piece and piece.strip())


def _word_count(text: str) -> int:
    if not text:
        return 0
    return len(text.split())


def _build_narrative_metrics(rows: Sequence[ValidationRow]) -> NarrativeMetrics:
    word_counts = [_word_count(_extract_narrative_text(row.full_json)) for row in rows]
    avg_word_count = mean(word_counts) if word_counts else 0.0

    scores = [row.narrative_score for row in rows if row.narrative_score is not None]
    avg_score = mean(scores) if scores else 0.0
    normalized = avg_score / 100.0 if avg_score else 0.0

    return NarrativeMetrics(
        avg_word_count=avg_word_count,
        factual_consistency_score=normalized,
        clarity_score=normalized,
    )


def _build_outcome_metrics(rows: Sequence[ValidationRow]) -> OutcomeMetrics:
    actual_outcomes = [
        _outcome_from_scores(row.actual_home, row.actual_away) for row in rows
    ]
    outcomes = [outcome for outcome in actual_outcomes if outcome is not None]

    wins = sum(1 for outcome in outcomes if outcome is Outcome.HOME)
    draws = sum(1 for outcome in outcomes if outcome is Outcome.DRAW)
    losses = sum(1 for outcome in outcomes if outcome is Outcome.AWAY)
    total = len(outcomes)

    correct = 0
    for row, actual in zip(rows, actual_outcomes):
        predicted = _parse_predicted_outcome(row.predicted_score)
        if predicted is None or actual is None:
            continue
        if predicted == actual:
            correct += 1
    accuracy = correct / total if total else 0.0

    return OutcomeMetrics(
        wins=wins,
        draws=draws,
        losses=losses,
        total=total,
        accuracy=accuracy,
    )


def _build_calibration_stats(rows: Sequence[ValidationRow]) -> CalibrationStats:
    samples: List[tuple[float, bool]] = []
    brier_scores: List[float] = []

    for row in rows:
        actual = _outcome_from_scores(row.actual_home, row.actual_away)
        predicted = _parse_predicted_outcome(row.predicted_score)
        if actual is None or predicted is None:
            continue
        if row.confidence is None:
            continue
        p_pred = max(0.0, min(row.confidence / 100.0, 1.0))
        remaining = (1.0 - p_pred) / 2.0
        probabilities = {
            Outcome.HOME: remaining,
            Outcome.DRAW: remaining,
            Outcome.AWAY: remaining,
        }
        probabilities[predicted] = p_pred
        brier = 0.0
        for outcome, probability in probabilities.items():
            actual_value = 1.0 if outcome == actual else 0.0
            brier += (probability - actual_value) ** 2
        brier_scores.append(brier)
        samples.append((p_pred, predicted == actual))

    brier_score = mean(brier_scores) if brier_scores else 0.0
    ece = _expected_calibration_error(samples)
    return CalibrationStats(
        brier_score=brier_score,
        expected_calibration_error=ece,
    )


def _expected_calibration_error(samples: Sequence[tuple[float, bool]]) -> float:
    if not samples:
        return 0.0
    bins: Dict[int, List[tuple[float, bool]]] = defaultdict(list)
    for confidence, correct in samples:
        bucket = min(int(confidence * 10), 9)
        bins[bucket].append((confidence, correct))

    total = len(samples)
    ece = 0.0
    for bucket_samples in bins.values():
        if not bucket_samples:
            continue
        bucket_total = len(bucket_samples)
        avg_conf = mean(sample[0] for sample in bucket_samples)
        accuracy = sum(1 for _, correct in bucket_samples if correct) / bucket_total
        ece += abs(accuracy - avg_conf) * (bucket_total / total)
    return ece


def _build_actions(rows: Sequence[ValidationRow]) -> List[Action]:
    actions: List[Action] = []
    for row in rows:
        action = extract_action(
            row.full_json,
            home_team=row.home_team,
            away_team=row.away_team,
            fixture_id=row.fixture_id,
        )
        actions.append(action)
    return actions


def _build_outcome_sequence(rows: Sequence[ValidationRow]) -> List[Optional[Outcome]]:
    return [_outcome_from_scores(row.actual_home, row.actual_away) for row in rows]


def _fetch_validation_rows(
    season: str,
    league: str,
    from_round: int,
    to_round: int,
    prompt_version: Optional[str],
) -> List[ValidationRow]:
    conn = get_connection()
    if not conn:
        raise RuntimeError("Database connection failed")

    query = """
        SELECT
            f.id,
            f.home_team,
            f.away_team,
            ar.prompt_version,
            ar.confidence,
            ar.predicted_score,
            ar.full_json,
            ae.narrative_score,
            ae.score_accuracy,
            ae.tip_accuracy,
            COALESCE(mr.score_home, f.home_score) AS actual_home,
            COALESCE(mr.score_away, f.away_score) AS actual_away
        FROM fixtures f
        JOIN analysis_reports ar ON f.id = ar.fixture_id
        LEFT JOIN analysis_evaluations ae ON ar.id = ae.report_id
        LEFT JOIN match_reality mr ON f.id = mr.fixture_id
        WHERE f.season = %s
          AND f.league = %s
          AND f.status = 'FINISHED'
          AND f.round BETWEEN %s AND %s
    """
    params: List[object] = [season, league, from_round, to_round]
    if prompt_version:
        query += " AND ar.prompt_version = %s"
        params.append(prompt_version)
    query += " ORDER BY f.date ASC, ar.prompt_version ASC"

    rows: List[ValidationRow] = []
    with conn.cursor() as cur:
        cur.execute(query, tuple(params))
        for row in cur.fetchall():
            rows.append(
                ValidationRow(
                    fixture_id=row[0],
                    home_team=row[1],
                    away_team=row[2],
                    prompt_version=row[3],
                    confidence=row[4],
                    predicted_score=row[5],
                    full_json=_parse_full_json(row[6]),
                    narrative_score=row[7],
                    score_accuracy=row[8],
                    tip_accuracy=row[9],
                    actual_home=row[10],
                    actual_away=row[11],
                )
            )
    conn.close()
    return rows


def _fetch_odds_snapshots(fixture_ids: Iterable[str]) -> List[Dict[str, object]]:
    fixture_list = [fixture_id for fixture_id in fixture_ids if fixture_id]
    if not fixture_list:
        return []
    conn = get_connection()
    if not conn:
        raise RuntimeError("Database connection failed")

    query = """
        SELECT fixture_id, market_key, selection_key, odds_decimal, captured_at, source
        FROM odds_snapshots
        WHERE fixture_id = ANY(%s)
    """
    with conn.cursor() as cur:
        cur.execute(query, (fixture_list,))
        snapshots = [
            {
                "fixture_id": row[0],
                "market_key": row[1],
                "selection_key": row[2],
                "odds_decimal": float(row[3]) if row[3] is not None else None,
                "captured_at": row[4],
                "source": row[5],
            }
            for row in cur.fetchall()
        ]
    conn.close()
    return snapshots


def _group_rows_by_prompt(rows: Sequence[ValidationRow]) -> Dict[str, List[ValidationRow]]:
    grouped: Dict[str, List[ValidationRow]] = defaultdict(list)
    for row in rows:
        grouped[row.prompt_version].append(row)
    return grouped


def _build_records(rows: Sequence[ValidationRow]) -> List[ValidationRecord]:
    grouped = _group_rows_by_prompt(rows)
    fixture_ids = {row.fixture_id for row in rows}
    odds_snapshots = _fetch_odds_snapshots(fixture_ids)

    records: List[ValidationRecord] = []
    for prompt_version, prompt_rows in sorted(grouped.items()):
        records.append(
            ValidationRecord(
                prompt_version=prompt_version,
                narrative_metrics=_build_narrative_metrics(prompt_rows),
                outcome_metrics=_build_outcome_metrics(prompt_rows),
                calibration_stats=_build_calibration_stats(prompt_rows),
                actions=_build_actions(prompt_rows),
                odds_snapshots=odds_snapshots,
                outcomes=_build_outcome_sequence(prompt_rows),
            )
        )
    return records


def _format_percent(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _format_decimal(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _build_markdown_summary(report: ValidationReport, path: Path) -> None:
    lines = [
        "# Validation Report",
        "",
        f"Season: {report.season}",
        f"League: {report.league}",
        f"Round Range: {report.round_range}",
        "",
        "## Leaderboard",
        "",
        "| Prompt Version | Accuracy | Bet Rate | ROI | Win Rate | Avg Odds | Total Bets |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for entry in report.leaderboard:
        betting = entry.betting_metrics
        if betting is None:
            lines.append(
                f"| {entry.prompt_version} | {_format_percent(entry.outcome_metrics.accuracy)}"
                " | n/a | n/a | n/a | n/a | 0 |"
            )
            continue
        lines.append(
            "| {prompt_version} | {accuracy} | {bet_rate} | {roi} | {win_rate} | {avg_odds} | {total_bets} |".format(
                prompt_version=entry.prompt_version,
                accuracy=_format_percent(entry.outcome_metrics.accuracy),
                bet_rate=_format_percent(betting.bet_rate),
                roi=_format_percent(betting.roi),
                win_rate=_format_percent(betting.win_rate),
                avg_odds=_format_decimal(betting.avg_odds),
                total_bets=betting.total_bets,
            )
        )

    if report.baselines:
        lines.extend([
            "",
            "## Baselines",
            "",
            "| Random Accuracy | Majority Accuracy | Bookmaker Accuracy | Bookmaker ROI |",
            "| --- | --- | --- | --- |",
            "| {random_acc} | {majority_acc} | {bookmaker_acc} | {bookmaker_roi} |".format(
                random_acc=_format_percent(report.baselines.random_baseline_accuracy),
                majority_acc=_format_percent(report.baselines.majority_class_accuracy),
                bookmaker_acc=_format_percent(report.baselines.bookmaker_accuracy),
                bookmaker_roi=_format_percent(report.baselines.bookmaker_expected_roi),
            ),
        ])

    path.write_text("\n".join(lines), encoding="utf-8")


def run_suite(
    season: str,
    league: str,
    from_round: int,
    to_round: int,
    prompt_version: Optional[str],
) -> ValidationReport:
    rows = _fetch_validation_rows(season, league, from_round, to_round, prompt_version)
    if not rows:
        raise RuntimeError("No validation rows found for the given filters")

    records = _build_records(rows)
    engine = ValidationEngine(records=records)
    report = engine.build_report(
        season=season,
        league=league,
        round_range=f"{from_round}-{to_round}",
    )

    engine.save_report(report, PROJECT_ROOT / "validation_report.json")
    _build_markdown_summary(report, PROJECT_ROOT / "validation_report.md")
    return report


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Run validation suite")
    parser.add_argument("--season", required=True)
    parser.add_argument("--league", required=True)
    parser.add_argument("--from-round", required=True, type=int)
    parser.add_argument("--to-round", required=True, type=int)
    parser.add_argument("--prompt-version", default=None)
    args = parser.parse_args(argv)

    if args.from_round > args.to_round:
        raise SystemExit("from-round must be <= to-round")

    run_suite(
        season=args.season,
        league=args.league,
        from_round=args.from_round,
        to_round=args.to_round,
        prompt_version=args.prompt_version,
    )
    print("✅ Validation report generated.")
    print(f"   - {PROJECT_ROOT / 'validation_report.json'}")
    print(f"   - {PROJECT_ROOT / 'validation_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
