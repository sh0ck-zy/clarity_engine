# Clarity Engine — Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         WEBAPP (UI)                              │
│         Navigate data, view intelligence, drill-down             │
├─────────────────────────────────────────────────────────────────┤
│                    INTELLIGENCE AGENTS                           │
│     Research → Analyze → Synthesize → Validate → Learn          │
├─────────────────────────────────────────────────────────────────┤
│                      KNOWLEDGE BASE                              │
│     Facts | Insights | Opinions | Predictions | Validations     │
├─────────────────────────────────────────────────────────────────┤
│                      DATA PLATFORM                               │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐ │
│  │  Sources  │→ │    ETL    │→ │ Normalized │→ │  Monitoring  │ │
│  │           │  │ Pipelines │  │   Schema   │  │  & Quality   │ │
│  └───────────┘  └───────────┘  └───────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Data Platform

### Sources

| Source | Type | Data | Status |
|--------|------|------|--------|
| **external APIs** | Primary | Matches, players, shotmaps, momentum | ✅ 260 matches |
| **API-Football** | Secondary | Fixtures, odds, standings | ✅ Available |
| **News Aggregator** | Text | News, articles, expert analysis | ✅ BetHub has this |
| **Reddit** | Social | Discussions, sentiment | ✅ In aggregator |
| **Twitter/X** | Social | Breaking news, reactions | ✅ Via Nitter |

### Normalized Schema

```sql
-- Core Entities
competitions (id, name, country, type)
seasons (id, competition_id, year, start_date, end_date)
teams (id, name, short_name, country, logo_url)
players (id, name, nationality, position)

-- Match Data
matches (id, season_id, round, home_team_id, away_team_id, datetime, status)
match_stats (match_id, team_id, possession, shots, xg, ...)
match_events (match_id, minute, type, player_id, x, y, metadata)
player_match_stats (match_id, player_id, minutes, goals, rating, ...)

-- Computed State
team_form (team_id, season_id, round, form_array, rolling_xg, ...)
player_form (player_id, season_id, round, rolling_stats)
team_style (team_id, season_id, cluster_label, style_metrics)
```

### ETL Pipelines

```python
# Abstract base for all providers
class SourceProvider(ABC):
    @abstractmethod
    async def fetch(self, params: dict) -> RawData: ...
    
    @abstractmethod
    def transform(self, raw: RawData) -> NormalizedData: ...
    
    @abstractmethod
    async def load(self, data: NormalizedData) -> None: ...

# Implementations
class external APIsProvider(SourceProvider): ...
class APIFootballProvider(SourceProvider): ...
class NewsAggregatorProvider(SourceProvider): ...
```

---

## Layer 2: Knowledge Base

The Knowledge Base stores everything we know, organized by type:

### Facts (Objective, from sources)
```json
{
  "type": "fact",
  "entity": "team:arsenal",
  "attribute": "xg_last_5",
  "value": 1.82,
  "source": "external data",
  "timestamp": "2026-02-15T10:00:00Z"
}
```

### Insights (Learned by us)
```json
{
  "type": "insight",
  "claim": "Arsenal struggles vs low blocks",
  "evidence": [
    {"type": "stat", "value": "1.1 xG vs low blocks (vs 1.8 avg)", "source": "derived"},
    {"type": "matches", "value": ["match:123", "match:456"], "pattern": "confirmed 4/5 times"}
  ],
  "confidence": 0.78,
  "created_at": "2026-02-10T00:00:00Z"
}
```

### Opinions (From experts, not ours)
```json
{
  "type": "opinion",
  "source": "the_athletic",
  "author": "Michael Cox",
  "claim": "Liverpool's new shape fixes midfield issues",
  "url": "https://...",
  "published_at": "2026-02-14T00:00:00Z",
  "credibility": 0.9
}
```

### Predictions (Our takes)
```json
{
  "type": "prediction",
  "match_id": "match:789",
  "claims": [
    {"claim": "Arsenal will dominate possession", "value": "58-62%", "confidence": 0.75},
    {"claim": "Left channel will be key danger zone", "confidence": 0.82},
    {"claim": "BTTS likely", "value": "yes", "confidence": 0.74}
  ],
  "created_at": "2026-02-15T08:00:00Z",
  "status": "pending"
}
```

### Validations (Post-match)
```json
{
  "type": "validation",
  "prediction_id": "pred:123",
  "match_id": "match:789",
  "results": [
    {"claim": "Arsenal possession 58-62%", "actual": "58%", "score": 1.0},
    {"claim": "Left channel danger zone", "actual": "0.62 xG from left (vs 0.28 avg)", "score": 0.9},
    {"claim": "BTTS", "actual": "yes", "score": 1.0}
  ],
  "overall_score": 0.87,
  "learnings": ["Left channel model accurate", "Trent vulnerability confirmed"]
}
```

