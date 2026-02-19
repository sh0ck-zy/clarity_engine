# Clarity Engine — Gaps & Challenges

## Critical Questions We Haven't Answered

### 1. How Do We Measure "Good" Intelligence?

**The Problem:**
We can measure if a prediction is correct (Arsenal won, BTTS happened).
But how do we measure if the *intelligence* was valuable?

**Examples of Valuable Intelligence:**
- "Left channel will be key" → Was it? How do we measure?
- "Expect open game" → What's the threshold?
- "Trent will struggle" → Rating < 6.5? Duels lost > 60%?

**Needed:**
- Define measurable proxies for each type of claim
- Create scoring rubric for subjective claims
- Track whether users found it valuable (feedback loop?)

**Status:** ❌ Not defined

---

### 2. How Do We Extract Insights from Articles?

**The Problem:**
Articles contain valuable context:
- "Arteta said in presser that Saka is fit"
- "Liverpool have changed to 4-2-3-1 in recent weeks"
- "Expert thinks Arsenal will struggle vs low block"

How do we reliably extract this?

**Options:**
1. **LLM extraction** — Prompt Claude to extract structured insights
2. **Named Entity Recognition** — Extract players, teams, events
3. **Manual curation** — Human reviews key articles

**Challenges:**
- Hallucination risk
- Cost at scale
- Keeping structure consistent

**Status:** ❌ Not implemented

---

### 3. What Makes an Insight "Trustworthy"?

**The Problem:**
Not all information is equal:
- FotMob stat: High trust
- The Athletic article: High trust
- Random tweet: Low trust
- Reddit comment: Very low trust

How do we weight these in our analysis?

**Needed:**
- Source credibility scoring
- Claim validation against multiple sources
- Explicit confidence levels with justification

**Status:** 🟡 BetHub has basic quality scoring, needs refinement

---

### 4. How Do We Handle Uncertainty?

**The Problem:**
Before lineups drop, we don't know:
- Who's starting
- Exact formation
- Late fitness changes

Our predictions might be invalidated by a lineup decision.

**Approach:**
- Clearly mark predictions as "pre-lineup" vs "post-lineup"
- Update intelligence after lineups drop
- Flag which predictions depend on lineup

**Status:** ❌ Not designed

---

### 5. What Data Don't We Have (But Need)?

**Missing Data:**

| Data | Why We Need It | Where to Get |
|------|---------------|--------------|
| Pass maps | Build-up analysis, progression zones | StatsBomb, Opta (paid) |
| Pressure events | Pressing intensity, triggers | StatsBomb (paid) |
| Player heatmaps | Actual positions, not nominal | FBref (free), Opta (paid) |
| Defensive actions | Tackles, interceptions by zone | FotMob has some |
| PPDA | Pressing intensity metric | WhoScored, can calculate |

**Workaround:**
- Derive what we can from shotmaps + basic stats
- Be honest about limitations
- Add sources as available

**Status:** 🟡 Partially mapped

---

### 6. How Do We Handle Multiple Leagues?

**The Problem:**
System should be league-agnostic, but:
- Different leagues have different data availability
- Team/player IDs differ across sources
- Some sources only cover certain leagues

**Needed:**
- Abstract "competition" config
- ID mapping layer
- Graceful degradation when data missing

**Status:** ❌ Currently hardcoded to Premier League

---

### 7. How Do We Calibrate Confidence?

**The Problem:**
When we say "70% confidence," it should mean:
- 70% of our 70% predictions are correct

But without historical validation, we're guessing.

**Approach:**
1. Start with heuristic confidence
2. Track actual accuracy
3. Adjust calibration over time

**Implementation:**
- Store all predictions with confidence
- Validate and score
- Periodic calibration report
- Adjust confidence calculation

**Status:** ❌ No historical data yet

---

### 8. How Do Agents Coordinate?

**The Problem:**
We have 5 agents. How do they work together?

**Questions:**
- Sequential or parallel?
- How does context flow between them?
- What if one agent fails?
- How do we debug/trace?

**Options:**
1. **Simple orchestrator** — Sequential calls, pass outputs
2. **Event-driven** — Agents react to KB changes
3. **Full framework** — LangGraph, CrewAI, etc.

**Recommendation:**
Start simple (1), add complexity as needed.

**Status:** ❌ Not implemented

---

### 9. How Do We Keep Data Fresh?

**The Problem:**
- Pre-match intelligence should update as news comes in
- Lineups change everything
- Odds move

**Needed:**
- Incremental updates (not regenerate everything)
- Clear "last updated" timestamps
- Notification when significant change

**Status:** ❌ Not designed

---

### 10. Cost Management

**The Problem:**
- LLM calls cost money
- API calls have rate limits
- At scale, this adds up

**Questions:**
- How many LLM calls per match?
- Can we cache/reuse?
- What's the cost per match?

**Rough Estimate:**
- Research: ~5 API calls
- Analysis (with LLM): ~3 Claude calls
- Synthesis: ~2 Claude calls
- Total: ~$0.10-0.50 per match?

**Status:** ❌ Not measured

---

## Technical Debt / Cleanup Needed

### Current State Issues

1. **No normalized schema** — Raw FotMob data, not entities
2. **No ID linking** — fotmob_match_id ≠ fixture_id (API-Football)
3. **Models not used** — Created Pydantic schemas, not integrated
4. **BetHub disconnected** — Webapp exists but uses Supabase

### Code Cleanup

1. Archive old experiments in `clarity_engine/archive/`
2. Consolidate docs (many overlapping files)
3. Update `requirements.txt`
4. Create proper project structure

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| LLM hallucinations | Bad intelligence | Medium | Human review, citations |
| Data source goes down | No intelligence | Low | Multiple sources, caching |
| Cost overrun | Unsustainable | Medium | Monitoring, caching |
| Low accuracy | No value | Medium | Validation loop, iterate |
| Over-engineering | Never ships | High | Start simple, iterate |

---

## Open Decisions

### Architecture
- [ ] Use OpenClaw sessions for agents or custom?
- [ ] Postgres only or add vector DB?
- [ ] Monorepo (clarity_engine + bethub) or separate?

### Product
- [ ] Free tier scope?
- [ ] Pricing for paid tiers?
- [ ] Which leagues first?

### Process
- [ ] Manual review before publishing?
- [ ] How to handle corrections?
- [ ] Feedback mechanism?

---

## What We Need to Learn

1. **Domain expertise** — Watch more tactical analysis
2. **User needs** — Talk to potential users
3. **Competition** — What do paid services offer?
4. **ML approaches** — Could models predict better than heuristics?

---

*Last updated: 2026-02-15*
