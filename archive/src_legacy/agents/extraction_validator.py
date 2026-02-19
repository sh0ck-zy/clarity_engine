"""
Extraction Validator - Anti-Hallucination Cross-Checks

This module validates agent extractions against:
1. Schema constraints (types, ranges, patterns)
2. Logical consistency (points match W/D/L, scores match results)
3. Cross-field validation (goal difference = GF - GA)
4. Temporal validity (dates make sense)

If validation fails, the extraction is REJECTED and fallback to DB data.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date, timedelta
import re
import logging

from .extraction_schemas import (
    InjuryExtraction, FormExtraction, TablePositionExtraction,
    HeadToHeadExtraction, TeamEnrichment, MatchEnrichment,
    FormMatchExtraction, H2HMatchExtraction,
    EXTRACTION_SCHEMAS
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validation with detailed error tracking."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    data: Optional[Any] = None
    confidence: float = 0.0  # Adjusted confidence based on validation


class ExtractionValidator:
    """
    Validates extracted data against schemas and logical constraints.

    Design principle: Be STRICT. It's better to reject good data
    than to accept hallucinated data.
    """

    def __init__(self, match_date: Optional[date] = None):
        """
        Initialize validator.

        Args:
            match_date: The match date for temporal validation
        """
        self.match_date = match_date or date.today()

    # ============================================================
    # INJURY VALIDATION
    # ============================================================

    def validate_injury(self, data: Dict) -> ValidationResult:
        """Validate a single injury extraction."""
        errors = []
        warnings = []

        # Required fields
        if not data.get('player_name'):
            errors.append("player_name is required")
        elif len(data['player_name']) < 2:
            errors.append(f"player_name too short: {data['player_name']}")

        # Position validation
        position = data.get('position', '')
        valid_positions = ['GK', 'DEF', 'MID', 'FWD']
        if position not in valid_positions:
            errors.append(f"Invalid position '{position}', must be one of {valid_positions}")

        # Injury type
        if not data.get('injury_type'):
            errors.append("injury_type is required")

        # Expected return - check for obviously wrong values
        expected_return = data.get('expected_return', '')
        if expected_return:
            # Check for suspicious phrases that indicate hallucination
            suspicious = ['unknown date', 'TBD', 'soon', 'indefinitely']
            if expected_return.lower() in [s.lower() for s in suspicious]:
                warnings.append(f"Vague expected_return: {expected_return}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=data,
            confidence=0.9 if len(errors) == 0 and len(warnings) == 0 else 0.5
        )

    def validate_injuries_list(self, injuries: List[Dict]) -> ValidationResult:
        """Validate a list of injuries."""
        all_errors = []
        all_warnings = []
        valid_injuries = []

        # Check for duplicates
        player_names = []
        for injury in injuries:
            result = self.validate_injury(injury)
            if result.is_valid:
                name = injury.get('player_name', '').lower()
                if name in player_names:
                    all_warnings.append(f"Duplicate player: {injury.get('player_name')}")
                else:
                    player_names.append(name)
                    valid_injuries.append(injury)
            else:
                all_errors.extend(result.errors)
                all_warnings.extend(result.warnings)

        # Sanity check - too many injuries is suspicious
        if len(injuries) > 15:
            all_warnings.append(f"Suspiciously many injuries ({len(injuries)})")

        return ValidationResult(
            is_valid=True,  # We return valid injuries, not all-or-nothing
            errors=all_errors,
            warnings=all_warnings,
            data=valid_injuries,
            confidence=len(valid_injuries) / max(len(injuries), 1) if injuries else 1.0
        )

    # ============================================================
    # FORM VALIDATION
    # ============================================================

    def validate_form_match(self, match: Dict) -> ValidationResult:
        """Validate a single form match."""
        errors = []
        warnings = []

        # Required fields
        if not match.get('opponent'):
            errors.append("opponent is required")

        # Result validation
        result = match.get('result', '')
        if result not in ['W', 'D', 'L']:
            errors.append(f"Invalid result '{result}', must be W/D/L")

        # Score validation
        score = match.get('score', '')
        score_pattern = re.compile(r'^(\d+)-(\d+)$')
        score_match = score_pattern.match(score)
        if not score_match:
            errors.append(f"Invalid score format '{score}', must be 'X-Y'")
        else:
            # Cross-check: score must match result
            our_goals = int(score_match.group(1))
            their_goals = int(score_match.group(2))

            expected_result = 'D' if our_goals == their_goals else ('W' if our_goals > their_goals else 'L')
            if result and result != expected_result:
                errors.append(f"Score {score} doesn't match result {result} (expected {expected_result})")

        # Venue validation
        venue = match.get('venue', '')
        if venue not in ['H', 'A']:
            errors.append(f"Invalid venue '{venue}', must be H/A")

        # Date validation (if provided)
        match_date_str = match.get('date')
        if match_date_str:
            try:
                match_dt = datetime.strptime(match_date_str, '%Y-%m-%d').date()
                if match_dt >= self.match_date:
                    errors.append(f"Match date {match_date_str} is not before match date {self.match_date}")
                if match_dt < self.match_date - timedelta(days=365):
                    warnings.append(f"Match date {match_date_str} is suspiciously old")
            except ValueError:
                errors.append(f"Invalid date format '{match_date_str}', must be YYYY-MM-DD")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=match,
            confidence=0.9 if len(errors) == 0 else 0.0
        )

    def validate_form(self, data: Dict) -> ValidationResult:
        """Validate complete form extraction."""
        errors = []
        warnings = []

        last_5 = data.get('last_5', [])

        # Must have exactly 5 matches
        if len(last_5) != 5:
            errors.append(f"Form must have exactly 5 matches, got {len(last_5)}")

        # Validate each match
        valid_matches = []
        for match in last_5:
            result = self.validate_form_match(match)
            if result.is_valid:
                valid_matches.append(match)
            errors.extend(result.errors)
            warnings.extend(result.warnings)

        # Cross-check: goals totals must match individual scores
        goals_scored = data.get('goals_scored_last_5', 0)
        goals_conceded = data.get('goals_conceded_last_5', 0)

        calculated_scored = 0
        calculated_conceded = 0
        for match in valid_matches:
            score = match.get('score', '0-0')
            parts = score.split('-')
            if len(parts) == 2:
                calculated_scored += int(parts[0])
                calculated_conceded += int(parts[1])

        if calculated_scored != goals_scored:
            errors.append(f"goals_scored_last_5 ({goals_scored}) doesn't match calculated ({calculated_scored})")
        if calculated_conceded != goals_conceded:
            errors.append(f"goals_conceded_last_5 ({goals_conceded}) doesn't match calculated ({calculated_conceded})")

        # Validate streak format
        streak = data.get('current_streak', '')
        if streak:
            streak_pattern = re.compile(r'^\d+[WDL]$')
            if not streak_pattern.match(streak):
                warnings.append(f"Invalid streak format: {streak}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=data if len(errors) == 0 else None,
            confidence=0.9 if len(errors) == 0 else 0.0
        )

    # ============================================================
    # TABLE POSITION VALIDATION
    # ============================================================

    def validate_table_position(self, data: Dict, max_position: int = 20) -> ValidationResult:
        """Validate table position extraction."""
        errors = []
        warnings = []

        position = data.get('position')
        points = data.get('points', 0)
        played = data.get('played', 0)
        won = data.get('won', 0)
        drawn = data.get('drawn', 0)
        lost = data.get('lost', 0)
        gf = data.get('goals_for', 0)
        ga = data.get('goals_against', 0)
        gd = data.get('goal_difference', 0)

        # Position range
        if position is None or position < 1 or position > max_position:
            errors.append(f"Position {position} out of range 1-{max_position}")

        # Points consistency: points = won*3 + drawn*1
        calculated_points = won * 3 + drawn
        if points != calculated_points:
            errors.append(f"Points ({points}) don't match W/D/L ({calculated_points} = {won}*3 + {drawn})")

        # Played consistency: played = won + drawn + lost
        calculated_played = won + drawn + lost
        if played != calculated_played:
            errors.append(f"Played ({played}) doesn't match W+D+L ({calculated_played})")

        # Goal difference consistency
        calculated_gd = gf - ga
        if gd != calculated_gd:
            errors.append(f"Goal difference ({gd}) doesn't match GF-GA ({calculated_gd})")

        # Sanity checks
        if played > 38:
            errors.append(f"Played ({played}) exceeds season maximum (38)")
        if points < 0:
            errors.append(f"Points cannot be negative ({points})")
        if points > played * 3:
            errors.append(f"Points ({points}) exceed maximum possible for {played} games ({played * 3})")

        # Form string validation
        form_string = data.get('form_string', '')
        if form_string:
            if not re.match(r'^[WDL]{0,5}$', form_string):
                warnings.append(f"Invalid form_string: {form_string}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=data if len(errors) == 0 else None,
            confidence=0.95 if len(errors) == 0 else 0.0
        )

    # ============================================================
    # HEAD-TO-HEAD VALIDATION
    # ============================================================

    def validate_h2h_match(self, match: Dict, home_team: str, away_team: str) -> ValidationResult:
        """Validate a single H2H match."""
        errors = []
        warnings = []

        # Date validation
        match_date_str = match.get('date', '')
        if match_date_str:
            try:
                match_dt = datetime.strptime(match_date_str, '%Y-%m-%d').date()
                if match_dt >= self.match_date:
                    errors.append(f"H2H match date {match_date_str} is not before match date")
            except ValueError:
                errors.append(f"Invalid date format: {match_date_str}")

        # Team names - should involve both teams
        match_home = match.get('home_team', '')
        match_away = match.get('away_team', '')

        teams_involved = {match_home.lower(), match_away.lower()}
        expected_teams = {home_team.lower(), away_team.lower()}

        if not teams_involved.intersection(expected_teams):
            errors.append(f"H2H match doesn't involve expected teams: {match_home} vs {match_away}")

        # Score validation
        score = match.get('score', '')
        if not re.match(r'^\d+-\d+$', score):
            errors.append(f"Invalid score format: {score}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=match
        )

    def validate_h2h(self, data: Dict, home_team: str, away_team: str) -> ValidationResult:
        """Validate complete H2H extraction."""
        errors = []
        warnings = []

        last_5 = data.get('last_5_meetings', [])
        home_wins = data.get('home_team_wins', 0)
        draws = data.get('draws', 0)
        away_wins = data.get('away_team_wins', 0)

        # Validate individual matches
        valid_matches = []
        for match in last_5:
            result = self.validate_h2h_match(match, home_team, away_team)
            if result.is_valid:
                valid_matches.append(match)
            errors.extend(result.errors)
            warnings.extend(result.warnings)

        # Cross-check: wins + draws must equal matches
        total_results = home_wins + draws + away_wins
        if last_5 and total_results != len(last_5):
            errors.append(f"W/D/L total ({total_results}) doesn't match number of matches ({len(last_5)})")

        # Verify win counts from matches
        if valid_matches:
            calculated_home_wins = 0
            calculated_draws = 0
            calculated_away_wins = 0

            for match in valid_matches:
                score = match.get('score', '0-0')
                parts = score.split('-')
                if len(parts) == 2:
                    h_goals = int(parts[0])
                    a_goals = int(parts[1])

                    # Determine who won based on who was home
                    match_home = match.get('home_team', '').lower()
                    if match_home == home_team.lower():
                        if h_goals > a_goals:
                            calculated_home_wins += 1
                        elif h_goals < a_goals:
                            calculated_away_wins += 1
                        else:
                            calculated_draws += 1
                    else:
                        if a_goals > h_goals:
                            calculated_home_wins += 1
                        elif a_goals < h_goals:
                            calculated_away_wins += 1
                        else:
                            calculated_draws += 1

            if calculated_home_wins != home_wins:
                warnings.append(f"home_team_wins ({home_wins}) may not match calculated ({calculated_home_wins})")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=data if len(errors) == 0 else None,
            confidence=0.85 if len(errors) == 0 else 0.0
        )

    # ============================================================
    # TEAM ENRICHMENT VALIDATION
    # ============================================================

    def validate_team_enrichment(self, data: Dict) -> ValidationResult:
        """Validate complete team enrichment."""
        errors = []
        warnings = []

        team_name = data.get('team_name')
        if not team_name:
            errors.append("team_name is required")
            return ValidationResult(is_valid=False, errors=errors)

        # Validate injuries
        injuries_result = self.validate_injuries_list(data.get('injuries', []))
        if not injuries_result.is_valid:
            errors.extend(injuries_result.errors)
        warnings.extend(injuries_result.warnings)

        # Validate form (if present)
        form_data = data.get('form')
        if form_data:
            form_result = self.validate_form(form_data)
            if not form_result.is_valid:
                errors.extend(form_result.errors)
            warnings.extend(form_result.warnings)

        # Validate table position (if present)
        table_data = data.get('table_position')
        if table_data:
            table_result = self.validate_table_position(table_data)
            if not table_result.is_valid:
                errors.extend(table_result.errors)
            warnings.extend(table_result.warnings)

        # Calculate overall confidence
        confidence = 1.0
        if errors:
            confidence *= 0.5
        if warnings:
            confidence *= 0.9

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=data if len(errors) == 0 else None,
            confidence=confidence
        )

    # ============================================================
    # MATCH ENRICHMENT VALIDATION
    # ============================================================

    def validate_match_enrichment(
        self,
        data: Dict,
        home_team: str,
        away_team: str
    ) -> ValidationResult:
        """Validate complete match enrichment."""
        errors = []
        warnings = []

        # Validate home team enrichment
        home_data = data.get('home_team', {})
        if home_data:
            home_result = self.validate_team_enrichment(home_data)
            errors.extend([f"Home: {e}" for e in home_result.errors])
            warnings.extend([f"Home: {w}" for w in home_result.warnings])

        # Validate away team enrichment
        away_data = data.get('away_team', {})
        if away_data:
            away_result = self.validate_team_enrichment(away_data)
            errors.extend([f"Away: {e}" for e in away_result.errors])
            warnings.extend([f"Away: {w}" for w in away_result.warnings])

        # Validate H2H (if present)
        h2h_data = data.get('head_to_head')
        if h2h_data:
            h2h_result = self.validate_h2h(h2h_data, home_team, away_team)
            errors.extend([f"H2H: {e}" for e in h2h_result.errors])
            warnings.extend([f"H2H: {w}" for w in h2h_result.warnings])

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            data=data,
            confidence=0.9 if len(errors) == 0 else 0.5
        )


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def validate_extraction(
    data: Dict,
    extraction_type: str,
    match_date: Optional[date] = None,
    **kwargs
) -> ValidationResult:
    """
    Validate extraction by type.

    Args:
        data: The extracted data dict
        extraction_type: "injury", "form", "table", "h2h", "team", "match"
        match_date: Match date for temporal validation
        **kwargs: Additional args (e.g., home_team, away_team for H2H)

    Returns:
        ValidationResult
    """
    validator = ExtractionValidator(match_date)

    if extraction_type == "injury":
        return validator.validate_injury(data)
    elif extraction_type == "injuries":
        return validator.validate_injuries_list(data if isinstance(data, list) else [data])
    elif extraction_type == "form":
        return validator.validate_form(data)
    elif extraction_type == "table":
        return validator.validate_table_position(data)
    elif extraction_type == "h2h":
        home_team = kwargs.get('home_team', '')
        away_team = kwargs.get('away_team', '')
        return validator.validate_h2h(data, home_team, away_team)
    elif extraction_type == "team":
        return validator.validate_team_enrichment(data)
    elif extraction_type == "match":
        home_team = kwargs.get('home_team', '')
        away_team = kwargs.get('away_team', '')
        return validator.validate_match_enrichment(data, home_team, away_team)
    else:
        return ValidationResult(
            is_valid=False,
            errors=[f"Unknown extraction type: {extraction_type}"]
        )
