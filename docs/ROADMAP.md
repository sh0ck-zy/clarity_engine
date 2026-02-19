# Clarity Engine — Roadmap

## Current State

```
✅ DONE                              ❌ TODO
────────────────────────────────     ────────────────────────────────
FotMob raw data (260 matches)        Normalized schema
Player performances                  Knowledge Base tables
Shotmaps, momentum                   Agents (all 5)
Pydantic models (schemas)            News integration
Database config                      Webapp connection
News aggregator (in BetHub)          Validation loop
BetHub webapp structure              Telegram delivery
```

---

## Phase 0: Foundation [Week 1]

### 0.1 Schema Design
| Task | Description | Output |
|------|-------------|--------|
| 0.1.1 | Design normalized entity tables | `schema_v2.sql` |
| 0.1.2 | Design Knowledge Base tables | `knowledge_base.sql` |
| 0.1.3 | Create migration from current to new | `migrations/001_normalize.sql` |
| 0.1.4 | Document schema | `docs/SCHEMA.md` |

### 0.2 ETL Framework
| Task | Description | Output |
|------|-------------|--------|
| 0.2.1 | Create `SourceProvider` base class | `src/sources/base.py` |
| 0.2.2 | Implement `FotMobProvider` | `src/sources/fotmob/provider.py` |
| 0.2.3 | Run ETL: fotmob_matches → normalized | Script + data |
| 0.2.4 | Validate ETL (counts, nulls, integrity) | Tests |

### 0.3 Computed Features
| Task | Description | Output |
|------|-------------|--------|
| 0.3.1 | Create `team_form` table and population script | Table + script |
| 0.3.2 | Create `player_form` table | Table + script |
| 0.3.3 | Create shot zone aggregations | Materialized view |
| 0.3.4 | Create H2H query/view | View |

---

## Phase 1: News Integration [Week 2]

### 1.1 Connect to BetHub Aggregator
| Task | Description | Output |
|------|-------------|--------|
| 1.1.1 | Audit BetHub news-aggregator code | Understanding |
| 1.1.2 | Create shared config/interface | `src/sources/news/config.py` |
| 1.1.3 | Create `NewsProvider` that wraps BetHub | `src/sources/news/provider.py` |
| 1.1.4 | Test: fetch news for a match | Working fetch |

### 1.2 Article Processing
| Task | Description | Output |
|------|-------------|--------|
| 1.2.1 | Define article schema for KB | Schema |
| 1.2.2 | Store articles in Knowledge Base | Working storage |
| 1.2.3 | Create relevance scoring | Scoring function |
| 1.2.4 | Test with real match | Articles stored |

---

## Phase 2: Agents [Weeks 3-4]

### 2.1 Agent Infrastructure
| Task | Description | Output |
|------|-------------|--------|
| 2.1.1 | Define `Agent` base class | `src/agents/base.py` |
| 2.1.2 | Define `AgentContext` (KB access, config) | Part of base |
| 2.1.3 | Create agent orchestrator | `src/agents/orchestrator.py` |

### 2.2 Research Agent
| Task | Description | Output |
|------|-------------|--------|
| 2.2.1 | Implement stats fetching | `research.py` |
| 2.2.2 | Implement news fetching | `research.py` |
| 2.2.3 | Implement H2H fetching | `research.py` |
| 2.2.4 | Store research in KB | Working storage |
| 2.2.5 | Test: research for Arsenal vs Liverpool | Research output |

### 2.3 Analysis Agent
| Task | Description | Output |
|------|-------------|--------|
| 2.3.1 | Implement matchup identification | `analysis.py` |
| 2.3.2 | Implement pattern detection | `analysis.py` |
| 2.3.3 | Implement article insight extraction (LLM) | `analysis.py` |
| 2.3.4 | Implement uncertainty flagging | `analysis.py` |
| 2.3.5 | Test: analyze research output | Analysis output |

### 2.4 Synthesis Agent
| Task | Description | Output |
|------|-------------|--------|
| 2.4.1 | Implement story identification | `synthesis.py` |
| 2.4.2 | Implement prediction generation | `synthesis.py` |
| 2.4.3 | Implement scenario building | `synthesis.py` |
| 2.4.4 | Implement webapp formatting | `synthesis.py` |
| 2.4.5 | Implement telegram formatting | `synthesis.py` |
| 2.4.6 | Test: synthesize for a match | Intelligence output |