---

## Layer 3: Intelligence Agents

### Agent 1: Research Agent

**Purpose:** Collect all relevant information for a match.

```python
class ResearchAgent:
    """
    Collects stats + news + opinions for a match.
    Does NOT interpret. Just gathers.
    """
    
    async def research(self, match: Match) -> ResearchOutput:
        # 1. Get team stats (last 5 matches)
        home_stats = await self.get_team_stats(match.home_team, last_n=5)
        away_stats = await self.get_team_stats(match.away_team, last_n=5)
        
        # 2. Get H2H history
        h2h = await self.get_h2h(match.home_team, match.away_team)
        
        # 3. Get news (injuries, suspensions, drama)
        news = await self.news_aggregator.collect_for_match(
            match.home_team, match.away_team, match.datetime
        )
        
        # 4. Get expert analysis (articles, podcasts)
        analysis = await self.get_expert_analysis(match)
        
        # 5. Get odds and market sentiment
        odds = await self.get_odds(match)
        
        # 6. Store in Knowledge Base
        await self.kb.store_research(match.id, {
            'stats': {'home': home_stats, 'away': away_stats},
            'h2h': h2h,
            'news': news,
            'analysis': analysis,
            'odds': odds
        })
        
        return ResearchOutput(...)
```

### Agent 2: Analysis Agent

**Purpose:** Structure insights from raw research.

```python
class AnalysisAgent:
    """
    Reads research and identifies patterns, edges, uncertainties.
    Combines quantitative (stats) with qualitative (articles).
    """
    
    async def analyze(self, research: ResearchOutput) -> AnalysisOutput:
        # 1. Identify key matchups
        matchups = self.identify_matchups(research)
        
        # 2. Find tactical patterns
        patterns = self.find_patterns(research)
        
        # 3. Extract insights from articles (LLM)
        article_insights = await self.extract_from_articles(research.analysis)
        
        # 4. Identify contradictions
        # "Stats say X but expert says Y"
        contradictions = self.find_contradictions(research, article_insights)
        
        # 5. Identify uncertainties
        # "We don't know X"
        uncertainties = self.identify_unknowns(research)
        
        # 6. Generate structured analysis
        return AnalysisOutput(
            key_matchups=matchups,
            patterns=patterns,
            insights=article_insights,
            contradictions=contradictions,
            uncertainties=uncertainties,
            evidence_map=self.build_evidence_map(research)
        )
```

### Agent 3: Synthesis Agent

**Purpose:** Create narrative for humans.

```python
class SynthesisAgent:
    """
    Takes structured analysis and creates story-driven output.
    Adapts format to channel (webapp vs telegram).
    """
    
    async def synthesize(
        self, 
        analysis: AnalysisOutput,
        channel: str = "webapp"
    ) -> Intelligence:
        
        # 1. Determine the "story" of this match
        story = self.identify_story(analysis)
        # e.g., "Two pressing teams, something has to give"
        
        # 2. Rank insights by importance
        ranked_insights = self.rank_by_importance(analysis.insights)
        
        # 3. Create predictions with evidence
        predictions = self.generate_predictions(analysis)
        
        # 4. Build scenarios
        scenarios = self.build_scenarios(analysis)
        # "If Arsenal scores first...", "If 0-0 at 60'..."
        
        # 5. Format for channel
        if channel == "webapp":
            output = self.format_webapp(story, ranked_insights, predictions, scenarios)
        elif channel == "telegram":
            output = self.format_telegram(story, ranked_insights, predictions, scenarios)
        
        # 6. Store predictions in KB for validation
        await self.kb.store_predictions(match_id, predictions)
        
        return output
```

### Agent 4: Validation Agent

**Purpose:** Compare predictions with reality post-match.

```python
class ValidationAgent:
    """
    After match ends, compares our predictions with what happened.
    Scores accuracy and generates learnings.
    """
    
    async def validate(self, match_id: str) -> ValidationReport:
        # 1. Get our predictions
        predictions = await self.kb.get_predictions(match_id)
        
        # 2. Get actual match data
        reality = await self.get_match_reality(match_id)
        
        # 3. Compare each claim
        results = []
        for pred in predictions.claims:
            score = self.score_prediction(pred, reality)
            results.append({
                'claim': pred.claim,
                'predicted': pred.value,
                'actual': self.get_actual(pred.claim, reality),
                'score': score
            })
        
        # 4. Calculate overall score
        overall = sum(r['score'] for r in results) / len(results)
        
        # 5. Generate learnings
        learnings = self.extract_learnings(predictions, reality, results)
        
        # 6. Store validation
        await self.kb.store_validation(match_id, results, learnings)
        
        return ValidationReport(
            match_id=match_id,
            results=results,
            overall_score=overall,
            learnings=learnings
        )
```

