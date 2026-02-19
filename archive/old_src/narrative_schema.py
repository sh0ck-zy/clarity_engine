"""
Narrative Schema Validation - Phase 1 (P1-006)

Enforces strict schema validation for LLM-generated narratives.
Ensures all outputs are comparable and evaluatable.

Usage:
    from src.analysis.narrative_schema import validate_narrative, NarrativeOutput

    is_valid, errors = validate_narrative(llm_response)
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import json
import re


# ============================================================
# NARRATIVE SCHEMA DEFINITIONS
# ============================================================

@dataclass
class ScorePrediction:
    """Predicted final score."""
    home: int
    away: int
    confidence: int  # 0-100

    def to_string(self) -> str:
        return f"{self.home}-{self.away}"


@dataclass
class KeyDriver:
    """A key factor driving the prediction."""
    factor: str  # e.g., "Form", "Injuries", "Tactical Matchup"
    description: str
    impact: str  # "positive", "negative", "neutral"
    weight: float  # 0-1, how much this factor influences prediction


@dataclass
class SwingFactor:
    """A factor that could change the outcome."""
    factor: str
    upside_scenario: str
    downside_scenario: str
    probability: float  # 0-1


@dataclass
class RiskFlag:
    """Identified risk in the prediction."""
    risk_type: str  # "tactical", "form", "injury", "motivation", "referee"
    description: str
    severity: str  # "low", "medium", "high"


@dataclass
class GameFlow:
    """Expected flow of the match."""
    opening_period: str  # Description of first 30 mins
    mid_game: str  # Description of middle period
    closing_period: str  # Description of final 20 mins
    likely_scorer_first: Optional[str] = None
    expected_tempo: str = "balanced"  # "high", "balanced", "low"


@dataclass
class TacticalDynamic:
    """Tactical analysis."""
    home_approach: str
    away_approach: str
    key_battle: str  # e.g., "Midfield control"
    formation_matchup: Optional[str] = None


@dataclass
class MarketVerdict:
    """Relationship to betting market."""
    action: str  # "NO_ACTION", "AVOID_PUBLIC_SIDE", "BET_1X2"
    selection: Optional[str] = None  # "HOME", "DRAW", "AWAY" if betting
    reasoning: str = ""
    edge_description: Optional[str] = None


@dataclass
class GlassBoxLogic:
    """Transparent reasoning chain."""
    primary_reasoning: str
    factor_weights: Dict[str, float]  # e.g., {"form": 0.3, "xg": 0.25}
    confidence_drivers: List[str]
    uncertainty_sources: List[str]


@dataclass
class NarrativeOutput:
    """
    Complete narrative output schema.

    All LLM responses MUST conform to this structure.
    """
    # Core Prediction
    prediction: ScorePrediction
    headline: str  # Max 100 chars

    # Narrative Components
    game_flow: GameFlow
    tactical_dynamic: TacticalDynamic
    key_drivers: List[KeyDriver]
    swing_factors: List[SwingFactor]
    risk_flags: List[RiskFlag]

    # Market Analysis
    market_verdict: MarketVerdict

    # Transparency
    glass_box_logic: GlassBoxLogic

    # Metadata
    model_name: str
    prompt_version: str
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


# ============================================================
# REQUIRED FIELDS
# ============================================================

REQUIRED_FIELDS = [
    "prediction",
    "prediction.home",
    "prediction.away",
    "prediction.confidence",
    "headline",
    "game_flow",
    "game_flow.opening_period",
    "tactical_dynamic",
    "tactical_dynamic.home_approach",
    "tactical_dynamic.away_approach",
    "key_drivers",
    "market_verdict",
    "market_verdict.action",
    "glass_box_logic",
    "glass_box_logic.primary_reasoning",
    "glass_box_logic.factor_weights"
]

VALID_ACTIONS = ["NO_ACTION", "AVOID_PUBLIC_SIDE", "BET_1X2"]
VALID_SELECTIONS = ["HOME", "DRAW", "AWAY", None]
VALID_SEVERITIES = ["low", "medium", "high"]
VALID_IMPACTS = ["positive", "negative", "neutral"]
VALID_TEMPOS = ["high", "balanced", "low"]


# ============================================================
# VALIDATION FUNCTIONS
# ============================================================

def _get_nested(obj: Any, path: str) -> Any:
    """Get nested value using dot notation."""
    parts = path.split('.')
    current = obj
    for part in parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None
    return current


def validate_narrative(
    response: Union[Dict, str],
    strict: bool = True
) -> tuple[bool, List[str]]:
    """
    Validate LLM response against narrative schema.

    Args:
        response: LLM response (dict or JSON string)
        strict: If True, fail on any error. If False, allow warnings.

    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    warnings = []

    # Parse JSON if string
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON: {str(e)}"]

    # Check required fields
    for field_path in REQUIRED_FIELDS:
        value = _get_nested(response, field_path)
        if value is None:
            errors.append(f"Missing required field: {field_path}")

    # Validate prediction
    pred = response.get('prediction', {})
    if pred:
        if not isinstance(pred.get('home'), int) or pred.get('home', -1) < 0:
            errors.append("prediction.home must be a non-negative integer")
        if not isinstance(pred.get('away'), int) or pred.get('away', -1) < 0:
            errors.append("prediction.away must be a non-negative integer")
        if not isinstance(pred.get('confidence'), int):
            errors.append("prediction.confidence must be an integer")
        elif not (0 <= pred.get('confidence', -1) <= 100):
            errors.append("prediction.confidence must be 0-100")

    # Validate headline length
    headline = response.get('headline', '')
    if len(headline) > 150:
        warnings.append(f"Headline too long ({len(headline)} chars), should be <100")
    if len(headline) < 10:
        errors.append("Headline too short (must be >10 chars)")

    # Validate market_verdict
    mv = response.get('market_verdict', {})
    if mv:
        action = mv.get('action')
        if action not in VALID_ACTIONS:
            errors.append(f"Invalid market_verdict.action: {action}. Must be one of {VALID_ACTIONS}")

        selection = mv.get('selection')
        if action == 'BET_1X2' and selection not in ['HOME', 'DRAW', 'AWAY']:
            errors.append(f"BET_1X2 requires valid selection (HOME/DRAW/AWAY), got: {selection}")

    # Validate key_drivers
    drivers = response.get('key_drivers', [])
    if not isinstance(drivers, list):
        errors.append("key_drivers must be a list")
    elif len(drivers) < 2:
        warnings.append("Should have at least 2 key_drivers for meaningful analysis")
    else:
        for i, driver in enumerate(drivers):
            if not isinstance(driver, dict):
                errors.append(f"key_drivers[{i}] must be an object")
                continue
            if driver.get('impact') not in VALID_IMPACTS:
                warnings.append(f"key_drivers[{i}].impact should be: {VALID_IMPACTS}")
            weight = driver.get('weight', 0)
            if not (0 <= weight <= 1):
                warnings.append(f"key_drivers[{i}].weight should be 0-1, got {weight}")

    # Validate risk_flags
    risks = response.get('risk_flags', [])
    if isinstance(risks, list):
        for i, risk in enumerate(risks):
            if isinstance(risk, dict):
                if risk.get('severity') not in VALID_SEVERITIES:
                    warnings.append(f"risk_flags[{i}].severity should be: {VALID_SEVERITIES}")

    # Validate glass_box_logic
    logic = response.get('glass_box_logic', {})
    if logic:
        weights = logic.get('factor_weights', {})
        if not isinstance(weights, dict):
            errors.append("glass_box_logic.factor_weights must be an object")
        elif weights:
            total_weight = sum(weights.values())
            if not (0.9 <= total_weight <= 1.1):
                warnings.append(f"factor_weights should sum to ~1.0, got {total_weight:.2f}")

    # Validate game_flow
    gf = response.get('game_flow', {})
    if gf:
        tempo = gf.get('expected_tempo')
        if tempo and tempo not in VALID_TEMPOS:
            warnings.append(f"game_flow.expected_tempo should be: {VALID_TEMPOS}")

    # Final result
    if strict:
        all_issues = errors + warnings
        return len(errors) == 0, errors + (warnings if errors else [])
    else:
        return len(errors) == 0, errors