### 2.5 Validation Agent
| Task | Description | Output |
|------|-------------|--------|
| 2.5.1 | Implement prediction retrieval | `validation.py` |
| 2.5.2 | Implement reality fetching | `validation.py` |
| 2.5.3 | Implement claim scoring | `validation.py` |
| 2.5.4 | Implement learning extraction | `validation.py` |
| 2.5.5 | Test: validate a completed match | Validation report |

### 2.6 Learning Agent
| Task | Description | Output |
|------|-------------|--------|
| 2.6.1 | Implement error pattern analysis | `learning.py` |
| 2.6.2 | Implement calibration check | `learning.py` |
| 2.6.3 | Implement knowledge generation | `learning.py` |
| 2.6.4 | Test: run on historical validations | Learning report |

---

## Phase 3: Delivery [Week 5]

### 3.1 Webapp Integration
| Task | Description | Output |
|------|-------------|--------|
| 3.1.1 | Connect BetHub to Postgres | DB config |
| 3.1.2 | Create API routes for intelligence | Next.js API |
| 3.1.3 | Create match intelligence page | React component |
| 3.1.4 | Create team page | React component |
| 3.1.5 | Create navigation | Routing |
| 3.1.6 | Test: view match intelligence | Working page |

### 3.2 Telegram Delivery
| Task | Description | Output |
|------|-------------|--------|
| 3.2.1 | Create Telegram formatting agent | `delivery/telegram.py` |
| 3.2.2 | Integrate with OpenClaw message tool | Integration |
| 3.2.3 | Create subscription management | DB + logic |
| 3.2.4 | Test: send intelligence to Telegram | Working delivery |

---

## Phase 4: End-to-End [Week 6]

### 4.1 Pipeline Automation
| Task | Description | Output |
|------|-------------|--------|
| 4.1.1 | Create pre-match pipeline script | `scripts/run_pre_match.py` |
| 4.1.2 | Create post-match pipeline script | `scripts/run_post_match.py` |
| 4.1.3 | Create cron jobs for automation | Cron config |
| 4.1.4 | Create monitoring/alerting | Logging + alerts |

### 4.2 Validation Sprint
| Task | Description | Output |
|------|-------------|--------|
| 4.2.1 | Run on full round (10 matches) | 10 intelligence outputs |
| 4.2.2 | Validate post-match | 10 validation reports |
| 4.2.3 | Review and iterate | Improvements |

### 4.3 Demo
| Task | Description | Output |
|------|-------------|--------|
| 4.3.1 | Prepare demo match | Full pipeline |
| 4.3.2 | Record demo video | Video |
| 4.3.3 | Document learnings | `docs/LEARNINGS.md` |

---

## Phase 5: Iteration [Ongoing]

### 5.1 Coverage Expansion
- Add more leagues
- Add more data sources
- Improve news coverage

### 5.2 Quality Improvement
- Better LLM prompts
- More sophisticated analysis
- Calibration improvements

### 5.3 Feature Addition
- Player deep dives
- Custom queries
- API for external users

---

## Success Criteria for V0.1

1. **Coverage:** Can generate intelligence for all Premier League matches
2. **Quality:** Intelligence reads as valuable (not generic)
3. **Validation:** Can score predictions post-match
4. **Delivery:** Accessible via webapp and Telegram
5. **Automation:** Runs with minimal manual intervention

---

## Dependencies

```
clarity_engine ←── FotMob data (✅ have)
       │
       ├──────────← API-Football (✅ available)
       │
       ├──────────← BetHub news-aggregator (✅ exists, need to connect)
       │
       └──────────← BetHub webapp (✅ exists, need to adapt)
```

---

## Timeline

```
Week 1: Foundation (schema, ETL, features)
Week 2: News integration
Week 3: Agents (research, analysis)
Week 4: Agents (synthesis, validation, learning)
Week 5: Delivery (webapp, telegram)
Week 6: E2E testing, demo
────────────────────────────────────────────
Total: 6 weeks to V0.1
```

---

*Last updated: 2026-02-15*
