from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from typing import Dict, Iterable, List, Optional, Sequence

from src.validation.action_extractor import Action, ActionType, BetSelection
from src.validation.report_schema import (
    BaselineMetrics,
    BettingMetrics,
    CalibrationStats,
    NarrativeMetrics,
    Outcome,
    OutcomeMetrics,
    PromptVersionReport,
    ValidationReport,
)


@dataclass(frozen=True)
class ValidationRecord:
    prompt_version: str
    narrative_metrics: NarrativeMetrics
    outcome_metrics: OutcomeMetrics
    calibration_stats: CalibrationStats
    actions: Optional[List[Action]] = None
    odds_snapshots: Optional[List[Dict[str, object]]] = None
    outcomes: Optional[List[Outcome]] = None


class ValidationEngine:
    def __init__(self, records: Iterable[ValidationRecord]):
        self._records = list(records)
        self._baselines = self._build_baselines(self._records)

    def build_leaderboard(self) -> List[PromptVersionReport]:
        leaderboard = [
            PromptVersionReport(
                prompt_version=record.prompt_version,
                narrative_metrics=record.narrative_metrics,
                outcome_metrics=record.outcome_metrics,
                calibration_stats=record.calibration_stats,
                betting_metrics=self._build_betting_metrics(record),
                baselines=self._baselines,
            )
            for record in self._records
        ]
        leaderboard.sort(key=lambda entry: entry.prompt_version)
        return leaderboard

    def _build_betting_metrics(self, record: ValidationRecord) -> Optional[BettingMetrics]:
        actions = record.actions or []
        if not actions:
            return None
        odds_lookup = self._build_odds_lookup(record.odds_snapshots or [])
        outcomes = record.outcomes or []
        total_actions = len(actions)
        total_bets = sum(1 for action in actions if action.action_type == ActionType.BET_1X2)
        priced_bets = 0
        unpriced_bets = 0
        odds_used: List[float] = []
        profits: List[float] = []
        wins = 0
        for index, action in enumerate(actions):
            if action.action_type != ActionType.BET_1X2:
                continue
            odds = self._lookup_odds(odds_lookup, action)
            if odds is None:
                unpriced_bets += 1
                continue
            priced_bets += 1
            odds_used.append(odds)
            outcome = outcomes[index] if index < len(outcomes) else None
            profit = self._profit_for_bet(action.selection, outcome, odds)
            profits.append(profit)
            if profit > 0:
                wins += 1
        bet_rate = total_bets / total_actions if total_actions else 0.0
        avg_odds = mean(odds_used) if odds_used else None
        win_rate = wins / priced_bets if priced_bets else None
        roi = sum(profits) / priced_bets if priced_bets else None
        max_drawdown = self._max_drawdown(profits) if profits else None
        return BettingMetrics(
            total_actions=total_actions,
            total_bets=total_bets,
            bet_rate=bet_rate,
            avg_odds=avg_odds,
            win_rate=win_rate,
            roi=roi,
            max_drawdown=max_drawdown,
            unpriced_bets=unpriced_bets,
        )

    @classmethod
    def _build_baselines(
        cls, records: Sequence[ValidationRecord]
    ) -> Optional[BaselineMetrics]:
        if not records:
            return None
        outcome_sequences = [record.outcomes or [] for record in records]
        if not any(outcome_sequences):
            return None
        outcomes = [outcome for seq in outcome_sequences for outcome in seq]
        if not outcomes:
            return None
        total = len(outcomes)
        outcome_counts = {
            Outcome.HOME: sum(1 for outcome in outcomes if outcome == Outcome.HOME),
            Outcome.DRAW: sum(1 for outcome in outcomes if outcome == Outcome.DRAW),
            Outcome.AWAY: sum(1 for outcome in outcomes if outcome == Outcome.AWAY),
        }
        majority_accuracy = max(outcome_counts.values()) / total if total else None
        random_accuracy = 1.0 / len(Outcome) if total else None
        bookmaker = cls._build_bookmaker_baseline(records)
        return BaselineMetrics(
            random_baseline_accuracy=random_accuracy,
            majority_class_accuracy=majority_accuracy,
            bookmaker_accuracy=bookmaker[0],
            bookmaker_expected_roi=bookmaker[1],
            bookmaker_avg_odds=bookmaker[2],
        )

    @classmethod
    def _build_bookmaker_baseline(
        cls, records: Sequence[ValidationRecord]
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        fixtures: Dict[str, Dict[str, object]] = {}
        for record in records:
            for snapshot in record.odds_snapshots or []:
                fixture_id = snapshot.get("fixture_id")
                market_key = snapshot.get("market_key")
                selection_key = snapshot.get("selection_key")
                odds_value = cls._parse_odds_value(snapshot.get("odds_decimal"))
                if not fixture_id or not market_key or not selection_key:
                    continue
                if str(market_key) != "1X2" or odds_value is None:
                    continue
                fixture_entry = fixtures.setdefault(
                    str(fixture_id), {"odds": {}, "outcome": None}
                )
                odds_map = fixture_entry["odds"]
                if isinstance(odds_map, dict):
                    odds_map[str(selection_key)] = odds_value

        for record in records:
            outcomes = record.outcomes or []
            for index, action in enumerate(record.actions or []):
                if action.fixture_id is None:
                    continue
                if index >= len(outcomes):
                    continue
                fixture_entry = fixtures.setdefault(
                    str(action.fixture_id), {"odds": {}, "outcome": None}
                )
                if isinstance(fixture_entry, dict):
                    fixture_entry["outcome"] = outcomes[index]

        if not fixtures:
            return None, None, None

        correct = 0
        profits: List[float] = []
        odds_used: List[float] = []
        priced_total = 0
        for fixture_data in fixtures.values():
            outcome = fixture_data.get("outcome")
            odds_map = fixture_data.get("odds")
            if not isinstance(outcome, Outcome):
                continue
            if not isinstance(odds_map, dict):
                continue
            if not odds_map:
                continue
            selection_key, odds = min(odds_map.items(), key=lambda item: item[1])
            if odds <= 0:
                continue
            priced_total += 1
            odds_used.append(float(odds))
            if selection_key == outcome.value:
                correct += 1
            profits.append(cls._profit_for_baseline(selection_key, outcome, float(odds)))

        accuracy = correct / priced_total if priced_total else None
        roi = sum(profits) / priced_total if priced_total else None
        avg_odds = mean(odds_used) if odds_used else None
        return accuracy, roi, avg_odds

    @staticmethod
    def _parse_odds_value(odds_decimal: object) -> Optional[float]:
        if odds_decimal is None:
            return None
        if isinstance(odds_decimal, (int, float)):
            return float(odds_decimal)
        if isinstance(odds_decimal, str):
            try:
                return float(odds_decimal)
            except ValueError:
                return None
        return None

    @staticmethod
    def _profit_for_baseline(
        selection_key: str, outcome: Outcome, odds: float
    ) -> float:
        if selection_key == outcome.value:
            return odds - 1.0
        return -1.0

    @staticmethod
    def _build_odds_lookup(
        odds_snapshots: List[Dict[str, object]]
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        lookup: Dict[str, Dict[str, Dict[str, float]]] = {}
        for snapshot in odds_snapshots:
            fixture_id = snapshot.get("fixture_id")
            market_key = snapshot.get("market_key")
            selection_key = snapshot.get("selection_key")
            odds_decimal = snapshot.get("odds_decimal")
            odds_value: Optional[float] = None
            if not fixture_id or not market_key or not selection_key:
                continue
            if odds_decimal is None:
                continue
            if isinstance(odds_decimal, (int, float)):
                odds_value = float(odds_decimal)
            elif isinstance(odds_decimal, str):
                try:
                    odds_value = float(odds_decimal)
                except ValueError:
                    odds_value = None
            if odds_value is None:
                continue
            fixture_lookup = lookup.setdefault(str(fixture_id), {})
            market_lookup = fixture_lookup.setdefault(str(market_key), {})
            market_lookup[str(selection_key)] = odds_value
        return lookup

    @staticmethod
    def _lookup_odds(
        odds_lookup: Dict[str, Dict[str, Dict[str, float]]],
        action: Action,
    ) -> Optional[float]:
        if not action.market_key or not action.selection_key or not action.fixture_id:
            return None
        fixture_lookup = odds_lookup.get(str(action.fixture_id))
        if fixture_lookup is None:
            return None
        market_lookup = fixture_lookup.get(action.market_key)
        if market_lookup is None:
            return None
        return market_lookup.get(action.selection_key)

    @staticmethod
    def _profit_for_bet(
        selection: Optional[BetSelection],
        outcome: Optional[Outcome],
        odds: float,
    ) -> float:
        if selection is None or outcome is None:
            return 0.0
        if selection.name == outcome.name:
            return odds - 1.0
        return -1.0

    @staticmethod
    def _max_drawdown(profits: List[float]) -> float:
        peak = 0.0
        max_drawdown = 0.0
        cumulative = 0.0
        for profit in profits:
            cumulative += profit
            peak = max(peak, cumulative)
            drawdown = peak - cumulative
            max_drawdown = max(max_drawdown, drawdown)
        return max_drawdown

    def build_report(self, season: str, league: str, round_range: str) -> ValidationReport:
        return ValidationReport(
            season=season,
            league=league,
            round_range=round_range,
            leaderboard=self.build_leaderboard(),
            baselines=self._baselines,
        )

    def save_report(
        self, report: ValidationReport, path: Path = Path("validation_report.json")
    ) -> None:
        path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
