#!/usr/bin/env python3
"""
Test script for the Agents module (Anti-Hallucination Architecture).

This tests:
1. Extraction schemas and parsing
2. Validation layer cross-checks

Run with: python3 scripts/test_agents.py
"""

import sys
from pathlib import Path
from datetime import date, datetime
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Import only the schema and validator modules (no DB dependencies)
from src.agents.extraction_schemas import (
    InjuryExtraction, FormExtraction, TablePositionExtraction,
    HeadToHeadExtraction, FormMatchExtraction,
    dict_to_injury_extraction, dict_to_form_extraction,
    dict_to_table_extraction, dict_to_h2h_extraction,
    extraction_to_json
)
from src.agents.extraction_validator import (
    ExtractionValidator, ValidationResult, validate_extraction
)


def test_schemas():
    """Test extraction schema dataclasses."""
    print("\n" + "=" * 60)
    print("TEST: Extraction Schemas")
    print("=" * 60)

    # Test InjuryExtraction
    injury = InjuryExtraction(
        player_name="Bukayo Saka",
        position="FWD",
        injury_type="hamstring",
        expected_return="2 weeks",
        is_key_player=True,
        source_quote="Arteta confirmed Saka will miss the next few games"
    )
    print(f"\n1. InjuryExtraction: {injury.player_name} ({injury.position})")
    print(f"   Injury: {injury.injury_type}, Return: {injury.expected_return}")

    # Test FormMatchExtraction
    match = FormMatchExtraction(
        opponent="Chelsea",
        result="W",
        score="2-0",
        venue="H",
        date="2024-01-15"
    )
    print(f"\n2. FormMatchExtraction: vs {match.opponent} ({match.venue}) - {match.result} {match.score}")

    # Test FormExtraction
    form = FormExtraction(
        last_5=[
            FormMatchExtraction("Chelsea", "W", "2-0", "H", "2024-01-15"),
            FormMatchExtraction("Liverpool", "D", "1-1", "A", "2024-01-10"),
            FormMatchExtraction("Brighton", "W", "3-1", "H", "2024-01-06"),
            FormMatchExtraction("Man United", "L", "0-1", "A", "2024-01-02"),
            FormMatchExtraction("Newcastle", "W", "2-1", "H", "2023-12-28"),
        ],
        current_streak="1W",
        goals_scored_last_5=8,
        goals_conceded_last_5=4
    )
    print(f"\n3. FormExtraction: {len(form.last_5)} matches, {form.goals_scored_last_5} GF, {form.goals_conceded_last_5} GA")

    # Test TablePositionExtraction
    table = TablePositionExtraction(
        position=2,
        points=45,
        played=20,
        won=14,
        drawn=3,
        lost=3,
        goals_for=42,
        goals_against=18,
        goal_difference=24,
        form_string="WWDLW"
    )
    print(f"\n4. TablePositionExtraction: {table.position}th, {table.points}pts ({table.won}W-{table.drawn}D-{table.lost}L)")

    # Test JSON serialization
    print(f"\n5. JSON serialization:")
    print(f"   Injury JSON preview: {extraction_to_json(injury)[:100]}...")

    print("\n[PASS] All schema tests passed")
    return True


def test_validation_injuries():
    """Test injury validation."""
    print("\n" + "=" * 60)
    print("TEST: Injury Validation")
    print("=" * 60)

    validator = ExtractionValidator(match_date=date(2024, 1, 20))

    # Valid injury
    valid_injury = {
        "player_name": "Bukayo Saka",
        "position": "FWD",
        "injury_type": "hamstring",
        "expected_return": "2 weeks",
        "is_key_player": True
    }
    result = validator.validate_injury(valid_injury)
    print(f"\n1. Valid injury: is_valid={result.is_valid}, errors={result.errors}")
    assert result.is_valid, f"Valid injury should pass: {result.errors}"

    # Invalid position
    invalid_position = {
        "player_name": "Test Player",
        "position": "STRIKER",  # Wrong - should be FWD
        "injury_type": "knee"
    }
    result = validator.validate_injury(invalid_position)
    print(f"2. Invalid position: is_valid={result.is_valid}, errors={result.errors}")
    assert not result.is_valid, "Invalid position should fail"

    # Missing player name
    missing_name = {
        "player_name": "",
        "position": "MID",
        "injury_type": "illness"
    }
    result = validator.validate_injury(missing_name)
    print(f"3. Missing name: is_valid={result.is_valid}, errors={result.errors}")
    assert not result.is_valid, "Missing name should fail"

    print("\n[PASS] Injury validation tests passed")
    return True