def parse_narrative(response: Union[Dict, str]) -> Optional[NarrativeOutput]:
    """
    Parse and validate LLM response into NarrativeOutput object.

    Args:
        response: LLM response (dict or JSON string)

    Returns:
        NarrativeOutput or None if validation fails
    """
    is_valid, errors = validate_narrative(response, strict=False)

    if not is_valid:
        print(f"❌ Narrative validation failed: {errors}")
        return None

    if isinstance(response, str):
        response = json.loads(response)

    try:
        # Parse prediction
        pred_data = response.get('prediction', {})
        prediction = ScorePrediction(
            home=int(pred_data.get('home', 0)),
            away=int(pred_data.get('away', 0)),
            confidence=int(pred_data.get('confidence', 50))
        )

        # Parse game_flow
        gf_data = response.get('game_flow', {})
        game_flow = GameFlow(
            opening_period=gf_data.get('opening_period', ''),
            mid_game=gf_data.get('mid_game', ''),
            closing_period=gf_data.get('closing_period', ''),
            likely_scorer_first=gf_data.get('likely_scorer_first'),
            expected_tempo=gf_data.get('expected_tempo', 'balanced')
        )

        # Parse tactical_dynamic
        td_data = response.get('tactical_dynamic', {})
        tactical_dynamic = TacticalDynamic(
            home_approach=td_data.get('home_approach', ''),
            away_approach=td_data.get('away_approach', ''),
            key_battle=td_data.get('key_battle', ''),
            formation_matchup=td_data.get('formation_matchup')
        )

        # Parse key_drivers
        key_drivers = []
        for kd in response.get('key_drivers', []):
            key_drivers.append(KeyDriver(
                factor=kd.get('factor', ''),
                description=kd.get('description', ''),
                impact=kd.get('impact', 'neutral'),
                weight=float(kd.get('weight', 0))
            ))

        # Parse swing_factors
        swing_factors = []
        for sf in response.get('swing_factors', []):
            swing_factors.append(SwingFactor(
                factor=sf.get('factor', ''),
                upside_scenario=sf.get('upside_scenario', ''),
                downside_scenario=sf.get('downside_scenario', ''),
                probability=float(sf.get('probability', 0.5))
            ))

        # Parse risk_flags
        risk_flags = []
        for rf in response.get('risk_flags', []):
            risk_flags.append(RiskFlag(
                risk_type=rf.get('risk_type', 'unknown'),
                description=rf.get('description', ''),
                severity=rf.get('severity', 'medium')
            ))

        # Parse market_verdict
        mv_data = response.get('market_verdict', {})
        market_verdict = MarketVerdict(
            action=mv_data.get('action', 'NO_ACTION'),
            selection=mv_data.get('selection'),
            reasoning=mv_data.get('reasoning', ''),
            edge_description=mv_data.get('edge_description')
        )

        # Parse glass_box_logic
        gl_data = response.get('glass_box_logic', {})
        glass_box_logic = GlassBoxLogic(
            primary_reasoning=gl_data.get('primary_reasoning', ''),
            factor_weights=gl_data.get('factor_weights', {}),
            confidence_drivers=gl_data.get('confidence_drivers', []),
            uncertainty_sources=gl_data.get('uncertainty_sources', [])
        )

        return NarrativeOutput(
            prediction=prediction,
            headline=response.get('headline', ''),
            game_flow=game_flow,
            tactical_dynamic=tactical_dynamic,
            key_drivers=key_drivers,
            swing_factors=swing_factors,
            risk_flags=risk_flags,
            market_verdict=market_verdict,
            glass_box_logic=glass_box_logic,
            model_name=response.get('model_name', 'unknown'),
            prompt_version=response.get('prompt_version', 'unknown')
        )

    except Exception as e:
        print(f"❌ Failed to parse narrative: {e}")
        return None


