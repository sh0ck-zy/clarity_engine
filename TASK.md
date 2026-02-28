# TASK: Phase 1 - Enriched ML Output

## Context

We have a Match Intelligence system that generates narratives for football matches. The problem: narratives are disconnected from ML predictions. We need to ground narratives in ML output.

**Current state:**
- `report.json` has probabilities and drivers
- `context.json` has all match data (8 layers)
- `narrative.json` has 4-section text (but not grounded in ML)

**Goal:** Enrich ML output so the narrator can explain WHY the model predicts what it predicts.

---

## Task 1.1: Enrich driver output in report.json

**File:** `src/models/probabilistic.py`

Find where drivers are computed and add these fields to each driver:

### Current driver structure:
```json
{
  "feature": "away_venue_points",
  "value": 22.0,
  "contribution": 0.165
}
```

### New driver structure:
```json
{
  "feature": "away_venue_points",
  "value": 22.0,
  "contribution": 0.165,
  "direction": "for_draw",
  "display_name": "Away Team Home Record",
  "context_keys": ["factual.away.venue_points", "factual.away.venue_record"]
}
```

### Logic for `direction`:
- If contribution > 0 and pushes toward home_win → "for_home"
- If contribution > 0 and pushes toward draw → "for_draw"  
- If contribution > 0 and pushes toward away_win → "for_away"
- Use the predicted_result to determine which direction the positive contribution supports

### Add `driver_summary` to report:
```json
{
  "driver_summary": {
    "total_drivers": 3,
    "primary_driver": "away_venue_points",
    "primary_contribution": 0.165,
    "drivers_for_home": 1,
    "drivers_for_draw": 2,
    "drivers_for_away": 0
  }
}
```

---

## Task 1.2: Create driver explanations map

**File:** `src/models/driver_explanations.py` (NEW)

Create a mapping for each feature used in the model:

```python
"""
Human-readable explanations for ML model drivers.
Used by narrator to explain WHY the model predicts what it predicts.
"""

DRIVER_CONFIG = {
    "away_venue_points": {
        "display_name": "Away Team Home Record",
        "explanation_template": "{away_team} has {value} points at home this season ({venue_record}). {interpretation}",
        "context_keys": ["factual.away.venue_points", "factual.away.venue_record"],
        "interpretation": {
            "low": "This is poor - they struggle to defend their home ground.",
            "medium": "This is average home form.",
            "high": "This is strong - they're solid at home."
        },
        "thresholds": {"low": 15, "high": 25}
    },
    
    "home_venue_points": {
        "display_name": "Home Team Home Record",
        "explanation_template": "{home_team} has {value} points at home ({venue_record}). {interpretation}",
        "context_keys": ["factual.home.venue_points", "factual.home.venue_record"],
        "interpretation": {
            "low": "They've been vulnerable at home.",
            "medium": "Decent home record.",
            "high": "Fortress - they rarely drop points here."
        },
        "thresholds": {"low": 18, "high": 30}
    },
    
    "home_strength_delta": {
        "display_name": "Venue Strength Gap",
        "explanation_template": "{home_team} has {home_val} home points vs {away_team}'s {away_val} away points. Gap of {value}.",
        "context_keys": ["factual.home.venue_points", "factual.away.away_points"],
        "interpretation": {
            "large_positive": "Strong home advantage in this matchup.",
            "small": "Venue factor is neutral.",
            "large_negative": "Away team actually performs better on the road than home team at home."
        },
        "thresholds": {"small": 5}
    },
    
    "elo_delta": {
        "display_name": "ELO Rating Gap",
        "explanation_template": "ELO gap of {value:.0f} points. {interpretation}",
        "context_keys": ["ml_inference.elo_delta"],
        "interpretation": {
            "large_positive": "Significant quality gap favouring home team.",
            "small": "Teams are evenly matched by ELO rating.",
            "large_negative": "Away team is the stronger side on paper."
        },
        "thresholds": {"small": 50}
    },
    
    "form_points_delta": {
        "display_name": "Recent Form Gap",
        "explanation_template": "{home_team} has {home_form} ({home_pts} pts from last 5) vs {away_team}'s {away_form} ({away_pts} pts).",
        "context_keys": [
            "factual.home.form_string", "factual.home.form_points",
            "factual.away.form_string", "factual.away.form_points"
        ],
        "interpretation": {
            "large_positive": "Home team in much better form.",
            "small": "Similar recent form.",
            "large_negative": "Away team coming in with better momentum."
        },
        "thresholds": {"small": 3}
    },
    
    "xg_diff_last5_delta": {
        "display_name": "Expected Goals Gap (Last 5)",
        "explanation_template": "{home_team} xG diff {home_xg:+.2f} vs {away_team} {away_xg:+.2f} in last 5 matches.",
        "context_keys": ["factual.home.xg_diff_last5", "factual.away.xg_diff_last5"],
        "interpretation": {
            "large_positive": "Home team creating much more than conceding.",
            "small": "Similar underlying performance.",
            "large_negative": "Away team's underlying numbers are stronger."
        },
        "thresholds": {"small": 1.5}
    },
    
    "goal_diff_season_delta": {
        "display_name": "Season Goal Difference Gap",
        "explanation_template": "{home_team} GD {home_gd:+d} vs {away_team} GD {away_gd:+d}. Season gap of {value:+.0f}.",
        "context_keys": ["factual.home.goal_difference", "factual.away.goal_difference"],
        "interpretation": {
            "large_positive": "Home team has been dominant all season.",
            "small": "Similar goal difference.",
            "large_negative": "Away team has the better season record."
        },
        "thresholds": {"small": 10}
    },
    
    "position_delta": {
        "display_name": "League Position Gap",
        "explanation_template": "{home_team} ({home_pos}{home_suffix}) vs {away_team} ({away_pos}{away_suffix}). {interpretation}",
        "context_keys": ["factual.home.position", "factual.away.position"],
        "interpretation": {
            "large_positive": "Home team significantly higher in table.",
            "small": "Close in the standings.",
            "large_negative": "Away team is the higher-placed side."
        },
        "thresholds": {"small": 4}
    },
    
    "clean_sheets_delta": {
        "display_name": "Defensive Solidity Gap",
        "explanation_template": "{home_team} has {home_cs} clean sheets in last 5, {away_team} has {away_cs}.",
        "context_keys": ["factual.home.clean_sheets_last5", "factual.away.clean_sheets_last5"],
        "interpretation": {
            "positive": "Home team keeping more clean sheets.",
            "zero": "Similar defensive records.",
            "negative": "Away team has been more solid defensively."
        },
        "thresholds": {}
    }
}


def get_driver_config(feature: str) -> dict:
    """Get configuration for a driver feature."""
    return DRIVER_CONFIG.get(feature, {
        "display_name": feature.replace("_", " ").title(),
        "explanation_template": "{feature} = {value}",
        "context_keys": [],
        "interpretation": {},
        "thresholds": {}
    })


def get_interpretation(feature: str, value: float) -> str:
    """Get interpretation text based on value and thresholds."""
    config = get_driver_config(feature)
    interp = config.get("interpretation", {})
    thresholds = config.get("thresholds", {})
    
    if not interp:
        return ""
    
    # Handle different threshold types
    if "low" in thresholds and "high" in thresholds:
        if value < thresholds["low"]:
            return interp.get("low", "")
        elif value > thresholds["high"]:
            return interp.get("high", "")
        else:
            return interp.get("medium", "")
    
    elif "small" in thresholds:
        if abs(value) < thresholds["small"]:
            return interp.get("small", "")
        elif value > 0:
            return interp.get("large_positive", "")
        else:
            return interp.get("large_negative", "")
    
    elif "positive" in interp:
        if value > 0:
            return interp.get("positive", "")
        elif value < 0:
            return interp.get("negative", "")
        else:
            return interp.get("zero", "")
    
    return ""
```

