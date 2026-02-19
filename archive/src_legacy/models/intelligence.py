"""
Intelligence Definition & Validation

Intelligence = Predictions/Takes that can be validated against reality.

Each piece of intelligence:
1. Has a pre-match PREDICTION (what we think will happen)
2. Has a post-match REALITY (what actually happened)
3. Has a SCORE (how right were we?)
4. Has FEATURE ATTRIBUTION (what signals drove the prediction?)

This enables:
- Tracking prediction accuracy over time
- Learning which features are predictive
- Improving models based on feedback

Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple, Union
from enum import Enum


# ============================================================
# INTELLIGENCE CATEGORIES
# ============================================================

class IntelligenceCategory(Enum):
    """Categories of intelligence/takes we generate."""
    
    # RESULTADO
    RESULT = "result"                    # Quem ganha?
    
    # GOLOS
    GOALS = "goals"                      # Quantos golos?
    
    # DOMÍNIO
    DOMINANCE = "dominance"              # Quem domina?
    
    # ESTILO
    STYLE_MATCHUP = "style_matchup"      # Como será o jogo?
    
    # JOGADORES
    KEY_PLAYERS = "key_players"          # Quem decide?
    
    # ZONAS
    DANGER_ZONES = "danger_zones"        # De onde vêm os golos?
    
    # MOMENTUM
    MATCH_FLOW = "match_flow"            # Como evolui o jogo?
    
    # TÁCTICA
    TACTICAL = "tactical"                # Como vão jogar?


class ValidationScore(Enum):
    """How well did we predict?"""
    CRUSH_IT = "crush_it"       # Exceeded expectations (90%+)
    NAIL_IT = "nail_it"         # Got it right (70-90%)
    CLOSE = "close"             # Almost (50-70%)
    MISS = "miss"               # Wrong (30-50%)
    DISASTER = "disaster"       # Completely wrong (<30%)


# ============================================================
# TAKE: A single prediction with validation
# ============================================================

@dataclass
class Take:
    """
    A single "take" or prediction that can be validated.
    
    Example:
        take = Take(
            category=IntelligenceCategory.RESULT,
            question="Quem ganha?",
            prediction="Liverpool",
            confidence=0.75,
            reasoning="Form + H2H + Home advantage",
            features_used=["form_diff", "h2h_record", "home_xG"]
        )
        
        # After match:
        take.actual = "Liverpool"
        take.score = ValidationScore.NAIL_IT
        take.accuracy = 1.0
    """
    # Identity
    take_id: str
    category: IntelligenceCategory
    
    # The question being answered
    question: str
    
    # Pre-match prediction
    prediction: Any              # Can be str, float, dict, etc.
    confidence: float            # 0-1, how confident
    reasoning: str               # Why this prediction?
    
    # Feature attribution
    features_used: List[str] = field(default_factory=list)
    feature_weights: Dict[str, float] = field(default_factory=dict)
    
    # Post-match validation (filled after match)
    actual: Optional[Any] = None
    accuracy: Optional[float] = None     # 0-1, how accurate
    score: Optional[ValidationScore] = None
    
    # Learning
    was_correct: Optional[bool] = None
    error_analysis: Optional[str] = None
    
    # Meta
    created_at: datetime = field(default_factory=datetime.now)
    validated_at: Optional[datetime] = None


# ============================================================
# THE TAKES: Detailed prediction structures per category
# ============================================================

# ------------ RESULT ------------

@dataclass
class ResultTake:
    """
    RESULT: Quem ganha?
    
    Predictions:
    - Winner (home/draw/away)
    - Win probabilities
    - Margin prediction
    """
    # Prediction
    predicted_winner: str        # "home", "draw", "away"
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    predicted_margin: Optional[int] = None  # Goal difference
    
    confidence: float = 0.0
    reasoning: str = ""
    
    # Validation (post-match)
    actual_winner: Optional[str] = None
    actual_margin: Optional[int] = None
    
    # Scoring
    winner_correct: Optional[bool] = None
    margin_error: Optional[int] = None
    brier_score: Optional[float] = None  # Probability accuracy
    
    def validate(self, home_goals: int, away_goals: int) -> ValidationScore:
        """Validate against actual result."""
        if home_goals > away_goals:
            self.actual_winner = "home"
        elif away_goals > home_goals:
            self.actual_winner = "away"
        else:
            self.actual_winner = "draw"
        
        self.actual_margin = abs(home_goals - away_goals)
        self.winner_correct = (self.predicted_winner == self.actual_winner)
        self.margin_error = abs((self.predicted_margin or 0) - self.actual_margin)
        
        # Calculate Brier score
        actual_probs = [1 if self.actual_winner == w else 0 for w in ["home", "draw", "away"]]
        pred_probs = [self.home_win_prob, self.draw_prob, self.away_win_prob]
        self.brier_score = sum((p - a) ** 2 for p, a in zip(pred_probs, actual_probs)) / 3
        
        # Score
        if self.winner_correct and self.brier_score < 0.1:
            return ValidationScore.CRUSH_IT
        elif self.winner_correct and self.brier_score < 0.2:
            return ValidationScore.NAIL_IT
        elif self.winner_correct:
            return ValidationScore.CLOSE
        elif self.brier_score < 0.3:
            return ValidationScore.MISS
        else:
            return ValidationScore.DISASTER


# ------------ GOALS ------------

@dataclass
class GoalsTake:
    """
    GOALS: Quantos golos?
    
    Predictions:
    - Total goals
    - Home goals / Away goals
    - Over/Under lines
    - BTTS
    """
    # Prediction
    predicted_total: float
    predicted_home: float
    predicted_away: float
    
    over_25_prob: float = 0.5
    over_35_prob: float = 0.3
    btts_prob: float = 0.5
    
    confidence: float = 0.0
    reasoning: str = ""
    
    # Validation
    actual_total: Optional[int] = None
    actual_home: Optional[int] = None
    actual_away: Optional[int] = None
    
    # Scoring
    total_error: Optional[float] = None
    over_25_correct: Optional[bool] = None
    btts_correct: Optional[bool] = None
    
    def validate(self, home_goals: int, away_goals: int) -> ValidationScore:
        """Validate against actual goals."""
        self.actual_home = home_goals
        self.actual_away = away_goals
        self.actual_total = home_goals + away_goals
        
        self.total_error = abs(self.predicted_total - self.actual_total)
        self.over_25_correct = (self.actual_total > 2.5) == (self.over_25_prob > 0.5)
        self.btts_correct = (home_goals > 0 and away_goals > 0) == (self.btts_prob > 0.5)
        
        # Score based on accuracy
        if self.total_error <= 0.5 and self.over_25_correct and self.btts_correct:
            return ValidationScore.CRUSH_IT
        elif self.total_error <= 1.0 and (self.over_25_correct or self.btts_correct):
            return ValidationScore.NAIL_IT
        elif self.total_error <= 1.5:
            return ValidationScore.CLOSE
        elif self.total_error <= 2.5:
            return ValidationScore.MISS
        else:
            return ValidationScore.DISASTER


# ------------ DOMINANCE ------------

@dataclass
class DominanceTake:
    """
    DOMINANCE: Quem domina?
    
    Predictions:
    - Possession split
    - xG split
    - Shot dominance
    - Territory control
    """
    # Prediction
    predicted_possession_home: float     # 0-100
    predicted_xG_home: float
    predicted_xG_away: float
    predicted_shot_ratio: float          # home_shots / total_shots
    dominant_team: str                   # "home", "away", "balanced"
    
    confidence: float = 0.0
    reasoning: str = ""
    
    # Validation
    actual_possession_home: Optional[float] = None
    actual_xG_home: Optional[float] = None
    actual_xG_away: Optional[float] = None
    actual_dominant_team: Optional[str] = None
    
    # Scoring
    possession_error: Optional[float] = None
    xG_home_error: Optional[float] = None
    xG_away_error: Optional[float] = None
    dominance_correct: Optional[bool] = None
    
    def validate(
        self, 
        possession_home: float, 
        xG_home: float, 
        xG_away: float
    ) -> ValidationScore:
        """Validate against actual match stats."""
        self.actual_possession_home = possession_home
        self.actual_xG_home = xG_home
        self.actual_xG_away = xG_away
        
        # Determine actual dominance
        if xG_home > xG_away * 1.3:
            self.actual_dominant_team = "home"
        elif xG_away > xG_home * 1.3:
            self.actual_dominant_team = "away"
        else:
            self.actual_dominant_team = "balanced"
        
        self.possession_error = abs(self.predicted_possession_home - possession_home)
        self.xG_home_error = abs(self.predicted_xG_home - xG_home)
        self.xG_away_error = abs(self.predicted_xG_away - xG_away)
        self.dominance_correct = (self.dominant_team == self.actual_dominant_team)
        
        total_xG_error = self.xG_home_error + self.xG_away_error
        
        if self.dominance_correct and total_xG_error < 0.5:
            return ValidationScore.CRUSH_IT
        elif self.dominance_correct and total_xG_error < 1.0:
            return ValidationScore.NAIL_IT
        elif self.dominance_correct or total_xG_error < 1.5:
            return ValidationScore.CLOSE
        elif total_xG_error < 2.5:
            return ValidationScore.MISS
        else:
            return ValidationScore.DISASTER


# ------------ STYLE MATCHUP ------------

@dataclass
class StyleMatchupTake:
    """
    STYLE: Como será o jogo?
    
    Predictions:
    - Game tempo (open, tight, slow)
    - Style clash outcome
    - Expected patterns
    """
    # Prediction
    predicted_tempo: str                 # "open", "tight", "slow", "chaotic"
    predicted_style_winner: str          # Whose style prevails
    expected_patterns: List[str] = field(default_factory=list)
    
    confidence: float = 0.0
    reasoning: str = ""
    
    # Validation
    actual_tempo: Optional[str] = None
    patterns_occurred: List[str] = field(default_factory=list)
    
    # Scoring
    tempo_correct: Optional[bool] = None
    patterns_accuracy: Optional[float] = None
    
    def validate(
        self,
        total_shots: int,
        possession_changes: int,
        fouls: int,
        total_xG: float
    ) -> ValidationScore:
        """Infer actual tempo from stats."""
        # Classify tempo based on stats
        if total_shots > 25 and total_xG > 3.0:
            self.actual_tempo = "open"
        elif total_shots < 15 and total_xG < 1.5:
            self.actual_tempo = "tight"
        elif fouls > 25:
            self.actual_tempo = "chaotic"
        else:
            self.actual_tempo = "slow"
        
        self.tempo_correct = (self.predicted_tempo == self.actual_tempo)
        
        if self.tempo_correct:
            return ValidationScore.NAIL_IT
        elif self.predicted_tempo in ["open", "chaotic"] and self.actual_tempo in ["open", "chaotic"]:
            return ValidationScore.CLOSE
        else:
            return ValidationScore.MISS


# ------------ KEY PLAYERS ------------

@dataclass
class KeyPlayerTake:
    """
    KEY PLAYERS: Quem decide?
    
    Predictions:
    - Players expected to impact
    - Expected performances
    - Matchup winners
    """
    # Prediction
    home_key_player_id: int
    home_key_player_name: str
    home_player_prediction: str          # "score", "assist", "dominate", "quiet"
    
    away_key_player_id: int
    away_key_player_name: str
    away_player_prediction: str
    
    predicted_motm_team: str             # "home" or "away"
    
    confidence: float = 0.0
    reasoning: str = ""
    
    # Validation
    home_player_actual: Optional[str] = None  # What they actually did
    away_player_actual: Optional[str] = None
    actual_motm_id: Optional[int] = None
    actual_motm_team: Optional[str] = None
    
    # Scoring
    home_prediction_correct: Optional[bool] = None
    away_prediction_correct: Optional[bool] = None
    motm_team_correct: Optional[bool] = None


# ------------ DANGER ZONES ------------

@dataclass
class DangerZonesTake:
    """
    DANGER ZONES: De onde vêm os golos?
    
    Predictions:
    - Primary threat zones
    - Set piece threat level
    - Counter attack threat
    """
    # Prediction - where goals will come from
    home_primary_threat: str             # "left_wing", "center", "right_wing", "set_piece"
    away_primary_threat: str
    
    set_piece_goal_prob: float
    counter_goal_prob: float
    
    predicted_xG_by_zone: Dict[str, float] = field(default_factory=dict)
    
    confidence: float = 0.0
    reasoning: str = ""
    
    # Validation (from shotmap)
    actual_xG_by_zone: Dict[str, float] = field(default_factory=dict)
    goals_from_set_pieces: int = 0
    goals_from_counters: int = 0
    
    # Scoring
    primary_threat_correct_home: Optional[bool] = None
    primary_threat_correct_away: Optional[bool] = None
    zone_accuracy: Optional[float] = None


# ------------ MATCH FLOW ------------

@dataclass
class MatchFlowTake:
    """
    MATCH FLOW: Como evolui o jogo?
    
    Predictions:
    - Which team starts stronger
    - Key periods
    - Late game prediction
    """
    # Prediction
    first_goal_team: str                 # "home", "away"
    first_goal_before_min: int           # Expected before minute X
    
    home_strong_periods: List[str] = field(default_factory=list)  # "0-15", "75-90"
    away_strong_periods: List[str] = field(default_factory=list)
    
    late_goal_prob: float = 0.3          # Goal after 75'
    
    confidence: float = 0.0
    reasoning: str = ""
    
    # Validation (from momentum + events)
    actual_first_goal_team: Optional[str] = None
    actual_first_goal_minute: Optional[int] = None
    actual_strong_periods_home: List[str] = field(default_factory=list)
    had_late_goal: Optional[bool] = None
    
    # Scoring
    first_goal_team_correct: Optional[bool] = None
    first_goal_timing_error: Optional[int] = None
    period_accuracy: Optional[float] = None


# ------------ TACTICAL ------------

@dataclass
class TacticalTake:
    """
    TACTICAL: Como vão jogar?
    
    Predictions:
    - Expected formations
    - Tactical approach
    - In-game changes
    """
    # Prediction
    predicted_home_formation: str
    predicted_away_formation: str
    
    home_approach: str                   # "attack", "control", "defend", "counter"
    away_approach: str
    
    expected_subs_home: int
    expected_subs_away: int
    
    confidence: float = 0.0
    reasoning: str = ""
    
    # Validation
    actual_home_formation: Optional[str] = None
    actual_away_formation: Optional[str] = None
    actual_subs_home: int = 0
    actual_subs_away: int = 0
    
    # Scoring
    formation_home_correct: Optional[bool] = None
    formation_away_correct: Optional[bool] = None


# ============================================================
# MATCH INTELLIGENCE (all takes for a fixture)
# ============================================================

@dataclass
class MatchIntelligence:
    """
    Complete intelligence package for a fixture.
    
    Contains all takes across all categories,
    with pre-match predictions and post-match validation.
    """
    # Fixture
    fixture_id: int
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    match_date: date
    round_number: int
    
    # THE TAKES
    result: Optional[ResultTake] = None
    goals: Optional[GoalsTake] = None
    dominance: Optional[DominanceTake] = None
    style: Optional[StyleMatchupTake] = None
    key_players: Optional[KeyPlayerTake] = None
    danger_zones: Optional[DangerZonesTake] = None
    match_flow: Optional[MatchFlowTake] = None
    tactical: Optional[TacticalTake] = None
    
    # Aggregate confidence
    overall_confidence: float = 0.0
    
    # Feature attribution (what drove predictions?)
    top_features: List[str] = field(default_factory=list)
    feature_importance: Dict[str, float] = field(default_factory=dict)
    
    # Validation summary (post-match)
    is_validated: bool = False
    validation_scores: Dict[IntelligenceCategory, ValidationScore] = field(default_factory=dict)
    overall_score: Optional[ValidationScore] = None
    
    # Learning
    accuracy_by_category: Dict[IntelligenceCategory, float] = field(default_factory=dict)
    best_prediction: Optional[IntelligenceCategory] = None
    worst_prediction: Optional[IntelligenceCategory] = None
    lessons_learned: List[str] = field(default_factory=list)
    
    # Meta
    created_at: datetime = field(default_factory=datetime.now)
    validated_at: Optional[datetime] = None
    
    def validate_all(
        self,
        home_goals: int,
        away_goals: int,
        possession_home: float,
        xG_home: float,
        xG_away: float,
        **kwargs
    ) -> Dict[IntelligenceCategory, ValidationScore]:
        """Validate all takes against match reality."""
        scores = {}
        
        if self.result:
            scores[IntelligenceCategory.RESULT] = self.result.validate(home_goals, away_goals)
        
        if self.goals:
            scores[IntelligenceCategory.GOALS] = self.goals.validate(home_goals, away_goals)
        
        if self.dominance:
            scores[IntelligenceCategory.DOMINANCE] = self.dominance.validate(
                possession_home, xG_home, xG_away
            )
        
        # Add more validations...
        
        self.validation_scores = scores
        self.is_validated = True
        self.validated_at = datetime.now()
        
        # Calculate overall score
        if scores:
            score_values = {
                ValidationScore.CRUSH_IT: 5,
                ValidationScore.NAIL_IT: 4,
                ValidationScore.CLOSE: 3,
                ValidationScore.MISS: 2,
                ValidationScore.DISASTER: 1
            }
            avg_score = sum(score_values[s] for s in scores.values()) / len(scores)
            
            if avg_score >= 4.5:
                self.overall_score = ValidationScore.CRUSH_IT
            elif avg_score >= 3.5:
                self.overall_score = ValidationScore.NAIL_IT
            elif avg_score >= 2.5:
                self.overall_score = ValidationScore.CLOSE
            elif avg_score >= 1.5:
                self.overall_score = ValidationScore.MISS
            else:
                self.overall_score = ValidationScore.DISASTER
        
        return scores


# ============================================================
# ROUND INTELLIGENCE (all matches in a round)
# ============================================================

@dataclass
class RoundIntelligence:
    """
    Intelligence for all matches in a round.
    
    Enables batch validation and aggregate learning.
    """
    season: str
    round_number: int
    
    # All match intelligence
    matches: List[MatchIntelligence] = field(default_factory=list)
    
    # Aggregate stats (post-validation)
    total_matches: int = 0
    validated_matches: int = 0
    
    # Score distribution
    score_distribution: Dict[ValidationScore, int] = field(default_factory=dict)
    
    # Category accuracy
    category_accuracy: Dict[IntelligenceCategory, float] = field(default_factory=dict)
    
    # Best/worst
    best_prediction_match: Optional[int] = None  # fixture_id
    worst_prediction_match: Optional[int] = None
    
    # Feature performance
    feature_accuracy: Dict[str, float] = field(default_factory=dict)
    
    def aggregate_validation(self):
        """Aggregate validation results across all matches."""
        self.total_matches = len(self.matches)
        self.validated_matches = sum(1 for m in self.matches if m.is_validated)
        
        # Count scores
        self.score_distribution = {s: 0 for s in ValidationScore}
        for match in self.matches:
            if match.overall_score:
                self.score_distribution[match.overall_score] += 1
        
        # Calculate category accuracy
        for cat in IntelligenceCategory:
            scores = [
                m.validation_scores.get(cat)
                for m in self.matches
                if m.is_validated and cat in m.validation_scores
            ]
            if scores:
                correct = sum(1 for s in scores if s in [ValidationScore.CRUSH_IT, ValidationScore.NAIL_IT])
                self.category_accuracy[cat] = correct / len(scores)


# ============================================================
# SEASON INTELLIGENCE TRACKER
# ============================================================

@dataclass
class SeasonIntelligenceTracker:
    """
    Track intelligence accuracy across the whole season.
    
    This is the feedback loop for learning.
    """
    season: str
    league_id: int
    
    # All rounds
    rounds: List[RoundIntelligence] = field(default_factory=list)
    
    # Cumulative stats
    total_predictions: int = 0
    total_validated: int = 0
    
    # Overall accuracy
    overall_accuracy: float = 0.0
    accuracy_by_category: Dict[IntelligenceCategory, float] = field(default_factory=dict)
    accuracy_trend: List[float] = field(default_factory=list)  # Per round
    
    # Feature importance (learned)
    feature_importance_learned: Dict[str, float] = field(default_factory=dict)
    best_features: List[str] = field(default_factory=list)
    worst_features: List[str] = field(default_factory=list)
    
    # Patterns discovered
    patterns: List[str] = field(default_factory=list)
    
    def update_feature_importance(self):
        """Learn which features are most predictive."""
        # Aggregate feature performance across all validated matches
        feature_scores: Dict[str, List[float]] = {}
        
        for round_intel in self.rounds:
            for match in round_intel.matches:
                if match.is_validated and match.overall_score:
                    score_val = {
                        ValidationScore.CRUSH_IT: 1.0,
                        ValidationScore.NAIL_IT: 0.8,
                        ValidationScore.CLOSE: 0.5,
                        ValidationScore.MISS: 0.2,
                        ValidationScore.DISASTER: 0.0
                    }[match.overall_score]
                    
                    for feature in match.top_features:
                        if feature not in feature_scores:
                            feature_scores[feature] = []
                        feature_scores[feature].append(score_val)
        
        # Calculate average score per feature
        for feature, scores in feature_scores.items():
            self.feature_importance_learned[feature] = sum(scores) / len(scores)
        
        # Sort features
        sorted_features = sorted(
            self.feature_importance_learned.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        self.best_features = [f for f, _ in sorted_features[:10]]
        self.worst_features = [f for f, _ in sorted_features[-10:]]


# ============================================================
# HELPER: Create intelligence from KG snapshots
# ============================================================

def create_match_intelligence(
    fixture_id: int,
    home_snapshot: 'TeamKGSnapshot',
    away_snapshot: 'TeamKGSnapshot',
    h2h_data: Optional[Dict] = None,
    market_odds: Optional[Dict] = None
) -> MatchIntelligence:
    """
    Create match intelligence from team KG snapshots.
    
    This is where the magic happens:
    1. Compare team profiles
    2. Generate predictions for each category
    3. Track feature attribution
    """
    # This would be implemented with actual prediction logic
    # For now, just skeleton
    
    intelligence = MatchIntelligence(
        fixture_id=fixture_id,
        home_team_id=home_snapshot.team_id,
        home_team_name=home_snapshot.team_name,
        away_team_id=away_snapshot.team_id,
        away_team_name=away_snapshot.team_name,
        match_date=home_snapshot.snapshot_date,
        round_number=home_snapshot.round_number,
    )
    
    # TODO: Implement prediction logic for each take
    # - Compare attack vs defense profiles
    # - Factor in form
    # - Consider H2H
    # - Adjust for availability
    # - etc.
    
    return intelligence
