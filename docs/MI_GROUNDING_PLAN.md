# Match Intelligence with ML Grounding - Implementation Plan

## Overview

Transform Match Intelligence from disconnected narratives to ML-grounded, measurable analysis.

**Core Principle:** ML is ground truth. MI explains and enriches.

```
ML (probabilities + drivers) = GROUND TRUTH
                ↓
Match Intelligence EXPLAINS each driver
                ↓
Uses 8 layers for context
                ↓
MEASURABLE output
```

---

## Phase 1: Enriched ML Output

### 1.1 Modify report.json

**File:** `src/models/probabilistic.py`

Add to each driver:
- `direction`: "for_home" | "for_draw" | "for_away"
- `explanation_hint`: Human-readable name
- `context_key`: Path to data in context.json

### 1.2 Create driver_explanations.py

**File:** `src/models/driver_explanations.py`

Map each feature to:
- Human-readable name
- Template for explanation
- Interpretation rules
- Context keys needed

---

## Phase 2: Grounded Narrator

### 2.1 New system prompt

Narrator MUST:
1. Explain EACH driver in human language
2. Add 8-layer context (Position, Form, Style, Attack, Defense, Home/Away, Trajectory, Identity)
3. Be CONSISTENT with model direction
4. Never contradict the model

### 2.2 New output schema

```json
{
  "driver_explanations": [
    {
      "driver": "away_venue_points",
      "explanation": "Spurs only have 10 points at home...",
      "data_cited": ["away.venue_points=10"]
    }
  ],
  "layer_insights": [
    {"layer": "position", "insight": "1st vs 16th", "relevance": "high"}
  ],
  "narrative": {
    "a_historia": "...",
    "onde_se_decide": "...",
    "o_que_pode_correr_mal": "...",
    "bottom_line": "..."
  },
  "grounding_check": {
    "drivers_explained": 3,
    "drivers_total": 3,
    "direction_consistent": true
  }
}
```

---

## Phase 3: Grounding Validator

### 3.1 Create validator

**File:** `src/validation/grounding_validator.py`

Checks:
1. Driver coverage (all explained?)
2. Direction consistency (narrative aligns with ML?)
3. Citation accuracy (data cited exists and is correct?)
4. Layer insights (enough context?)
5. Confident conclusion (no wishy-washy?)

### 3.2 CLI script

**File:** `scripts/validate_grounding.py`

```bash
python scripts/validate_grounding.py PL_R27 --verbose
```

---

## Phase 4: HTML Visualization

### 4.1 New sections in match cards

1. **Model Prediction Banner** - Clear display of prediction
2. **Driver Explanations** - Each driver explained with citations
3. **8-Layer Insights** - Grid of layer context
4. **Grounding Score** - Visual quality indicator

---

## Phase 5: Pipeline Integration

### 5.1 generate_round.py

Add `--grounded` flag (or make default)

### 5.2 quality_check.py

Add grounding components to MIS:
- driver_coverage: 25%
- direction_consistent: 20%
- layer_insights: 15%

---

## Phase 6: Multi-League Support

### 6.1 Make market odds optional

Some leagues don't have Bet365 odds. Fill with neutral 0.33/0.33/0.33.

### 6.2 Verify league-agnostic

All code should work for PL, Liga Portugal, Brasileirão, etc.

---

## Files Summary

### New Files
- `src/models/driver_explanations.py`
- `src/validation/__init__.py`
- `src/validation/grounding_validator.py`
- `scripts/validate_grounding.py`

### Modified Files
- `src/models/probabilistic.py`
- `src/intelligence/narrator.py`
- `scripts/generate_round.py`
- `scripts/quality_check.py`
- `scripts/render_html.py`
- `src/models/feature_builder.py`

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Driver coverage | 100% |
| Direction consistency | 100% |
| Citation accuracy | ≥95% |
| Layer insights | ≥4/match |
| Grounding score | ≥80% |
| Cross-league variance | <5% |

---

## Estimated Timeline

| Phase | Time |
|-------|------|
| Phase 1 | 2-3h |
| Phase 2 | 3-4h |
| Phase 3 | 2h |
| Phase 4 | 2-3h |
| Phase 5 | 1-2h |
| Phase 6 | 1-2h |
| **Total** | **12-16h** |

---

*Created: 2026-02-28*
