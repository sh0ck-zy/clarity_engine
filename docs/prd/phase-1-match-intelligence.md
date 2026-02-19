# Phase 1 PRD: Match Intelligence (Beat ChatGPT)

## Status: DATA LAYER COMPLETE

Last updated: 2026-01-24

---

## Goals
- Deliver match narratives that consistently outperform generic ChatGPT previews.
- Build trust by explaining the match clearly, honestly, and with repeatable structure.
- Establish a validation loop that scores narrative alignment post-match.

## Scope
- Structured match context builder (deterministic facts layer).
- Narrative generation using a strict schema (LLM output).
- Post-match alignment evaluation and reporting.
- Dashboard views for narrative quality and outcome accuracy.

---

## Success Metrics
- Narrative alignment score >= target threshold (to be set).
- Outcome accuracy (W/D/L) improvement vs baseline prompt.
- Coverage: % of matches with full context data.
- Time to produce a full report (batch reliability).

---

## Deliverables

### Data Layer (COMPLETE)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Context Builder v1 | COMPLETE | `src/analysis/context_builder_v2.py` |
| Injuries data | COMPLETE | 3,337 records via Transfermarkt |
| Lineups data | COMPLETE | 358/380 fixtures (94%) |
| Odds data | COMPLETE | 220/380 fixtures with opening+closing odds |
| TM Match Mappings | COMPLETE | 358/380 fixtures mapped |
| Context Schema | COMPLETE | `src/analysis/context_schema.py` |

### Narrative Layer (IN PROGRESS)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Narrative Schema v1 | PARTIAL | `src/analysis/narrative_schema.py` exists |
| Evaluator v1 | PARTIAL | `src/analysis/evaluator.py` exists |
| Post-match alignment | TODO | Needs implementation |

### Dashboard (IN PROGRESS)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Dashboard v3 | PARTIAL | `src/dashboard_v3.py` exists |
| Narrative quality trend | TODO | |
| Best/worst analyses | TODO | |

---

## Task Breakdown (Updated)

| ID | Task | Status |
|----|------|--------|
| P1-001 | Define match context schema and required fields | DONE |
| P1-002 | Inventory and validate data sources | DONE |
| P1-003 | Implement deterministic context builder | DONE |
| P1-004 | Add data coverage diagnostics | DONE |
| P1-005 | Create strict narrative schema and prompt | PARTIAL |
| P1-006 | Add schema validation for narratives | TODO |
| P1-007 | Post-match narrative alignment evaluator | PARTIAL |
| P1-008 | Add time-travel safety checks for context | DONE |
| P1-009 | Phase 1 dashboard views | PARTIAL |
| P1-010 | Batch + iteration loop | TODO |
| P1-011 | Add baseline comparisons | TODO |
| P1-012 | Add regression alerts | DONE |

### New Tasks Added

| ID | Task | Status |
|----|------|--------|
| P1-013 | Transfermarkt injury scraper | DONE |
| P1-014 | Transfermarkt lineup scraper | DONE |
| P1-015 | TM match ID mapping system | DONE |
| P1-016 | Football-data.co.uk odds import | DONE |
| P1-017 | Context builder v2 with all data sources | DONE |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     DATA LAYER (COMPLETE)                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   FBRef      │  │ Transfermarkt│  │ Football-Data│      │
│  │  (fixtures)  │  │  (injuries,  │  │   (odds)     │      │
│  │              │  │   lineups)   │  │              │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│         ▼                 ▼                 ▼               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              PostgreSQL Database                     │   │
│  │  fixtures | lineups_historical | odds_snapshots     │   │
│  │  player_injuries_historical | tm_match_mapping      │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                               │
│                            ▼                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Context Builder v2                         │   │
│  │  src/analysis/context_builder_v2.py                 │   │
│  │  - Team identity (Elo, form)                        │   │
│  │  - Injuries/absences                                │   │
│  │  - Confirmed lineups                                │   │
│  │  - Pre-match odds                                   │   │
│  └─────────────────────────┬───────────────────────────┘   │
│                            │                               │
└────────────────────────────┼───────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   NARRATIVE LAYER (TODO)                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Narrative Generator                        │   │
│  │  - Uses context as grounding                        │   │
│  │  - Strict schema output                             │   │
│  │  - Claims linked to facts                           │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Sources Summary

| Source | Data | Coverage | File |
|--------|------|----------|------|
| FBRef | Fixtures, xG | 100% | `src/ingestion/scraper.py` |
| Transfermarkt | Injuries | 3,337 records | `src/ingestion/transfermarkt_injuries.py` |
| Transfermarkt | Lineups | 94% | `src/ingestion/transfermarkt_lineups.py` |
| Football-Data | Odds | 58%* | `scripts/download_odds_historical.py` |
| ClubElo | Ratings | 100% | `src/ingestion/elo_backfill.py` |
| Understat | PPDA, Field Tilt | 100% | `src/ingestion/understat_enrich.py` |

*58% = all played matches; remaining are future fixtures

---

## Risks (Updated)

| Risk | Status | Mitigation |
|------|--------|------------|
| Data gaps (injuries/lineups) | RESOLVED | Transfermarkt scrapers |
| Odds data missing | RESOLVED | Football-data.co.uk import |
| LLM hallucination | MITIGATED | Context grounding with real data |
| Evaluation rubric misalignment | OPEN | Needs calibration |
| Transfermarkt rate limiting | MITIGATED | 2-2.5s delays |

---

## Dependencies (Updated)

| Dependency | Status |
|------------|--------|
| Reliable data sources for form, xG | DONE |
| Injuries data | DONE |
| Lineups data | DONE |
| Fixture database completeness | DONE |
| Evaluation prompt and storage | PARTIAL |

---

## Next Steps

1. **Evaluator improvements** - Update narrative generation to use real data
2. **Confidence layer** - Calibrate claims against market odds
3. **Dashboard updates** - Surface injuries/lineups/odds in UI
4. **Batch validation** - Run full season evaluation

---

## Timeline (Revised)

- Week 1: ~~finalize data sources + context schema~~ DONE
- Week 2: ~~implement context builder + narrative schema~~ DONE (context), PARTIAL (narrative)
- Week 3: Update evaluator with real data, run batch
- Week 4: Dashboard iteration + calibration