---

## Task 1.3: Integrate into probabilistic.py

**File:** `src/models/probabilistic.py`

Find the function that generates the report and modify it to:

1. Import the driver config:
```python
from models.driver_explanations import get_driver_config, get_interpretation
```

2. Enrich each driver with the new fields:
```python
def _enrich_driver(driver: dict, predicted_result: str) -> dict:
    """Add display_name, direction, and context_keys to driver."""
    feature = driver["feature"]
    config = get_driver_config(feature)
    
    # Determine direction based on contribution and predicted result
    contribution = driver["contribution"]
    if contribution > 0:
        direction = f"for_{predicted_result.lower()}"
    else:
        # Negative contribution means it pushes AGAINST the prediction
        direction = "against_prediction"
    
    return {
        **driver,
        "display_name": config["display_name"],
        "direction": direction,
        "context_keys": config["context_keys"],
        "interpretation_hint": get_interpretation(feature, driver["value"])
    }
```

3. Add driver_summary to the report:
```python
def _compute_driver_summary(drivers: list, predicted_result: str) -> dict:
    """Compute summary statistics for drivers."""
    if not drivers:
        return {}
    
    # Sort by absolute contribution
    sorted_drivers = sorted(drivers, key=lambda d: abs(d["contribution"]), reverse=True)
    primary = sorted_drivers[0]
    
    return {
        "total_drivers": len(drivers),
        "primary_driver": primary["feature"],
        "primary_contribution": primary["contribution"],
        "top_3_drivers": [d["feature"] for d in sorted_drivers[:3]]
    }
```

---

## Verification

After implementation, run:

```bash
cd ~/Projects/clarity_engine
source venv/bin/activate

# Generate a round with context only (no narrative)
python scripts/generate_round.py 27 --context-only --league PL --league-id 47

# Check the enriched report.json
cat output/rounds/PL_R27/matches/Spurs_vs_Arsenal/report.json | python -m json.tool

# Should see:
# - drivers with "display_name", "direction", "context_keys"
# - "driver_summary" section
```

Expected output structure:
```json
{
  "probabilities": {"home_win": 0.30, "draw": 0.44, "away_win": 0.26},
  "prediction": {"predicted_result": "D", "confidence": "low"},
  "drivers": [
    {
      "feature": "away_venue_points",
      "value": 22.0,
      "contribution": 0.165,
      "display_name": "Away Team Home Record",
      "direction": "for_draw",
      "context_keys": ["factual.away.venue_points", "factual.away.venue_record"],
      "interpretation_hint": "This is poor - they struggle to defend their home ground."
    }
  ],
  "driver_summary": {
    "total_drivers": 3,
    "primary_driver": "away_venue_points",
    "primary_contribution": 0.165,
    "top_3_drivers": ["away_venue_points", "home_strength_delta", "elo_delta"]
  }
}
```

---

## Files to create/modify

| File | Action |
|------|--------|
| `src/models/driver_explanations.py` | CREATE |
| `src/models/probabilistic.py` | MODIFY (enrich drivers) |

---

## Notes

- The model currently uses 8 features (see `src/models/config.py` for FEATURE_COLS)
- Drivers come from logistic regression coefficients × feature values
- Keep backward compatibility - old fields should still work
