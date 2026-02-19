# Backtest Final Analysis

## Overview

**Period**: Premier League Rounds 25 + 26 (20 games)  
**Date**: February 2026  
**Methods Compared**:
- **Coded Agent**: Fixed sequence of tool calls → single LLM analysis
- **OpenClaw Agent**: Autonomous investigation with tool calling

---

## Results Summary

| Metric | Coded Agent | OpenClaw Agent | Winner |
|--------|-------------|----------------|--------|
| **Accuracy** | 35% (7/20) | 50% (10/20) | 🏆 OpenClaw |
| **Quality Score** | 5.9/10 | 7.2/10 | 🏆 OpenClaw |
| **Exact Scorelines** | 1/20 | 5/20 | 🏆 OpenClaw |
| **Avg Time** | 16.2s | 14.5s | 🏆 OpenClaw |
| **Avg Tokens** | 5,610 | 7,259 | 🏆 Coded |

---

## Critical Finding: Home Bias

The Coded Agent has a severe home bias problem:

| Round | Coded Predictions | OpenClaw Predictions |
|-------|-------------------|----------------------|
| 25 | 8H / 0D / 2A | 4H / 2D / 4A |
| 26 | **10H / 0D / 0A** | 6H / 2D / 2A |

The Coded agent predicted Home Win for **100% of Round 26 matches**!

This happens because:
1. The prompt emphasizes "home advantage" and "desperation"
2. Fixed data gathering doesn't adapt to context
3. No reasoning during investigation to question assumptions

---

## Quality Analysis (LLM Judge)

### Burnley 0-2 West Ham (Round 25)

**Coded Analysis** (5.2/10):
- Predicted: Burnley 2-0 win
- "Burnley's desperation will drive them to control"
- Missed: West Ham's clinical finishing, H2H dominance

**OpenClaw Analysis** (7.0/10):
- Predicted: West Ham 1-2 win ✅
- "West Ham has better attacking capabilities"
- Correctly identified: West Ham's quality over Burnley's desperation

### Brentford 1-1 Arsenal (Round 26)

**Coded Analysis** (7.0/10):
- Predicted: Brentford 2-0 win
- "Arsenal will collapse under pressure"
- Wrong read: Arsenal didn't collapse

**OpenClaw Analysis** (7.25/10):
- Predicted: 1-1 Draw ✅ **EXACT SCORELINE**
- "Match promises to be closely contested"
- Correct read: Neither team had clear edge

### Tottenham 1-2 Newcastle (Round 26)

**Coded Analysis** (5.5/10):
- Predicted: Tottenham home win
- Standard "home advantage" narrative

**OpenClaw Analysis** (7.25/10):
- Predicted: Newcastle away win ✅
- Recognized Newcastle's form and quality

---

## Why OpenClaw Wins

### 1. Adaptive Investigation
OpenClaw decides what to investigate based on findings:
- If it sees a new manager → investigates more
- If H2H shows clear pattern → weighs it appropriately
- Doesn't waste tokens on irrelevant data

### 2. Reasoning During Investigation
The agent thinks between tool calls:
- "Interesting, Arsenal's xG is declining..."
- "This H2H record is unusual, let me check why..."
- Leads to better understanding of context

### 3. Balanced Predictions
OpenClaw predicts draws and away wins when appropriate.
Coded defaults to home wins due to prompt bias.

---

## Cost vs Value

| Metric | Coded | OpenClaw | Delta |
|--------|-------|----------|-------|
| Tokens | 5,610 | 7,259 | +29% |
| Accuracy | 35% | 50% | +43% |
| Quality | 5.9 | 7.2 | +22% |

**Value calculation**: 29% more tokens → 43% better accuracy

This is a good trade-off for a premium product.

---

## Recommendations

1. **Use OpenClaw for production** - Better accuracy and quality justify the token cost

2. **Fix Coded Agent home bias** - If cost is critical:
   - Add explicit "consider away win" logic
   - Balance the prompt
   - Add reasoning step before final prediction

3. **Quality evaluation is essential** - Accuracy alone doesn't tell the full story. A good analysis with wrong prediction > lucky guess

4. **Time lock verified** - Both methods correctly use `round_number - 1` for data queries. No data leakage detected.

---

## Conclusion

> **"O raciocínio durante a investigação produz reports melhores do que receber todos os dados de uma vez?"**

**Yes.** The OpenClaw agent's ability to reason during investigation produces:
- 43% better accuracy
- 22% better quality scores
- More balanced, thoughtful predictions

The extra 29% token cost is justified by significantly better match intelligence.

---

*Generated: 2026-02-19*
