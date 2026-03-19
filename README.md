# Clarity Engine ⚽🧠

**Sports intelligence system that separates *what will happen* from *where the value is*.**

Clarity Engine generates pre-match football analysis by combining two distinct layers:

- **Match Intelligence** — How the game unfolds (tactical, narrative)
- **Market Intelligence** — Where the edge is (odds, value, mispricing)

Most tools confuse these. We don't.

---

## The Two Layers

### 🎯 Match Intelligence
*"Read the game like a scout"*

Investigates the tactical reality:
- Team form, style, trajectory
- Matchup dynamics
- Key players & absences
- How the game will flow

Output: Scout-style briefing with verdict, risks, and score shape.

> *"Arsenal's 0.84 xGA profile shields them from Everton's low-volume transition game. Saka's inside-left runs vs their narrow 4-4-2 create the overload. Home win via set-piece dominance, but draw gravity caps ceiling."*

---

### 📊 Market Intelligence
*"Find the edge, not the winner"*

Analyzes the betting market:
- Probability calibration (model vs odds)
- Value detection (expected value calculations)
- Market mispricing signals
- Risk-adjusted recommendations

Output: PICK / LEAN / WATCHLIST / NO_BET with confidence and EV.

> *"Model: 62% home win. Market: 55% implied. Edge: +7pp. EV: +12.7%. → LEAN (moderate confidence, data gaps on away defense)."*

---

## Why Separate?

| Trap | What happens |
|------|--------------|
| Mixing narrative with odds | "They'll win because they need to" — vibes, not edge |
| Pure stats, no context | Miss tactical dynamics that move probabilities |
| Chasing winners | Betting on likely outcomes at bad prices |

Clarity Engine keeps them separate, then combines them for decisions.

---

## Architecture

| Layer | What it does |
|-------|--------------|
| **Data** | FotMob + API-Football ingestion, PostgreSQL |
| **Knowledge Graph** | 8-layer team states (form, style, attack, defense...) |
| **Tools** | 17 agent tools for match investigation |
| **Match Intelligence** | LLM reasoning with tactical rubric |
| **Market Intelligence** | Probabilistic model + odds analysis |
| **Decision Engine** | Combines both → actionable output |

---

## Tech Stack

- **Python 3.12** — core runtime
- **PostgreSQL** — match data + knowledge graph
- **OpenAI / Anthropic** — LLM reasoning (configurable)
- **XGBoost** — probability calibration
- **FotMob + API-Football** — data sources

---

## Quick Start

```bash
cd clarity_engine
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your API keys

# Generate analysis for a match
python scripts/generate_match_analysis.py --match "Arsenal vs Everton"
```

---

## Status

🟢 **Match Intelligence** — Live, generating daily PL analysis  
🟡 **Market Intelligence** — Calibrated model, integration WIP  
🔧 **Delivery** — Telegram bot in progress

---

## Philosophy

> *"We don't predict winners. We find mispriced outcomes."*

The goal isn't to guess who wins — it's to identify when the market is wrong, and by how much.

---

*Built by [@sh0ck-zy](https://github.com/sh0ck-zy)*