def test_validation_form():
    """Test form validation with cross-checks."""
    print("\n" + "=" * 60)
    print("TEST: Form Validation (Cross-Checks)")
    print("=" * 60)

    validator = ExtractionValidator(match_date=date(2024, 1, 20))

    # Valid form with correct totals
    valid_form = {
        "last_5": [
            {"opponent": "Chelsea", "result": "W", "score": "2-0", "venue": "H", "date": "2024-01-15"},
            {"opponent": "Liverpool", "result": "D", "score": "1-1", "venue": "A", "date": "2024-01-10"},
            {"opponent": "Brighton", "result": "W", "score": "3-1", "venue": "H", "date": "2024-01-06"},
            {"opponent": "Man United", "result": "L", "score": "0-1", "venue": "A", "date": "2024-01-02"},
            {"opponent": "Newcastle", "result": "W", "score": "2-1", "venue": "H", "date": "2023-12-28"},
        ],
        "current_streak": "1W",
        "goals_scored_last_5": 8,  # 2+1+3+0+2 = 8
        "goals_conceded_last_5": 4  # 0+1+1+1+1 = 4
    }
    result = validator.validate_form(valid_form)
    print(f"\n1. Valid form: is_valid={result.is_valid}")
    print(f"   Errors: {result.errors}")
    assert result.is_valid, f"Valid form should pass: {result.errors}"

    # Invalid: goals don't match scores
    invalid_goals = {
        "last_5": [
            {"opponent": "Chelsea", "result": "W", "score": "2-0", "venue": "H"},
            {"opponent": "Liverpool", "result": "D", "score": "1-1", "venue": "A"},
            {"opponent": "Brighton", "result": "W", "score": "3-1", "venue": "H"},
            {"opponent": "Man United", "result": "L", "score": "0-1", "venue": "A"},
            {"opponent": "Newcastle", "result": "W", "score": "2-1", "venue": "H"},
        ],
        "goals_scored_last_5": 10,  # Wrong! Should be 8
        "goals_conceded_last_5": 4
    }
    result = validator.validate_form(invalid_goals)
    print(f"\n2. Invalid goals total: is_valid={result.is_valid}")
    print(f"   Errors: {result.errors}")
    assert not result.is_valid, "Invalid goals should fail"
    assert any("goals_scored" in e for e in result.errors), "Should mention goals_scored mismatch"

    # Invalid: result doesn't match score
    invalid_result = {
        "last_5": [
            {"opponent": "Chelsea", "result": "W", "score": "0-2", "venue": "H"},  # W with 0-2 is wrong!
            {"opponent": "Liverpool", "result": "D", "score": "1-1", "venue": "A"},
            {"opponent": "Brighton", "result": "W", "score": "3-1", "venue": "H"},
            {"opponent": "Man United", "result": "L", "score": "0-1", "venue": "A"},
            {"opponent": "Newcastle", "result": "W", "score": "2-1", "venue": "H"},
        ],
        "goals_scored_last_5": 6,
        "goals_conceded_last_5": 6
    }
    result = validator.validate_form(invalid_result)
    print(f"\n3. Result/score mismatch: is_valid={result.is_valid}")
    print(f"   Errors: {result.errors}")
    assert not result.is_valid, "Result/score mismatch should fail"
    assert any("doesn't match result" in e for e in result.errors), "Should mention result mismatch"

    # Invalid: only 3 matches
    too_few = {
        "last_5": [
            {"opponent": "Chelsea", "result": "W", "score": "2-0", "venue": "H"},
            {"opponent": "Liverpool", "result": "D", "score": "1-1", "venue": "A"},
            {"opponent": "Brighton", "result": "W", "score": "3-1", "venue": "H"},
        ],
        "goals_scored_last_5": 6,
        "goals_conceded_last_5": 2
    }
    result = validator.validate_form(too_few)
    print(f"\n4. Too few matches: is_valid={result.is_valid}")
    print(f"   Errors: {result.errors}")
    assert not result.is_valid, "Too few matches should fail"

    print("\n[PASS] Form validation tests passed")
    return True