### Agent 5: Learning Agent

**Purpose:** Improve the system over time.

```python
class LearningAgent:
    """
    Analyzes historical validations to improve predictions.
    Updates confidence calibration, identifies blind spots.
    """
    
    async def learn(self, period: str = "last_30_days") -> LearningReport:
        # 1. Get all validations in period
        validations = await self.kb.get_validations(period)
        
        # 2. Analyze error patterns
        errors = self.analyze_errors(validations)
        # e.g., "We consistently underestimate Liverpool away"
        
        # 3. Check calibration
        calibration = self.check_calibration(validations)
        # e.g., "Our 70% predictions are correct 65% of time"
        
        # 4. Identify blind spots
        blind_spots = self.find_blind_spots(validations)
        # e.g., "We don't track manager rotation patterns"
        
        # 5. Generate institutional knowledge
        knowledge = self.generate_knowledge(validations)
        # Facts we've learned that should inform future predictions
        
        # 6. Propose improvements
        improvements = self.propose_improvements(errors, blind_spots)
        
        # 7. Store learnings
        await self.kb.store_learnings(knowledge)
        
        return LearningReport(
            calibration=calibration,
            error_patterns=errors,
            blind_spots=blind_spots,
            new_knowledge=knowledge,
            proposed_improvements=improvements
        )
```

---

## Layer 4: Delivery

### Webapp
- Full match intelligence pages
- Team deep dives
- Player profiles
- League views
- Navigation and drill-down

### Telegram Bot
- Formatted intelligence
- Alerts (lineup, odds movement)
- On-demand queries
- Subscription tiers

### API
- Raw intelligence endpoints
- Custom queries
- Bulk access

---

## Data Flow: Pre-Match

```
1. TRIGGER: Match in 48h
   │
2. RESEARCH AGENT
   ├── Fetch team stats (external APIs)
   ├── Fetch H2H (external APIs)
   ├── Fetch news (News Aggregator)
   ├── Fetch articles (RSS, scrapers)
   └── Fetch odds (API-Football)
   │
3. ANALYSIS AGENT
   ├── Identify key matchups
   ├── Extract article insights (LLM)
   ├── Find patterns
   └── Flag uncertainties
   │
4. SYNTHESIS AGENT
   ├── Create narrative
   ├── Generate predictions
   ├── Build scenarios
   └── Format for channels
   │
5. DELIVERY
   ├── Publish to webapp
   ├── Send to Telegram subscribers
   └── Update after lineups
```

## Data Flow: Post-Match

```
1. TRIGGER: Match ended
   │
2. FETCH RESULTS
   ├── Match stats (external APIs)
   ├── Player performances
   └── Events timeline
   │
3. VALIDATION AGENT
   ├── Compare predictions vs reality
   ├── Score each claim
   └── Generate learnings
   │
4. LEARNING AGENT (periodic)
   ├── Analyze error patterns
   ├── Update calibration
   └── Generate institutional knowledge
   │
5. KNOWLEDGE BASE
   └── Store for future predictions
```

---

## Technology Choices

| Component | Choice | Reason |
|-----------|--------|--------|
| Database | PostgreSQL | Relational + JSONB flexibility |
| Agent Framework | OpenClaw sessions | Already integrated |
| LLM | Claude | Quality + context window |
| Webapp | Next.js (BetHub) | Already exists |
| Queue | Simple cron for now | Can upgrade later |
| Cache | Redis or simple file | Speed |

---

## Directory Structure

```
clarity_engine/
├── docs/                          # Documentation
│   ├── VISION.md
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   └── GAPS.md
│
├── src/
│   ├── database/
│   │   ├── schema.sql             # Normalized schema
│   │   ├── knowledge_base.sql     # KB tables
│   │   └── config.py
│   │
│   ├── sources/                   # Data providers
│   │   ├── base.py                # SourceProvider ABC
│   │   ├── external data/
│   │   ├── api_football/
│   │   └── news/                  # Link to BetHub aggregator
│   │
│   ├── agents/                    # Intelligence agents
│   │   ├── base.py
│   │   ├── research.py
│   │   ├── analysis.py
│   │   ├── synthesis.py
│   │   ├── validation.py
│   │   └── learning.py
│   │
│   ├── knowledge/                 # Knowledge Base
│   │   ├── store.py
│   │   └── queries.py
│   │
│   └── delivery/                  # Output formatting
│       ├── webapp.py
│       └── telegram.py
│
├── scripts/
│   ├── run_pre_match.py           # Generate match intelligence
│   ├── run_post_match.py          # Validate predictions
│   └── run_learning.py            # Periodic learning
│
└── webapp/                        # Or link to BetHub
```

---

*Last updated: 2026-02-15*
