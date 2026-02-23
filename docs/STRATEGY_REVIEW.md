# Clarity Engine - Strategy Review

**Date:** 2026-02-20  
**Goal:** Build AI that "knows ball" with 80%+ accuracy  
**Current Best:** 51.9% (gpt-4o-mini, full season)

---

## The Problem

We're trying to predict Premier League match outcomes (Home/Draw/Away) using AI + data. After a full day of iteration, our best result is **51.9%** — barely above break-even for betting (52.6%) and nowhere near the 80% target.

**Core confusion:** We've tried many approaches but don't have a clear understanding of what's actually helping vs hurting.

---

## Strategies Tested

### 1. CodedAgent (Python script with structured prompts)
**Location:** `src/agents/coded.py`  
**How it works:**
- Hardcoded tool calls in sequence
- Builds structured JSON context
- Sends to LLM with rigid prompt template
- Extracts prediction from response

**Results:** ~42% accuracy (R22-26 baseline)

**Pros:** Consistent, predictable  
**Cons:** Rigid, can't adapt investigation based on findings

---

### 2. OpenClawAgent (OpenClaw subagent with tools)
**Location:** `src/agents/openclaw.py`  
**How it works:**
- Spawns OpenClaw subagent via `sessions_spawn`
- Agent has access to KG tools
- Free-form investigation with SKILL.md guidance
- Returns analysis + prediction

**Results:** ~60% on R25 (6/10), ~53% combined R25-26

**Pros:** Can reason during investigation  
**Cons:** Expensive (Opus), slow, inconsistent output format

---

### 3. SkilledAgent (Direct Anthropic/OpenAI API with tools)
**Location:** `src/agents/skilled.py`  
**How it works:**
- Loads SKILL.md as system prompt
- Direct API call with function calling
- Agent calls tools as needed
- Extracts JSON prediction from response

**Results by model:**

| Model | R10-12 (30) | R22-24 (30) | R25 (10) | Full Season (260) |
|-------|-------------|-------------|----------|-------------------|
| gpt-4o-mini | 63% | 28% | 80% | **51.9%** |
| gpt-5-mini | 53% | 33% | 70% | — |
| gpt-5.2 | — | 30% | 60% | — |

**Pros:** Fast, cheap (4o-mini), good tool use  
**Cons:** Results vary wildly by round

---

### 4. Research + Analyst (Two-stage approach)
**Location:** `~/.openclaw/agents/research/` + `~/.openclaw/agents/analyst/`  
**How it works:**
1. Research agent searches web for pre-match intel (injuries, news, set pieces)
2. Saves to YAML file
3. Analyst agent reads research + KG data
4. Produces prediction

**Results:** R25: 5/8 confirmed = 63% (1 exact score)

**Pros:** Richer context (injuries, news)  
**Cons:** Complex, slow, 2 timeouts out of 10

---

## Data Sources

### Knowledge Graph (PostgreSQL)
- `team_states`: 8-layer team snapshots per round
- `matches`: Historical results with xG
- `players`: Performance stats
- `injuries`: Current injuries

**Tools available:**
- `get_team_state()` - Full team snapshot
- `get_team_form()` - Last N matches
- `get_h2h()` - Head-to-head history
- `get_key_players()` - Top performers
- `get_injuries_impact()` - Missing players
- `get_manager_info()` - Manager stats
- `get_psychological_state()` - Confidence/pressure

### Research (Web search)
- FotMob match previews
- News articles
- Injury updates
- Press conference quotes

---

## What We Observed

### Round variance is HUGE
- R25 with gpt-4o-mini: **80%** (8/10)
- R22-24 with gpt-4o-mini: **28%** (7/25)
- Full season: **51.9%** (135/260)

**This suggests:** Some rounds are "easy" (clear favorites win), others are chaos.

### Newer models ≠ better
- gpt-4o-mini consistently beats gpt-5-mini and gpt-5.2
- Possibly because simpler model follows structured SKILL.md better
- Or: reasoning models overthink pattern-matching tasks

### AI edge over baselines
- Always Home: 39.4%
- Always Away: 31.2%
- Random: 33.3%
- **AI (gpt-4o-mini): 51.9%**

AI adds ~12-18% over dumb strategies, but not enough for profitability.

---

## Key Questions

### 1. Is our data good enough?
- KG has stats but lacks: lineups, set piece data, game state narratives
- Research adds some context but is inconsistent
- **Question:** What data would actually move the needle?

### 2. Is the task even possible?
- Professional tipsters average 55-60%
- Betting markets are efficient
- **Question:** Is 80% realistic or fantasy?

### 3. Are we measuring correctly?
- We count H/D/A correctness
- But model might be good at identifying "safe" games
- **Question:** Should we filter to high-confidence only?

### 4. What types of games does the model get right?
- We haven't analyzed this
- **Question:** Is there a pattern (big favorites? relegation battles? derbies?)

### 5. Is the SKILL.md actually helping?
- We haven't tested with/without it
- **Question:** A/B test skill vs no skill?

---

## Execution Summary

```
┌─────────────────────────────────────────────────────────────┐
│                     How Each Strategy Runs                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  CodedAgent                                                  │
│  ───────────                                                 │
│  Python script → Fixed tool sequence → Build JSON → LLM     │
│  Run: python -m backtest.runner --methods coded              │
│                                                              │
│  SkilledAgent                                                │
│  ────────────                                                │
│  SKILL.md prompt → API w/ tools → Agent investigates → JSON │
│  Run: python -m backtest.runner --methods skilled --model X  │
│                                                              │
│  OpenClawAgent                                               │
│  ─────────────                                               │
│  sessions_spawn → Subagent w/ tools → Free investigation    │
│  Run: python -m backtest.runner --methods openclaw           │
│                                                              │
│  Research+Analyst                                            │
│  ────────────────                                            │
│  Manual: spawn research agent → save YAML → spawn analyst   │
│  No automated runner yet                                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Next Steps (Proposed)

1. **Analyze win/loss patterns** — Which games does AI get right?
2. **Filter high-confidence** — Only act on 70%+ confidence picks
3. **A/B test components** — SKILL vs no SKILL, with/without research
4. **Set realistic target** — Maybe 60% on filtered picks is achievable

---

## Files Reference

| File | Purpose |
|------|---------|
| `src/agents/coded.py` | CodedAgent implementation |
| `src/agents/skilled.py` | SkilledAgent (Anthropic/OpenAI) |
| `src/agents/openclaw.py` | OpenClawAgent (subagent) |
| `skills/match-intelligence/SKILL.md` | Analysis guidance |
| `backtest/runner.py` | Backtest orchestrator |
| `backtest/evaluator.py` | Result evaluation |
| `src/tools/*.py` | KG tool implementations |

