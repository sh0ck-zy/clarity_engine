# Results Summary

## All Test Results (2026-02-19/20)

### Full Season Test (260 games, R1-26)
| Model | Accuracy | Time/Game | Notes |
|-------|----------|-----------|-------|
| gpt-4o-mini | **51.9% (135/260)** | 13.8s | Best overall |

### Round-Specific Tests

#### R25 (10 games) — Our "best" round
| Model | Accuracy | Exact Scores |
|-------|----------|--------------|
| gpt-4o-mini | **80% (8/10)** | 2 |
| gpt-5-mini | 70% (7/10) | — |
| gpt-5.2 | 60% (6/10) | — |
| Research+Analyst (Opus) | 63% (5/8)* | 1 |
| OpenClaw Analyst (Sonnet) | 60% (6/10) | 3 |

*2 predictions lost in queue

#### R22-24 (30 games)
| Model | Accuracy |
|-------|----------|
| gpt-4o-mini | 28% (7/25)* |
| gpt-5-mini | 33% (10/30) |
| gpt-5.2 | 30% (9/30) |

*Only 25 matched in evaluation

#### R10-12 (30 games)
| Model | Accuracy |
|-------|----------|
| gpt-4o-mini | **63% (19/30)** |
| gpt-5-mini | 53% (16/30) |

### Baselines (R10-26, 170 games)
| Strategy | Accuracy |
|----------|----------|
| Always Home | 39.4% |
| Always Away | 31.2% |
| Always Draw | 29.4% |
| Random (33.3%) | 33.3% |

---

## The Math Problem

**For betting profitability at 1.90 odds:**
- Break-even: 52.6%
- Our best (full season): 51.9%
- **Gap: -0.7%** (losing money)

**For 80% target:**
- Current: 51.9%
- **Gap: -28.1%** (massive)

---

## Variance Problem

Same model (gpt-4o-mini), wildly different results:

| Round Set | Accuracy |
|-----------|----------|
| R25 | 80% |
| R10-12 | 63% |
| Full season | 52% |
| R22-24 | 28% |

**This is the core issue.** Results are not stable.

---

## Cost Analysis

| Model | Cost/Game | Full Season Cost |
|-------|-----------|------------------|
| gpt-4o-mini | ~$0.001 | ~$0.26 |
| gpt-5-mini | ~$0.01 | ~$2.60 |
| gpt-5.2 | ~$0.05 | ~$13.00 |
| claude-opus | ~$0.15 | ~$39.00 |

gpt-4o-mini is 10-150x cheaper AND performs best.