def test_validation_table():
    """Test table position validation with cross-checks."""
    print("\n" + "=" * 60)
    print("TEST: Table Position Validation (Cross-Checks)")
    print("=" * 60)

    validator = ExtractionValidator()

    # Valid table position
    valid_table = {
        "position": 2,
        "points": 45,  # 14*3 + 3*1 = 45
        "played": 20,  # 14+3+3 = 20
        "won": 14,
        "drawn": 3,
        "lost": 3,
        "goals_for": 42,
        "goals_against": 18,
        "goal_difference": 24,  # 42-18 = 24
        "form_string": "WWDLW"
    }
    result = validator.validate_table_position(valid_table)
    print(f"\n1. Valid table: is_valid={result.is_valid}")
    assert result.is_valid, f"Valid table should pass: {result.errors}"

    # Invalid: points don't match W/D/L
    invalid_points = {
        "position": 2,
        "points": 50,  # Wrong! 14*3 + 3*1 = 45
        "played": 20,
        "won": 14,
        "drawn": 3,
        "lost": 3,
        "goals_for": 42,
        "goals_against": 18,
        "goal_difference": 24
    }
    result = validator.validate_table_position(invalid_points)
    print(f"\n2. Points mismatch: is_valid={result.is_valid}")
    print(f"   Errors: {result.errors}")
    assert not result.is_valid, "Points mismatch should fail"
    assert any("Points" in e and "don't match" in e for e in result.errors)

    # Invalid: played doesn't match W+D+L
    invalid_played = {
        "position": 2,
        "points": 45,
        "played": 22,  # Wrong! 14+3+3 = 20
        "won": 14,
        "drawn": 3,
        "lost": 3,
        "goals_for": 42,
        "goals_against": 18,
        "goal_difference": 24
    }
    result = validator.validate_table_position(invalid_played)
    print(f"\n3. Played mismatch: is_valid={result.is_valid}")
    print(f"   Errors: {result.errors}")
    assert not result.is_valid, "Played mismatch should fail"

    # Invalid: goal difference doesn't match GF-GA
    invalid_gd = {
        "position": 2,
        "points": 45,
        "played": 20,
        "won": 14,
        "drawn": 3,
        "lost": 3,
        "goals_for": 42,
        "goals_against": 18,
        "goal_difference": 30  # Wrong! 42-18 = 24
    }
    result = validator.validate_table_position(invalid_gd)
    print(f"\n4. GD mismatch: is_valid={result.is_valid}")
    print(f"   Errors: {result.errors}")
    assert not result.is_valid, "GD mismatch should fail"

    # Invalid: position out of range
    invalid_position = {
        "position": 25,  # Wrong! Max is 20
        "points": 45,
        "played": 20,
        "won": 14,
        "drawn": 3,
        "lost": 3,
        "goals_for": 42,
        "goals_against": 18,
        "goal_difference": 24
    }
    result = validator.validate_table_position(invalid_position)
    print(f"\n5. Position out of range: is_valid={result.is_valid}")
    print(f"   Errors: {result.errors}")
    assert not result.is_valid, "Position out of range should fail"

    print("\n[PASS] Table validation tests passed")
    return True


