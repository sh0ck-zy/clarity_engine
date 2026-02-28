# Bot Integration — Clarity Engine ↔ Oddly Bot

## Overview

This document maps how to integrate `clarity_engine` (producer) with `clarity-odds-core/telegram_bot` (consumer).

---

## Source Code Audit

### clarity-odds-core/telegram_bot/

| File | Purpose | Reuse? |
|------|---------|--------|
| `main.py` | Bot entry point, registers handlers | ✅ Reuse as-is |
| `oddly_bot.py` | Bot class (25KB) | ⚠️ May need refactor |
| `app_setup.py` | Application setup | ✅ Reuse |
| `team_config.py` | Team name mappings | ✅ Reuse |
| `api_client.py` | API client wrapper | ❌ Not needed |
| `match_formatter.py` | Match card formatting (25KB) | ⚠️ Partially reuse |

### telegram_bot/handlers/

| File | Purpose | Reuse? |
|------|---------|--------|
| `commands_v0.py` | /start, /help, /jogo | ✅ Reuse, add /round |
| `callbacks_v0.py` | Inline button handlers | ✅ Reuse, add round callbacks |
| `menu_handler.py` | Menu navigation | ✅ Reuse |
| `matches_handler.py` | Match listing | ⚠️ Replace with engine output |
| `domain_commands.py` | Domain-specific commands | ✅ Reuse |

### telegram_bot/formatters/

| File | Purpose | Reuse? |
|------|---------|--------|
| `final_llm_formatter.py` | **GOLD** - LLM output formatting | ✅ Adapt for engine |
| `match_card_formatter.py` | Match card layout | ✅ Reuse |
| `messages.py` | Message templates | ✅ Reuse |

### database/repositories/

| File | Purpose | Reuse? |
|------|---------|--------|
| `analysis_cache_repository.py` | Cache AI analyses | ⚠️ Replace with engine output |

---

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     CURRENT (clarity-odds-core)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   User ──▶ Bot ──▶ DB Query ──▶ LLM Generate ──▶ Format ──▶ Send│
│                                                                 │
│   Problems:                                                     │
│   - Generates on-demand (slow)                                  │
│   - No human approval                                           │
│   - Uses clarity_odds_db (empty)                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     TARGET (integrated)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Engine (pre-generates) ──▶ Human Approves ──▶ Bot Reads ──▶ Send│
│                                                                 │
│   Benefits:                                                     │
│   - Pre-generated, instant response                            │
│   - Human-approved quality                                      │
│   - Uses clarity_football (has data)                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Changes Required

### 1. Bot reads from engine output (not DB)

**Current flow:**
```python
# callbacks_v0.py
cache_repo = AnalysisCacheRepository(db_config)
analysis = cache_repo.get_analysis(fixture_id, f"ai_v0_{lang}")
```

**New flow:**
```python
# New: engine_reader.py
from clarity_engine.output import RoundReader

reader = RoundReader("output/rounds/PL_R28")
analysis = reader.get_match_analysis("Leeds_vs_Man_City")
```

### 2. Add round-based commands

**New commands:**
- `/round 28` — Show all R28 analyses
- `/round 28 Leeds` — Show specific match
- `/latest` — Latest published round

**Implementation:**
```python
# handlers/round_handler.py

async def cmd_round(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /round <num> command"""
    round_num = int(context.args[0]) if context.args else None
    
    if not round_num:
        # Show latest round
        rounds = get_published_rounds()
        round_num = rounds[-1] if rounds else 28
    
    # Read from engine output
    reader = RoundReader(f"output/rounds/PL_R{round_num}")
    
    if not reader.is_published():
        await update.message.reply_text("⏳ Round not yet published")
        return
    
    # Show round overview
    message = reader.format_round_overview()
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
```

### 3. Adapt formatter for engine output

