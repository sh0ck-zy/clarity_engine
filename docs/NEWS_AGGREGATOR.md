# News Aggregator Integration

## Overview

BetHub already has a comprehensive news aggregator at:
```
/Users/joao/Projects/bethub/webapp/src/lib/news-aggregator/
```

**DO NOT rebuild this. Integrate it.**

---

## What BetHub Aggregator Has

### Collectors

| Collector | File | Sources |
|-----------|------|---------|
| **RSS** | `collectors/rss_collector.py` | BBC Sport, Guardian, Sky, ESPN, club official feeds, league feeds |
| **Reddit** | `collectors/reddit_collector.py` | r/soccer, team subreddits, league subreddits |
| **Twitter** | `collectors/nitter_collector.py` | Journalists, clubs, leagues (via Nitter) |
| **Web Scraper** | `collectors/scraper_collector.py` | Club websites, fallback scraping |
| **News APIs** | `collectors/api_collector.py` | Guardian API, NewsData, Currents |

### Processors

| Processor | File | Function |
|-----------|------|----------|
| **Content** | `processors/content_processor.py` | Extract and clean article content |
| **Deduplicator** | `processors/deduplicator.py` | Remove duplicate articles |
| **Quality Scorer** | `processors/quality_scorer.py` | Score source and content quality |
| **Sentiment** | `processors/sentiment_analyzer.py` | Sentiment analysis |

### Configuration

Main config: `config.py`

Includes:
- RSS feed URLs (40+ sources)
- Reddit subreddits (20+)
- Twitter accounts (journalists, clubs)
- Quality scoring weights
- Rate limiting
- Team name variations

---

## Key Features We Can Use

### 1. Match-Specific Collection
```python
from news_aggregator.collectors import RSSCollector

async with RSSCollector() as collector:
    articles = await collector.collect_for_match(
        home_team="Arsenal",
        away_team="Liverpool",
        match_date=datetime(2026, 2, 20)
    )
```

### 2. Quality Scoring
```python
from news_aggregator.config import QUALITY_SCORING

# Source weights
QUALITY_SCORING['source_weights'] = {
    'bbc_sport': 0.95,
    'guardian_football': 0.92,
    'reddit_discussion': 0.65,
    # ...
}

# Content multipliers
QUALITY_SCORING['content_multipliers'] = {
    'breaking_news': 1.3,
    'injury_news': 1.1,
    'rumor': 0.6,
    # ...
}
```

### 3. Team Variations
```python
from news_aggregator.config import TEAM_VARIATIONS

TEAM_VARIATIONS = {
    'Manchester United': ['Man United', 'ManUtd', 'United', 'MUFC'],
    'Liverpool': ['LFC', 'The Reds'],
    # ...
}
```

---

## Integration Plan

### Option A: Shared Library
1. Extract news-aggregator to shared package
2. Import in both BetHub webapp and Clarity Engine
3. Share config and collectors

```
/Users/joao/Projects/shared-libs/
└── news-aggregator/
    ├── collectors/
    ├── processors/
    └── config.py
```

### Option B: API Service
1. Create FastAPI wrapper around aggregator
2. Clarity Engine calls API
3. BetHub webapp calls API

```
# clarity_engine or bethub
POST /api/news/collect
{
    "home_team": "Arsenal",
    "away_team": "Liverpool",
    "match_date": "2026-02-20"
}
```

### Option C: Copy and Adapt (Simplest for now)
1. Copy relevant code to Clarity Engine
2. Adapt for our needs
3. Consolidate later

**Recommendation: Start with Option C**, consolidate later.

---

## What We Need to Add

### 1. Article Insight Extraction
Current aggregator collects and scores articles.
We need to EXTRACT insights:

```python
async def extract_insights(article: Article) -> List[Insight]:
    """
    Use LLM to extract structured insights from article.
    
    Example output:
    [
        Insight(
            type="injury",
            entity="player:saka",
            claim="Trained Friday, expected to start",
            source="the_athletic",
            confidence=0.85
        ),
        Insight(
            type="tactical",
            entity="team:arsenal",
            claim="Will target Liverpool's right side",
            source="the_athletic",
            confidence=0.70
        )
    ]
    """
```

### 2. Knowledge Base Storage
Store articles and insights in KB:

```sql
CREATE TABLE kb_articles (
    id SERIAL PRIMARY KEY,
    match_id INT REFERENCES matches(id),
    url TEXT UNIQUE,
    title TEXT,
    source TEXT,
    quality_score NUMERIC,
    published_at TIMESTAMP,
    content TEXT,
    collected_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE kb_insights (
    id SERIAL PRIMARY KEY,
    article_id INT REFERENCES kb_articles(id),
    match_id INT REFERENCES matches(id),
    type TEXT,  -- 'injury', 'tactical', 'lineup', 'opinion'
    entity_type TEXT,  -- 'team', 'player', 'match'
    entity_id TEXT,
    claim TEXT,
    confidence NUMERIC,
    extracted_at TIMESTAMP DEFAULT NOW()
);
```

### 3. Temporal Relevance
Current aggregator has date filtering.
We need to prioritize:
- Last 24-48h before match: highest relevance
- 2-7 days: medium relevance
- Older: lower relevance

---

## Dependencies

BetHub aggregator requires:
```
feedparser==6.0.10
beautifulsoup4==4.12.2
praw==7.7.1
aiohttp==3.9.0
newspaper3k==0.2.8
langdetect==1.0.9
```

Add to `clarity_engine/requirements.txt`:
```
feedparser>=6.0.10
beautifulsoup4>=4.12.2
praw>=7.7.1
aiohttp>=3.9.0
newspaper3k>=0.2.8
langdetect>=1.0.9
```

---

## Environment Variables Needed

```bash
# Reddit (optional but recommended)
REDDIT_CLIENT_ID=xxx
REDDIT_CLIENT_SECRET=xxx

# Guardian API (free tier: 5000/day)
GUARDIAN_API_KEY=xxx

# NewsData API (free tier: 200/day)
NEWSDATA_API_KEY=xxx
```

---

## Next Steps

1. [ ] Copy `news-aggregator` to `clarity_engine/src/sources/news/`
2. [ ] Test basic collection for a match
3. [ ] Add article storage to KB
4. [ ] Implement insight extraction (LLM)
5. [ ] Integrate with Research Agent

---

*Last updated: 2026-02-15*
