# Data Sources Analysis: FotMob vs API-Football

**Date:** 2026-02-15  
**Status:** Complete schema definitions for gap analysis  
**Updated:** Corrected to matchup-centric approach

---

## 🔑 Key Insight

**Pre-match intelligence is built FROM post-match data of previous matches!**

```
Past Matches (post-match data) → Aggregation → Matchup Intelligence → Prediction
```

This means **FotMob is the primary source** for BOTH:
- Post-match analysis (direct data)
- Pre-match intelligence (derived from historical post-match data)

API-Football is a **secondary/validation layer** for market context.

---

## Overview

This document analyzes the data available from two primary sources:
- **FotMob** - Rich match detail data (backfill complete) - **PRIMARY**
- **API-Football** - Structured API with predictions, odds, standings - **SECONDARY**

## Schema Files Created

| File | Purpose |
|------|---------|
| `src/models/api_football_pre_match.py` | All pre-match fields from API-Football |
| `src/models/api_football_post_match.py` | All post-match fields from API-Football |
| `src/models/data_comparison.py` | Comparison utilities and intelligence layers |

---

## Layer-by-Layer Comparison

### 🟢 FotMob Wins (use FotMob)

| Layer | FotMob | API-Football | Notes |
|-------|--------|--------------|-------|
| **Shotmap** | ✅ very_high | ❌ none | Per-shot xG with coordinates |
| **Momentum** | ✅ high | ❌ none | Match flow visualization |
| **Match Facts** | ✅ high | ❌ none | MOTM, insights, top players |
| **Commentary** | ✅ high | ❌ none | Minute-by-minute text |
| **Lineups** | ✅ very_high | ✅ high | Better ratings, fantasy scores |
| **xG** | ✅ very_high | ✅ high | Shot-level xG vs team only |

### 🔵 API-Football Wins (use API-Football)

| Layer | FotMob | API-Football | Notes |
|-------|--------|--------------|-------|
| **Standings** | ❌ none | ✅ very_high | Full table with home/away |
| **H2H** | ❌ none | ✅ very_high | Historical matches |
| **Predictions** | ❌ none | ✅ very_high | Probabilities, comparison |
| **Odds** | ❌ none | ✅ very_high | Multi-bookmaker with history |
| **Form** | ✅ medium | ✅ very_high | Detailed analysis in predictions |

### ⚖️ Tie (use both for validation)

| Layer | FotMob | API-Football | Notes |
|-------|--------|--------------|-------|
| **Fixture Info** | ✅ high | ✅ high | Both complete |
| **Injuries** | ✅ high | ✅ high | Both have data |
| **Player Stats** | ✅ very_high | ✅ very_high | Cross-validate |
| **Team Stats** | ✅ very_high | ✅ very_high | Cross-validate |
| **Events** | ✅ high | ✅ high | Both have full timeline |

---

## Unique Strengths

### FotMob Exclusive
- 📍 **Shotmap with per-shot xG coordinates** - Visual analysis
- 📈 **Momentum/match flow data** - Match dynamics
- 📋 **Match facts and insights** - MOTM, key moments
- ⭐ **Player ratings with fantasy scores** - Performance metrics
- 📝 **Commentary timeline** - Minute-by-minute narrative
- 🚑 **Unavailable players in lineup** - Inline injury data

### API-Football Exclusive
- 📊 **League standings with full breakdown** - Position, form, records
- 🎯 **Predictions with comparison metrics** - Probabilities, advice
- 💰 **Multi-bookmaker odds with history** - Market intelligence
- 🤝 **H2H historical matches** - Past encounters
- 🏥 **Dedicated injuries endpoint** - Structured absence data
- 📈 **Structured team season statistics** - Goals by minute, penalties

---

## Intelligence Layer Architecture (Corrected)

