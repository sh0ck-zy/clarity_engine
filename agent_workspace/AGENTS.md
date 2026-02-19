# AGENTS.md — Clarity Engine

## What Is This Project?

Clarity Engine is a **sports intelligence system** that generates pre-match analysis for football matches. Unlike FotMob or Sofascore that show stats, Clarity tells you **what's going to happen and why**.

## Project Status

**Phase:** 1 Complete ✅
**Current Sprint:** Agent Reasoning Loop

---

## Key Documentation

Read these in order:

1. **`docs/VISION.md`** — What we're building and why
2. **`docs/ONTOLOGY.md`** — Knowledge graph structure
3. **`docs/TOOLS.md`** — 12 MVP agent tools (NEW)
4. **`docs/ROADMAP.md`** — Phases and tasks
5. **`docs/GAPS.md`** — Unsolved problems and challenges

---

## What We Have

### Knowledge Graph ✅
- **team_states:** 520 rows (20 teams × 26 rounds)
  - 8 layers: Identity, Position, Form, Style, Attack, Defense, Home/Away, Trajectory
- **player_states:** 14,331 rows
  - Goals, assists, xG, xA, ratings, form per player per round

### Data Sources
- **FotMob (Primary):** 260 PL matches (R1-R26)
  - `fotmob_matches` — match info, stats, shotmaps, momentum
  - `fotmob_player_performances` — player stats per match
- **API-Football (Secondary):** Odds, standings (pending integration)
- **News Aggregator:** In BetHub (pending integration)

### Agent Tools ✅ (`src/tools/`)

| Tool | Status |
|------|--------|
| `get_team_state` | ✅ Working |
| `get_team_form` | ✅ Working |
| `get_team_profile` | ✅ Working |
| `get_key_players` | ✅ Working |
| `get_injuries_impact` | ✅ Working |
| `get_last_match_summary` | ✅ Working |
| `get_h2h` | ✅ Working |
| `get_matchup_analysis` | ✅ Working |
| `get_psychological_state` | ✅ Working |
| `search_news` | ⚠️ Placeholder |
| `get_odds` | ⚠️ Placeholder |
| `build_game_state_tree` | ✅ Working |

### Related Projects
- **BetHub webapp:** `~/Projects/bethub/webapp/` (Next.js, paused)
- **clarity-odds-core:** `~/Projects/clarity-odds-core/` (API-Football fetchers)

---

## Next Steps (Phase 2)

1. Build agent reasoning loop
2. Connect news aggregator
3. Connect API-Football for odds
4. Multi-league support

See `TASK.md` for current sprint details.

---

## Critical Constraints

1. **Pre-match is the value** — Post-match is just validation
2. **Story, not data dump** — Intelligence must tell a story
3. **Be honest about uncertainty** — Don't fake confidence
4. **Numbers aren't enough** — Need context from news/articles
5. **Validate and learn** — Track predictions vs reality

---

## Technical Decisions Made

| Decision | Choice | Reason |
|----------|--------|--------|
| Database | PostgreSQL | Already using, JSONB flexibility |
| LLM | Claude (via OpenClaw) | Quality, context window |
| Agent tools | Python functions | Keep simple, use directly |
| Data primary | FotMob | Rich tactical data |

---

## File Structure

```
clarity_engine/
├── docs/
│   ├── VISION.md
│   ├── ONTOLOGY.md
│   ├── TOOLS.md           # NEW: Agent tools documentation
│   ├── ROADMAP.md
│   └── GAPS.md
│
├── src/
│   ├── tools/             # NEW: Agent tools
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── team_tools.py
│   │   ├── player_tools.py
│   │   ├── match_tools.py
│   │   └── context_tools.py
│   │
│   ├── database/
│   │   ├── config.py
│   │   └── schema.sql
│   │
│   ├── models/            # Pydantic schemas
│   │   ├── temporal_kg.py
│   │   └── intelligence.py
│   │
│   └── data/providers/
│       └── fotmob.py
│
├── scripts/
│   ├── 001_create_kg_tables.sql
│   ├── populate_kg_states.py
│   ├── populate_player_states.py
│   └── backfill_fotmob.py
│
└── tests/
```

---

## Commands

```bash
# Activate venv
source venv/bin/activate

# Test tools
python -c "from src.tools import get_team_state; print(get_team_state('Arsenal').summary)"

# Connect to DB
psql -d clarity_football
```

---

## Database Tables

| Table | Rows | Description |
|-------|------|-------------|
| `team_states` | 520 | Team KG snapshots per round |
| `player_states` | 14,331 | Player snapshots per round |
| `teams` | 20 | Team entities |
| `players` | 640 | Player entities |
| `fotmob_matches` | 260 | Raw match data |
| `fotmob_player_performances` | 10,393 | Player match stats |

---

*Last updated: 2026-02-17*
