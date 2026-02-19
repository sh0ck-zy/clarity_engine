"""
Data Validator

Validates PreMatchContext and PostMatchReality for completeness and correctness.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple
import logging

from src.models import PreMatchContext, PostMatchReality

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validation."""
    is_valid: bool
    score: float              # 0-100
    errors: List[str]         # Critical issues
    warnings: List[str]       # Non-critical issues
    

class DataValidator:
    """
    Validates match data for completeness and correctness.
    
    Validations:
    - Required fields present
    - Data types correct
    - Values in valid ranges
    - Cross-field consistency
    - No future data leakage (for pre-match)
    """
    
    def validate_pre_match(
        self, 
        context: PreMatchContext,
        strict: bool = False
    ) -> ValidationResult:
        """
        Validate a PreMatchContext.
        
        Args:
            context: The context to validate
            strict: If True, warnings become errors
            
        Returns:
            ValidationResult with details
        """
        errors = []
        warnings = []
        
        # 1. Required fields
        if not context.fixture.fixture_id:
            errors.append("Missing fixture_id")
        if not context.fixture.home_team_id:
            errors.append("Missing home_team_id")
        if not context.fixture.away_team_id:
            errors.append("Missing away_team_id")
            
        # 2. Team snapshots
        if context.home_snapshot.league_position < 1:
            warnings.append("Invalid home league_position")
        if context.away_snapshot.league_position < 1:
            warnings.append("Invalid away league_position")
            
        # 3. Elo sanity check (typically 800-2200)
        if not (800 <= context.home_snapshot.elo <= 2500):
            warnings.append(f"Home Elo out of range: {context.home_snapshot.elo}")
        if not (800 <= context.away_snapshot.elo <= 2500):
            warnings.append(f"Away Elo out of range: {context.away_snapshot.elo}")
            
        # 4. Form string valid
        valid_form_chars = set("WDLN")  # Win, Draw, Loss, None
        if context.home_snapshot.form_last_5:
            invalid = set(context.home_snapshot.form_last_5) - valid_form_chars
            if invalid:
                warnings.append(f"Invalid form characters: {invalid}")
                
        # 5. No future data leakage
        if context.built_at > context.fixture.kickoff_time:
            # Built after kickoff - might have future data
            if context.odds and context.odds.captured_at > context.fixture.kickoff_time:
                errors.append("Odds captured after kickoff - future data leakage")
                
        # 6. Coverage check
        if context.coverage_score < 50:
            warnings.append(f"Low coverage score: {context.coverage_score:.1f}%")
            
        # 7. Availability sanity
        for absence in context.home_availability.absences:
            if absence.importance < 0 or absence.importance > 10:
                warnings.append(f"Invalid importance for {absence.player_name}: {absence.importance}")
                
        # Convert warnings to errors if strict
        if strict:
            errors.extend(warnings)
            warnings = []
            
        # Calculate score
        score = 100.0
        score -= len(errors) * 20
        score -= len(warnings) * 5
        score = max(0, min(100, score))
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            score=score,
            errors=errors,
            warnings=warnings,
        )
    
    def validate_post_match(
        self,
        reality: PostMatchReality,
        strict: bool = False
    ) -> ValidationResult:
        """
        Validate a PostMatchReality.
        
        Args:
            reality: The post-match data to validate
            strict: If True, warnings become errors
            
        Returns:
            ValidationResult with details
        """
        errors = []
        warnings = []
        
        # 1. Required fields
        if not reality.fixture_id:
            errors.append("Missing fixture_id")
            
        # 2. Score validity
        if reality.score_home < 0 or reality.score_away < 0:
            errors.append("Negative score")
            
        # 3. Winner consistency
        expected_winner = (
            "home" if reality.score_home > reality.score_away else
            "away" if reality.score_away > reality.score_home else
            "draw"
        )
        if reality.winner != expected_winner:
            errors.append(f"Winner mismatch: {reality.winner} vs expected {expected_winner}")
            
        # 4. Goals count matches score
        home_goals = sum(1 for g in reality.goals if g.team_id == reality.home_lineup.team_id)
        away_goals = sum(1 for g in reality.goals if g.team_id == reality.away_lineup.team_id)
        
        # Account for own goals
        for goal in reality.goals:
            if goal.is_own_goal:
                if goal.team_id == reality.home_lineup.team_id:
                    home_goals -= 1
                    away_goals += 1
                else:
                    away_goals -= 1
                    home_goals += 1
                    
        if home_goals != reality.score_home:
            warnings.append(f"Home goals mismatch: {home_goals} goals recorded vs {reality.score_home} score")
        if away_goals != reality.score_away:
            warnings.append(f"Away goals mismatch: {away_goals} goals recorded vs {reality.score_away} score")
            
        # 5. xG sanity (usually 0-5 per team)
        if reality.statistics:
            if reality.statistics.home_stats.xg > 6:
                warnings.append(f"High home xG: {reality.statistics.home_stats.xg}")
            if reality.statistics.away_stats.xg > 6:
                warnings.append(f"High away xG: {reality.statistics.away_stats.xg}")
                
        # 6. Lineup size
        if len(reality.home_lineup.starting_xi) != 11:
            warnings.append(f"Home lineup has {len(reality.home_lineup.starting_xi)} players, expected 11")
        if len(reality.away_lineup.starting_xi) != 11:
            warnings.append(f"Away lineup has {len(reality.away_lineup.starting_xi)} players, expected 11")
            
        # Convert warnings to errors if strict
        if strict:
            errors.extend(warnings)
            warnings = []
            
        # Calculate score
        score = 100.0
        score -= len(errors) * 20
        score -= len(warnings) * 5
        score = max(0, min(100, score))
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            score=score,
            errors=errors,
            warnings=warnings,
        )
    
    def cross_validate(
        self,
        pre: PreMatchContext,
        post: PostMatchReality
    ) -> ValidationResult:
        """
        Cross-validate pre-match and post-match data.
        
        Checks consistency between what we predicted and what happened.
        """
        errors = []
        warnings = []
        
        # 1. Fixture ID matches
        if pre.fixture.fixture_id != post.fixture_id:
            errors.append("Fixture ID mismatch between pre and post")
            
        # 2. Team IDs match
        if pre.fixture.home_team_id != post.home_lineup.team_id:
            errors.append("Home team ID mismatch")
        if pre.fixture.away_team_id != post.away_lineup.team_id:
            errors.append("Away team ID mismatch")
            
        # 3. Pre-match built before kickoff
        if pre.built_at > pre.fixture.kickoff_time:
            warnings.append("Pre-match context built after kickoff")
            
        # 4. Check if predicted absences were actually absent
        pre_absent_ids = {a.player_id for a in pre.home_availability.absences}
        post_played_ids = {p.player_id for p in post.home_lineup.starting_xi}
        post_played_ids.update(p.player_id for p in post.home_lineup.substitutes if p.minutes_played and p.minutes_played > 0)
        
        # Players we thought would be absent but played
        surprise_plays = pre_absent_ids & post_played_ids
        if surprise_plays:
            warnings.append(f"Players predicted absent but played: {len(surprise_plays)}")
            
        # Calculate score
        score = 100.0
        score -= len(errors) * 20
        score -= len(warnings) * 5
        score = max(0, min(100, score))
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            score=score,
            errors=errors,
            warnings=warnings,
        )
