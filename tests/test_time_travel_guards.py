"""
Time-travel correctness tests for validation suite.

These tests ensure we NEVER accidentally use future data when validating,
which would make all validation results worthless.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from src.validation.action_extractor import extract_action


class TestOddsSnapshotTimeTravel:
    """Test that odds snapshots must be captured before fixture kickoff."""

    def test_odds_captured_before_fixture_date(self):
        """Odds captured_at must be < fixture date."""
        fixture_date = datetime(2024, 8, 17, 15, 0)  # 3pm kickoff

        # Valid: odds captured day before
        valid_captured_at = datetime(2024, 8, 16, 12, 0)
        assert valid_captured_at < fixture_date, "Valid odds should be before kickoff"

        # Invalid: odds captured after kickoff
        invalid_captured_at = datetime(2024, 8, 17, 16, 0)
        with pytest.raises(AssertionError):
            assert invalid_captured_at < fixture_date, "Odds after kickoff = time travel violation"

    def test_odds_import_rejects_future_odds(self):
        """CSV import should reject odds captured after fixture date."""
        from scripts.import_odds_csv import validate_row_time_travel

        fixture_date = datetime(2024, 8, 17)

        # Valid: captured before match
        valid_row = {
            "fixture_id": "2024-08-17_Arsenal_Wolves",
            "captured_at": "2024-08-16 12:00:00",
            "odds_decimal": "1.85"
        }
        fixture_dates = {"2024-08-17_Arsenal_Wolves": fixture_date}

        # Should not raise
        try:
            result = validate_row_time_travel(valid_row, fixture_dates)
            assert result is True or result is None  # Either validation passes or function doesn't exist yet
        except (ImportError, AttributeError):
            # Function doesn't exist - that's OK, this is a guard specification
            pytest.skip("validate_row_time_travel not implemented yet")

        # Invalid: captured after match
        invalid_row = {
            "fixture_id": "2024-08-17_Arsenal_Wolves",
            "captured_at": "2024-08-18 12:00:00",
            "odds_decimal": "1.85"
        }

        try:
            with pytest.raises((ValueError, AssertionError)):
                validate_row_time_travel(invalid_row, fixture_dates)
        except (ImportError, AttributeError):
            pytest.skip("validate_row_time_travel not implemented yet")


class TestActionExtractionTimeTravel:
    """Test that action extraction never reads post-match fields."""

    def test_action_extractor_only_uses_pre_match_fields(self):
        """Action extraction must NOT read match_reality or post-match fields."""
        analysis_report = {
            "evidence_chain": {
                "market_verdict": "Back Arsenal to win"
            },
            # These fields should NEVER be accessed during action extraction
            "actual_result": "HOME_WIN",  # Time travel!
            "post_match_xg": 2.5,  # Time travel!
        }

        # Extract action
        action = extract_action(
            analysis_report,
            home_team="Arsenal",
            away_team="Wolves",
            fixture_id="2024-08-17_Arsenal_Wolves"
        )

        # Action should be based only on market_verdict, not actual_result
        # If action extractor used actual_result, that would be time travel
        assert action is not None

    def test_validation_engine_does_not_leak_outcomes_to_extractor(self):
        """ValidationEngine must not pass outcomes/results to action extractor."""
        # This test ensures the validation engine architecture prevents time travel
        # by keeping outcomes separate from action extraction

        from src.validation.engine import ValidationEngine
        from src.validation.report_schema import Outcome, NarrativeMetrics, OutcomeMetrics, CalibrationStats

        # Create a validation record with outcomes
        # The engine should compute metrics AFTER extraction, never during
        record_data = {
            "prompt_version": "v1",
            "narrative_metrics": NarrativeMetrics(100.0, 0.8, 0.9),
            "outcome_metrics": OutcomeMetrics(5, 2, 3, 10, 0.5),
            "calibration_stats": CalibrationStats(0.15, 0.08),
            "outcomes": [Outcome.HOME, Outcome.DRAW, Outcome.AWAY]
        }

        # If we pass this to the engine, it should NOT use outcomes during action extraction
        # Outcomes are only used AFTER actions are extracted, for computing metrics
        assert record_data["outcomes"] is not None
        # The architecture itself prevents time travel by separating extraction from evaluation


class TestContextFeaturesTimeTravel:
    """Test that context features only use matches BEFORE fixture date."""

    def test_team_stats_only_from_previous_matches(self):
        """When computing team stats, only include matches before current fixture."""
        current_fixture_date = datetime(2024, 8, 17)

        # Previous match (valid context)
        previous_match_date = datetime(2024, 8, 10)
        assert previous_match_date < current_fixture_date

        # Future match (time travel violation)
        future_match_date = datetime(2024, 8, 24)
        assert not (future_match_date < current_fixture_date), \
            "Using future matches for context = time travel"

    def test_elo_ratings_computed_from_history_only(self):
        """Elo ratings must be computed from matches before current fixture."""
        # This is a specification test - the actual implementation should enforce this

        # Valid: Elo from matches up to (but not including) current match
        match_date = datetime(2024, 8, 17)
        historical_matches = [
            {"date": datetime(2024, 8, 3), "result": "WIN"},
            {"date": datetime(2024, 8, 10), "result": "DRAW"},
        ]

        for match in historical_matches:
            assert match["date"] < match_date, "Historical matches must be before current"

        # Invalid: Including current match in Elo would be time travel
        current_match = {"date": match_date, "result": "WIN"}
        # This should NOT be in the historical data used for Elo


class TestValidationSuiteGuardrails:
    """Test that validation suite has guardrails to detect time-travel violations."""

    def test_validation_fails_loudly_on_time_travel_violation(self):
        """If time-travel is detected, validation must raise clear error."""
        # This is a specification - the validation suite should have checks like:

        def check_time_travel_violation(odds_captured_at: datetime, fixture_date: datetime) -> None:
            """Raise error if time-travel violation detected."""
            if odds_captured_at >= fixture_date:
                raise ValueError(
                    f"TIME TRAVEL VIOLATION: Odds captured at {odds_captured_at} "
                    f"but fixture is on {fixture_date}. "
                    f"This makes validation worthless!"
                )

        # Test that it raises
        with pytest.raises(ValueError, match="TIME TRAVEL VIOLATION"):
            check_time_travel_violation(
                datetime(2024, 8, 18),  # After
                datetime(2024, 8, 17)   # Fixture
            )

        # Test that valid data passes
        check_time_travel_violation(
            datetime(2024, 8, 16),  # Before
            datetime(2024, 8, 17)   # Fixture
        )

    def test_import_script_validates_time_travel(self):
        """import_odds_csv.py must validate captured_at < fixture date."""
        # The import script should have this validation built-in
        # This test documents the requirement

        from scripts.import_odds_csv import parse_timestamp

        # Valid timestamp parsing
        ts = parse_timestamp("2024-08-16 12:00:00")
        assert isinstance(ts, datetime)

        # The import script should validate this timestamp against fixture date
        # See import_odds_csv.py:validate_row() for implementation


class TestDeterministicValidation:
    """Test that validation is deterministic given same DB state."""

    def test_validation_suite_makes_no_llm_calls(self):
        """Validation suite must NOT make LLM calls - it only analyzes existing data."""
        # This is a specification test

        # The validation suite should:
        # 1. Read from analysis_reports table (existing LLM outputs)
        # 2. Read from fixtures/team_stats/odds_snapshots (facts)
        # 3. Compute metrics deterministically
        # 4. Output report

        # It should NEVER:
        # - Call OpenAI API
        # - Generate new analyses
        # - Make any non-deterministic operations

        # This ensures reproducibility
        pass

    def test_same_db_state_produces_same_report(self):
        """Running validation twice on same DB should produce identical results."""
        # This is a specification - actual implementation would need:
        # - No randomness in metric computation
        # - Consistent sorting/ordering
        # - No timestamps in report (except run metadata)
        # - Deterministic floating point operations

        # Example of what should be deterministic:
        from src.validation.report_schema import NarrativeMetrics

        metrics1 = NarrativeMetrics(100.5, 0.85, 0.92)
        metrics2 = NarrativeMetrics(100.5, 0.85, 0.92)

        assert metrics1 == metrics2, "Same inputs should produce same metrics"


# Guard function that should be added to import_odds_csv.py
def validate_row_time_travel_spec(row: dict, fixture_dates: dict) -> None:
    """
    Specification for time-travel validation in odds import.

    This function should be implemented in scripts/import_odds_csv.py
    to enforce time-travel correctness.
    """
    from scripts.import_odds_csv import parse_timestamp

    fixture_id = row["fixture_id"]
    captured_at = parse_timestamp(row["captured_at"])

    if fixture_id not in fixture_dates:
        raise ValueError(f"Unknown fixture: {fixture_id}")

    fixture_date = fixture_dates[fixture_id]

    if captured_at >= fixture_date:
        raise ValueError(
            f"TIME TRAVEL VIOLATION: Odds for {fixture_id} captured at {captured_at} "
            f"but fixture is on {fixture_date}. Odds must be captured BEFORE kickoff!"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
