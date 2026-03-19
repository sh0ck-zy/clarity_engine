# Clarity Engine ⚽🧠

**Football intelligence that actually knows ball.**

Not another stats dashboard. Not vibes-based predictions. This is a **knowledge engine** — AI agents that investigate matches, build structured intelligence, and reason about the game like someone who actually watches football.

---

## The Problem

Most "football AI" is one of two things:

| Type | What it does | Why it fails |
|------|--------------|--------------|
| **Stats dumps** | "Arsenal have 1.87 xG/game" | Numbers without narrative. No insight. |
| **Vibes** | "Big game energy, they'll turn up" | No grounding. Just noise. |

Neither actually understands football.

---

## What Clarity Engine Does

### 1. Builds a Knowledge Graph

Every team has an **8-layer state profile** that evolves each round:

```
Identity → Position → Form → Style → Attack → Defense → Home/Away → Trajectory
```

This isn't just stats. It's structured knowledge about *how teams play*.

### 2. Investigates with AI Agents

Agents use **17 specialized tools** to investigate matches:

| Tool | What it reveals |
|------|-----------------|
| `get_team_state` | Full 8-layer snapshot |
| `get_team_form` | Recent results + xG context |
| `get_matchup_analysis` | How these teams match up |
| `get_key_players` | Who's in form, who matters |
| `get_injuries_impact` | Who's missing, how much it hurts |
| `get_h2h` | History, patterns, venue effects |
| `get_manager_info` | Tactical tendencies, tenure |
| `build_game_state_tree` | How the match could unfold |

The agent decides what to investigate. No rigid pipelines.

### 3. Reasons About the Game

Raw data goes in. Structured intelligence comes out:

```json
{
  "verdict": "Arsenal via set-piece dominance and Saka-side overloads",
  "core_read": "Everton's narrow 4-4-2 leaves half-spaces exposed...",
  "main_risk": "Draw gravity — both teams' last 5 average 2.1 goals",
  "kill_switch": "Early Everton goal flips the script entirely"
}
```

This isn't template-filling. It's **reasoning** — the AI investigates, weighs evidence, and reaches conclusions.

---

## "Knows Ball"

What does that actually mean?

| Knows Ball | Doesn't Know Ball |
|------------|-------------------|
| "Their 4-4-2 block leaves half-spaces exposed to inside-forward runs" | "They have a strong defense" |
| "Form string LLWWW shows momentum building after tactical shift" | "They're in good form" |
| "xG underperformance (0.72 ratio) suggests regression coming" | "They've been unlucky" |
| "This matchup favors the counter — space behind the high line" | "Should be a good game" |

The system generates the left column, not the right.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLARITY ENGINE                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   DATA      │───▶│  KNOWLEDGE  │───▶│    AI       │     │
│  │   LAYER     │    │    GRAPH    │    │   AGENTS    │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│        │                   │                  │             │
│   external APIs, APIs       8-layer team       17 tools +         │
│   Match data         state profiles      reasoning         │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                      OUTPUT                                 │
│   Structured match intelligence • Telegram delivery         │
└─────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Runtime** | Python 3.12 |
| **Knowledge Store** | PostgreSQL |
| **AI Reasoning** | OpenAI / Anthropic (swappable) |
| **Agent Framework** | Custom tools + LLM orchestration |
| **Delivery** | Telegram Bot |

---

## Project Structure

```
clarity_engine/
├── src/
│   ├── tools/           # 17 agent tools
│   ├── intelligence/    # Reasoning engine
│   ├── data/            # Data ingestion
│   └── models/          # Data models
├── skills/              # Agent skill definitions
├── scripts/             # Automation
└── docs/                # Documentation
```

---

## Quick Start

```bash
# Setup
git clone https://github.com/sh0ck-zy/clarity_engine.git
cd clarity_engine
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env  # Add API keys

# Run analysis
python scripts/generate_match_analysis.py --fixture "Arsenal vs Everton"
```

---

## Status

| Component | Status |
|-----------|--------|
| Knowledge Graph | 🟢 Live |
| Agent Tools | 🟢 17 operational |
| Match Intelligence | 🟢 Generating daily |
| Telegram Delivery | 🟡 Integration WIP |

---

## Philosophy

> **Data without context is noise. Context without structure is vibes. Structure without reasoning is a spreadsheet.**

Clarity Engine combines all three: structured football knowledge + AI reasoning = intelligence that actually knows ball.

---

*Built by [@sh0ck-zy](https://github.com/sh0ck-zy)*