```
┌─────────────────────────────────────────────────────────────────────┐
│                    THE REAL DATA FLOW                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  HISTORICAL POST-MATCH DATA (FotMob - last N matches per team)      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ • Shotmaps → shot patterns, xG quality, finishing ability    │   │
│  │ • Momentum → when teams are strong/weak, response patterns   │   │
│  │ • Player stats → form, key performers, who's hot/cold        │   │
│  │ • Lineups → tactical flexibility, rotation patterns          │   │
│  │ • Team stats → possession style, defensive solidity          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                           │                                          │
│                           ▼                                          │
│  MATCHUP INTELLIGENCE (derived pre-match analysis)                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ • Team tactical profiles (style, formations, patterns)       │   │
│  │ • Form trajectories (xG trends, momentum, regression risk)   │   │
│  │ • H2H intelligence (historical patterns between these teams) │   │
│  │ • Key player matchups (who wins which battles?)              │   │
│  │ • Style matchup prediction (possession vs counter, etc.)     │   │
│  │ • Predicted xG, goals, patterns                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                           │                                          │
│                           ▼                                          │
│  MARKET CONTEXT (API-Football - validation layer)                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ • Odds → what the market thinks                              │   │
│  │ • Predictions → API model probabilities                      │   │
│  │ • Standings → league position context                        │   │
│  │ • Compare with our derived intelligence → find value         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Source Priority

| Intelligence Layer | Primary Source | Why |
|--------------------|----------------|-----|
| Team tactical profile | FotMob history | Shotmaps, momentum, detailed stats |
| Form trajectory | FotMob history | xG trends more predictive than results |
| H2H intelligence | FotMob history | Full match detail for past meetings |
| Player matchups | FotMob history | Individual player performances |
| Availability impact | Both | FotMob ratings + API-Football injuries |
| Market context | API-Football | Odds, predictions, standings |
| Value detection | Derived | Compare our model vs market |

---

## Custom Metrics Potential

### From FotMob Only
| Metric | Formula | Use Case |
|--------|---------|----------|
| `xG_outperformance` | `actual_goals - sum(shot_xg)` | Identify lucky/unlucky teams |
| `shot_quality_differential` | `(home_xg/shots) - (away_xg/shots)` | Measure chance creation |

### From API-Football Only
| Metric | Formula | Use Case |
|--------|---------|----------|
| `market_vs_model_divergence` | `abs(implied_prob - prediction_percent)` | Find value bets |
| `h2h_venue_adjusted_score` | `h2h_win_rate * venue_factor * form_factor` | Historical predictor |

### Requires Both Sources
| Metric | Formula | Use Case |
|--------|---------|----------|
| `form_momentum_score` | `weighted(form, position_change, momentum)` | Team trajectory |
| `injury_impact_score` | `sum(missing_rating * minutes_share)` | Adjust for absences |

---

## Data Flow for Match Analysis

```
PRE-MATCH (before kickoff)
├── API-Football
│   ├── /fixtures → fixture info
│   ├── /standings → league position
│   ├── /predictions → H2H, comparison, probabilities
│   ├── /odds → market prices
│   └── /injuries → player availability
│
└── FotMob (limited pre-match)
    └── Team form in match facts

POST-MATCH (after final whistle)
├── FotMob (primary)
│   ├── Shotmap → per-shot xG analysis
│   ├── Momentum → match flow
│   ├── Player stats → ratings, detailed stats
│   ├── Match facts → MOTM, insights
│   └── Commentary → narrative
│
└── API-Football (secondary/validation)
    ├── /fixtures/statistics → team stats, xG
    ├── /fixtures/lineups → formations
    ├── /fixtures/events → goals, cards
    └── /fixtures/players → player stats
```

---

## Usage

```python
from src.models import (
    # Generic schemas
    PreMatchContext,
    PostMatchReality,
    
    # API-Football specific (gap analysis)
    APIFootballPreMatchContext,
    APIFootballPostMatchContext,
    
    # FotMob
    FotMobMatchDetail,
    
    # Comparison tools
    compare_sources,
    print_comparison_report,
    INTELLIGENCE_ARCHITECTURE,
)

# Run comparison
comparison = compare_sources()
print(print_comparison_report(comparison))

# Check what data is available
from src.models import FOTMOB_COVERAGE, API_FOOTBALL_COVERAGE, DataLayer

print(FOTMOB_COVERAGE[DataLayer.SHOTMAP])
# {'available': True, 'depth': 'very_high', 'fields': ['x', 'y', 'xG', ...]}
```

---

## Next Steps

1. **Build API-Football backfill** - Mirror FotMob backfill for API-Football
2. **Create data merger** - Combine both sources into unified `MatchRecord`
3. **Implement custom metrics** - Calculate derived metrics from combined data
4. **Build inference pipeline** - Use intelligence layers for match predictions
5. **Knowledge graph integration** - Link entities across matches/seasons

---

## Files Modified/Created

```
src/models/
├── __init__.py                # Updated with new exports
├── pre_match.py               # Existing (unchanged)
├── post_match.py              # Existing (unchanged)
├── fotmob.py                  # Existing (unchanged)
├── api_football_pre_match.py  # API-Football raw pre-match schema
├── api_football_post_match.py # API-Football raw post-match schema
├── data_comparison.py         # Comparison utilities + architecture
└── matchup_intelligence.py    # ⭐ NEW: Core matchup intelligence schema

docs/
└── DATA_SOURCES_ANALYSIS.md   # This document
```

## Key Schema: MatchupIntelligence

The `matchup_intelligence.py` contains the core pre-match analysis schema:

```python
from src.models import MatchupIntelligenceBuilder

# Build matchup intelligence from historical data
builder = MatchupIntelligenceBuilder(
    fixture_id=12345,
    home_team_id=1,
    home_team_name="Liverpool",
    away_team_id=2,
    away_team_name="Arsenal",
    match_date=date(2026, 2, 20)
)

# Add FotMob historical data
builder.add_home_matches(liverpool_last_10_matches)  # FotMobMatchDetail[]
builder.add_away_matches(arsenal_last_10_matches)
builder.add_h2h_matches(liverpool_vs_arsenal_history)

# Add API-Football market context
builder.add_market_context(odds=odds_data, predictions=predictions_data)

# Build the intelligence
intelligence = builder.build()

# Now you have:
# - intelligence.home_profile (tactical profile from history)
# - intelligence.away_profile
# - intelligence.home_form (xG trends, trajectory)
# - intelligence.away_form
# - intelligence.h2h (historical patterns)
# - intelligence.key_matchups (player battles)
# - intelligence.predicted_xG_home / away
# - intelligence.market_home_win_prob (from odds)
# - intelligence.model_vs_market_divergence (value detection!)
```
