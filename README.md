# Clarity Engine

Sports intelligence system that generates pre-match football analysis using AI agents and a knowledge graph.

## Structure

```
clarity_engine/
├── src/
│   ├── tools/          # 17 agent tools (V3)
│   ├── database/       # DB connection & schema
│   └── data/           # Data fetchers & scrapers
├── scripts/            # Population & backfill scripts
├── docs/               # Documentation
├── tests/              # Test suite
├── output/             # Generated analyses
├── archive/            # Legacy code (kept for reference)
├── TASK.md             # Current sprint
└── STATUS.md           # Quick status
```

## Tools (17 total)

| Category | Tools |
|----------|-------|
| **Team** | `get_team_state`, `get_team_form`, `get_team_profile`, `get_formation_history` |
| **Manager** | `get_manager_info` |
| **Player** | `get_key_players`, `get_injuries_impact` |
| **Match** | `get_last_match_summary`, `get_h2h`, `get_matchup_analysis` |
| **Context** | `get_psychological_state`, `search_news`, `search_press_conference`, `get_odds`, `build_game_state_tree` |
| **Helpers** | `odds_to_probability`, `calculate_value` |

## Quick Start

```bash
cd ~/Projects/clarity_engine
source venv/bin/activate

# Test tools
python -c "from src.tools import get_team_state; print(get_team_state('Arsenal').summary)"

# Test alias resolution
python -c "from src.tools import resolve_team; print(resolve_team('spurs'))"  # → 8586
```

## Data

- **Database:** PostgreSQL `clarity_football`
- **Primary source:** FotMob (matches, players, stats)
- **KG tables:** `team_states`, `player_states`, `manager_history`

## Next Steps

1. Implement agent loop
2. Backtest system
3. Launch Clarity Sports

---

*Last updated: 2026-02-19*