def validate_no_external_facts(response: Dict, context: Dict) -> tuple[bool, List[str]]:
    """
    Validate that narrative doesn't contain facts not in context.

    This helps ensure the LLM is grounded in the provided data.

    Args:
        response: LLM narrative response
        context: Match context that was provided to LLM

    Returns:
        (is_valid, list_of_issues)
    """
    issues = []

    # Get team names from context
    context_teams = set()
    if 'home' in context:
        context_teams.add(context['home'].get('identity', {}).get('name', '').lower())
    if 'away' in context:
        context_teams.add(context['away'].get('identity', {}).get('name', '').lower())

    # Convert response to string for text analysis
    response_text = json.dumps(response).lower()

    # Check for common hallucination patterns
    # (These are heuristics - not perfect but catch obvious issues)

    # 1. Check for specific player names (we don't provide these in basic context)
    # This is a simple heuristic - would need player list to be thorough

    # 2. Check for future tense claims about past events
    future_patterns = [
        r"will be announced",
        r"expected to announce",
        r"confirmed later"
    ]
    for pattern in future_patterns:
        if re.search(pattern, response_text):
            issues.append(f"Contains forward-looking claim: '{pattern}'")

    # 3. Check for injury claims if no injury data provided
    if 'absences' not in str(context):
        injury_patterns = [
            r"is injured",
            r"ruled out",
            r"suspended for",
            r"missing through"
        ]
        for pattern in injury_patterns:
            if re.search(pattern, response_text):
                issues.append(f"Claims injury without data: '{pattern}'")

    return len(issues) == 0, issues


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def create_empty_narrative(
    home: int = 0,
    away: int = 0,
    confidence: int = 50,
    headline: str = "Match Preview"
) -> NarrativeOutput:
    """Create a minimal valid narrative structure."""
    return NarrativeOutput(
        prediction=ScorePrediction(home=home, away=away, confidence=confidence),
        headline=headline,
        game_flow=GameFlow(
            opening_period="",
            mid_game="",
            closing_period=""
        ),
        tactical_dynamic=TacticalDynamic(
            home_approach="",
            away_approach="",
            key_battle=""
        ),
        key_drivers=[],
        swing_factors=[],
        risk_flags=[],
        market_verdict=MarketVerdict(action="NO_ACTION"),
        glass_box_logic=GlassBoxLogic(
            primary_reasoning="",
            factor_weights={},
            confidence_drivers=[],
            uncertainty_sources=[]
        ),
        model_name="unknown",
        prompt_version="unknown"
    )