def test_validation_h2h():
    """Test H2H validation with cross-checks."""
    print("\n" + "=" * 60)
    print("TEST: H2H Validation")
    print("=" * 60)

    validator = ExtractionValidator(match_date=date(2024, 1, 20))

    # Valid H2H
    valid_h2h = {
        "last_5_meetings": [
            {"date": "2023-10-15", "home_team": "Arsenal", "away_team": "Chelsea", "score": "2-1"},
            {"date": "2023-04-20", "home_team": "Chelsea", "away_team": "Arsenal", "score": "1-1"},
            {"date": "2022-11-06", "home_team": "Arsenal", "away_team": "Chelsea", "score": "3-0"},
        ],
        "home_team_wins": 2,
        "draws": 1,
        "away_team_wins": 0,
        "total_goals": 8,
        "most_recent_winner": "Arsenal"
    }
    result = validator.validate_h2h(valid_h2h, "Arsenal", "Chelsea")
    print(f"\n1. Valid H2H: is_valid={result.is_valid}")
    assert result.is_valid, f"Valid H2H should pass: {result.errors}"

    # Invalid: W/D/L doesn't sum to matches
    invalid_sum = {
        "last_5_meetings": [
            {"date": "2023-10-15", "home_team": "Arsenal", "away_team": "Chelsea", "score": "2-1"},
            {"date": "2023-04-20", "home_team": "Chelsea", "away_team": "Arsenal", "score": "1-1"},
            {"date": "2022-11-06", "home_team": "Arsenal", "away_team": "Chelsea", "score": "3-0"},
        ],
        "home_team_wins": 3,  # Wrong! Should be 2
        "draws": 1,
        "away_team_wins": 0,
        "total_goals": 8
    }
    result = validator.validate_h2h(invalid_sum, "Arsenal", "Chelsea")
    print(f"\n2. W/D/L sum mismatch: is_valid={result.is_valid}")
    print(f"   Errors: {result.errors}")
    assert not result.is_valid, "W/D/L mismatch should fail"

    print("\n[PASS] H2H validation tests passed")
    return True


def test_dict_to_dataclass():
    """Test dict to dataclass parsing."""
    print("\n" + "=" * 60)
    print("TEST: Dict to Dataclass Parsing")
    print("=" * 60)

    # Test injury parsing
    injury_dict = {
        "player_name": "Test Player",
        "position": "MID",
        "injury_type": "hamstring",
        "expected_return": "2 weeks",
        "is_key_player": True
    }
    injury = dict_to_injury_extraction(injury_dict)
    print(f"\n1. Injury parsing: {injury.player_name} ({injury.position})")
    assert injury.player_name == "Test Player"
    assert injury.is_key_player == True

    # Test form parsing
    form_dict = {
        "last_5": [
            {"opponent": "Chelsea", "result": "W", "score": "2-0", "venue": "H"},
            {"opponent": "Liverpool", "result": "D", "score": "1-1", "venue": "A"},
            {"opponent": "Brighton", "result": "W", "score": "3-1", "venue": "H"},
            {"opponent": "Man United", "result": "L", "score": "0-1", "venue": "A"},
            {"opponent": "Newcastle", "result": "W", "score": "2-1", "venue": "H"},
        ],
        "current_streak": "1W",
        "goals_scored_last_5": 8,
        "goals_conceded_last_5": 4
    }
    form = dict_to_form_extraction(form_dict)
    print(f"2. Form parsing: {len(form.last_5)} matches, streak={form.current_streak}")
    assert len(form.last_5) == 5
    assert form.goals_scored_last_5 == 8

    # Test table parsing
    table_dict = {
        "position": 2,
        "points": 45,
        "played": 20,
        "won": 14,
        "drawn": 3,
        "lost": 3,
        "goals_for": 42,
        "goals_against": 18,
        "goal_difference": 24,
        "form_string": "WWDLW"
    }
    table = dict_to_table_extraction(table_dict)
    print(f"3. Table parsing: {table.position}th, {table.points}pts")
    assert table.position == 2
    assert table.goal_difference == 24

    print("\n[PASS] Dict to dataclass parsing tests passed")
    return True


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("AGENTS MODULE TEST SUITE")
    print("=" * 60)

    tests = [
        ("Schemas", test_schemas),
        ("Injury Validation", test_validation_injuries),
        ("Form Validation", test_validation_form),
        ("Table Validation", test_validation_table),
        ("H2H Validation", test_validation_h2h),
        ("Dict Parsing", test_dict_to_dataclass),
    ]

    results = []
    for name, test_fn in tests:
        try:
            passed = test_fn()
            results.append((name, "PASS" if passed else "FAIL"))
        except Exception as e:
            print(f"\n[FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, f"ERROR: {e}"))

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for name, status in results:
        emoji = "[OK]" if status == "PASS" else "[XX]"
        print(f"  {emoji} {name}: {status}")

    all_passed = all(s == "PASS" for _, s in results)
    print("\n" + ("All tests passed!" if all_passed else "Some tests failed."))
    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