**Engine output format:**
```json
// output/rounds/PL_R28/matches/Leeds_vs_Man_City/report.json
{
  "summary": {
    "headline": "...",
    "overview": "..."
  },
  "analysis": {
    "prediction_rationale": "...",
    "key_factors": [...],
    "risks": [...]
  },
  "probabilities": {
    "home_win": 0.137,
    "draw": 0.293,
    "away_win": 0.570
  }
}
```

**Formatter adaptation:**
```python
# formatters/engine_formatter.py

def format_engine_analysis(match_dir: Path, lang: str = "en") -> str:
    """Format engine output for Telegram"""
    
    report = json.load(open(match_dir / "report.json"))
    facts = json.load(open(match_dir / "facts.json"))
    draft = (match_dir / "drafts" / "telegram.txt").read_text()
    
    # Use existing draft if quality is good
    quality = json.load(open(match_dir / "quality_checks.json"))
    if quality["mis_score"] >= 70:
        return draft
    
    # Fallback: format from report
    return format_from_report(report, facts, lang)
```

---

## File Changes Summary

### clarity-odds-core (bot)

| File | Action | Changes |
|------|--------|---------|
| `config/config.py` | Modify | Add `ENGINE_OUTPUT_PATH` |
| `telegram_bot/main.py` | Modify | Register round handlers |
| `handlers/round_handler.py` | **Create** | /round, /latest commands |
| `handlers/callbacks_v0.py` | Modify | Add round callbacks |
| `formatters/engine_formatter.py` | **Create** | Format engine output |
| `utils/engine_reader.py` | **Create** | Read engine output |

### clarity_engine

| File | Action | Changes |
|------|--------|---------|
| `scripts/publish_round.py` | Create | Trigger bot publish |
| `src/pipeline/bot_exporter.py` | Create | Export for bot consumption |

---

## Shared Output Contract

Both systems must agree on output format:

```
output/rounds/PL_R28/
├── round_status.json          # Bot checks this
│   {
│     "status": "published",   # draft | approved | published
│     "published_at": "2026-02-28T17:00:00Z",
│     "matches_count": 10
│   }
│
├── matches/
│   └── Leeds_vs_Man_City/
│       ├── report.json        # Full analysis
│       ├── facts.json         # Raw facts
│       ├── quality_checks.json
│       └── drafts/
│           ├── telegram.txt   # Ready to send
│           └── x.txt
```

**Bot reads:**
1. `round_status.json` — Check if published
2. `drafts/telegram.txt` — Pre-formatted message
3. `quality_checks.json` — MIS score for display

---

## Migration Path

### Phase 1: Parallel Operation
- Engine generates to `output/rounds/`
- Bot still uses old DB queries
- Manual copy-paste for testing

### Phase 2: Bot Integration
- Add `engine_reader.py` to bot
- Add `/round` command
- Test with R28

### Phase 3: Full Migration
- Remove old DB queries
- All analyses come from engine
- Rebrand: Oddly → Clarity

---

## Reusable Code Map

### From clarity-odds-core → clarity_engine

| Code | From | To | Purpose |
|------|------|-----|---------|
| `final_llm_formatter.py` | bot/formatters | engine/renderers | Telegram formatting |
| `team_config.py` | bot | engine/data | Team name mappings |
| Message templates | bot/formatters/messages.py | engine/renderers | i18n strings |

### From clarity_engine → clarity-odds-core

| Code | From | To | Purpose |
|------|------|-----|---------|
| Round output format | engine/output | bot/utils | Shared contract |
| Quality checks | engine/pipeline | bot/display | MIS score display |

---

## Quick Start

### Test bot locally:
```bash
cd ~/Projects/clarity-odds-core
source venv/bin/activate
python telegram_bot/main.py
```

### Test engine output reading:
```python
# In bot codebase
import sys
sys.path.insert(0, '/Users/joao/Projects/clarity_engine')

from pathlib import Path
import json

round_dir = Path("/Users/joao/Projects/clarity_engine/output/rounds/PL_R28")
status = json.load(open(round_dir / "round_status.json"))
print(f"Round status: {status['status']}")
```

---

*Created: 2026-02-28*