if __name__ == "__main__":
    # Test validation
    print("Testing Narrative Schema Validation...")

    # Valid example
    valid_response = {
        "prediction": {"home": 2, "away": 1, "confidence": 65},
        "headline": "Liverpool expected to edge past resilient Wolves",
        "game_flow": {
            "opening_period": "High press from Liverpool",
            "mid_game": "Wolves counter-attacks",
            "closing_period": "Liverpool tire but hold on",
            "expected_tempo": "high"
        },
        "tactical_dynamic": {
            "home_approach": "High pressing 4-3-3",
            "away_approach": "Deep block with counters",
            "key_battle": "Midfield control"
        },
        "key_drivers": [
            {"factor": "Form", "description": "Liverpool 4W in last 5", "impact": "positive", "weight": 0.3},
            {"factor": "xG", "description": "Liverpool +1.2 xG diff", "impact": "positive", "weight": 0.25}
        ],
        "swing_factors": [],
        "risk_flags": [
            {"risk_type": "form", "description": "Wolves improving", "severity": "low"}
        ],
        "market_verdict": {
            "action": "NO_ACTION",
            "reasoning": "Fair price"
        },
        "glass_box_logic": {
            "primary_reasoning": "Liverpool's form and home advantage",
            "factor_weights": {"form": 0.3, "xg": 0.25, "home": 0.2, "h2h": 0.15, "tactical": 0.1},
            "confidence_drivers": ["Strong form", "Home advantage"],
            "uncertainty_sources": ["Wolves recent improvement"]
        }
    }

    is_valid, errors = validate_narrative(valid_response)
    print(f"\n✅ Valid example: {is_valid}")
    if errors:
        print(f"   Warnings: {errors}")

    # Invalid example
    invalid_response = {
        "prediction": {"home": -1, "away": 1},  # Missing confidence, invalid home
        "headline": "Short"  # Too short
    }

    is_valid, errors = validate_narrative(invalid_response)
    print(f"\n❌ Invalid example: {is_valid}")
    print(f"   Errors: {errors[:5]}...")  # Show first 5

    print("\n✅ Schema validation test complete!")
