# Clarity Engine — Product Vision

## One-Liner
**Pre-match intelligence that tells you what's going to happen and why.**

---

## The Problem

Current football analytics (external APIs, Sofascore, etc.) show you **WHAT happened**:
- Possession: 58%
- Shots: 14
- xG: 1.82

But they don't tell you:
- **WHY** it happened
- **WHAT** will happen next
- **WHERE** the edges are

---

## The Solution

Clarity Engine is a **sports intelligence system** that:

1. **Predicts match dynamics** (not just results)
   - How will the game flow?
   - Where will danger come from?
   - What happens if Team A scores first?

2. **Tells a story** (not a data dump)
   - "Arsenal will dominate the left channel because Trent struggles vs pace"
   - Progressive disclosure: summary → details

3. **Validates and learns**
   - Track predictions vs reality
   - Score accuracy
   - Improve over time

4. **Is honest about uncertainty**
   - "We don't know X"
   - "This depends on lineup"
   - Confidence levels with evidence

---

## What We Sell

| Product | Channel | Description |
|---------|---------|-------------|
| **Clarity Web** | Webapp | Full intelligence, navigation, deep dives |
| **Clarity Telegram** | Bot | Formatted intelligence, alerts, on-demand |
| **Clarity API** | REST | Raw intelligence for devs/analysts |

---

## Example: Pre-Match Intelligence

```
Arsenal vs Liverpool • Saturday 17:30

━━━ THE STORY ━━━

Two high-pressing teams. Both want the ball.
Something has to give.

Arsenal have a clear tactical edge: Liverpool's right side 
is exposed. Trent's struggles vs pace are well-documented 
— and Martinelli is the fastest winger in the league.

But Liverpool are lethal on the break. If Arsenal 
overcommit, Salah punishes.

━━━ KEY QUESTION ━━━

Can Arsenal exploit the left channel?

EVIDENCE FOR:
• Trent: 41% duels won vs fast wingers (external APIs)
• Martinelli: 2.4 successful dribbles/90 (external APIs)
• Klopp addressed this in Friday presser (The Athletic)

EVIDENCE AGAINST:
• Liverpool may use Gravenberch to cover
• Last H2H: Liverpool adjusted, neutralized threat

OUR TAKE: Arsenal will try. 60% chance it works.
UNCERTAINTY: Lineup dependent. Watch for Gravenberch.

━━━ SCENARIOS ━━━

IF ARSENAL SCORES FIRST:
→ Liverpool forced to push up
→ Trent even more exposed
→ Counter-attack opportunities ↑↑

IF LIVERPOOL SCORES FIRST:
→ Mid-block activated
→ Arsenal struggles to break down
→ Game becomes frustrating

━━━ WHAT WE DON'T KNOW ━━━

• Saka fitness (trained Friday, but how sharp?)
• Liverpool's exact setup (4-3-3 or 4-2-3-1?)

We'll update after lineups drop.
```

---

## Key Principles

### 1. Story, Not Data Dump
A page answers: "What do I need to know about this match?"
Not 20 boxes of stats.

### 2. Pre-Match is Where the Value Is
Post-match is just validation. The money is made BEFORE the game.

### 3. Predict Dynamics, Not Just Results
- "Arsenal will dominate possession" ← validateable
- "Expect 2.5+ goals" ← validateable
- "Left channel will be key" ← validateable

More robust to variance. Reveals causality.

### 4. Numbers Aren't Enough
We need:
- Stats (external APIs, API-Football)
- Context (news, injuries, motivation)
- Expert analysis (The Athletic, Tifo, podcasts)
- Historical patterns

### 5. Honest About Uncertainty
Don't fake confidence. Say:
- "Based on 847 data points"
- "We don't know X"
- "This depends on Y"

### 6. Learn and Improve
Every prediction is tracked. Every validation teaches us.
The system gets better over time.

---

## Target Users

### Tier 1: Serious Bettors
- Want edges, not entertainment
- Value accuracy and validation
- Will pay for proven intelligence

### Tier 2: Football Enthusiasts
- Love tactical depth
- Want to understand the game better
- Will pay for insight

### Tier 3: Analysts / Scouts
- Need data and tools
- Custom queries
- API access

---

## Differentiation

| Aspect | external APIs/Sofascore | Clarity |
|--------|------------------|---------|
| Focus | What happened | What will happen |
| Format | Data tables | Narrative |
| Depth | Surface stats | Tactical analysis |
| Context | None | News + expert opinions |
| Validation | None | Track record shown |
| Learning | Static | Improves over time |

---

## Success Metrics

1. **Prediction Accuracy**
   - % of "takes" validated correctly
   - Calibration (50% confidence = 50% correct)

2. **User Value**
   - Retention
   - Upgrade rate
   - NPS

3. **Coverage**
   - Leagues covered
   - Matches analyzed
   - Sources integrated

---

## Non-Goals (For Now)

- Live match coverage (focus on pre-match)
- Fantasy football optimization
- Transfer rumor aggregation
- Social features

---

*Last updated: 2026-02-15*
