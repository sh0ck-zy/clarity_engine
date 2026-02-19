# Clarity Engine - Technical Architecture

## For: Senior Data Engineer Review

**Last Updated:** 2026-01-24
**Status:** Phase 1 Complete (Data Layer)

---

## 1. Project Overview

### What is Clarity Engine?

Clarity Engine is a **football match intelligence system** that generates pre-match analysis narratives grounded in real data. The goal is to produce analyses that consistently outperform generic ChatGPT-style previews by:

1. **Grounding claims in verifiable facts** (injuries, lineups, odds, form, xG)
2. **Separating deterministic context from LLM-generated narrative**
3. **Evaluating narrative quality post-match** against actual outcomes

### Core Problem

Generic LLM match previews mix facts with uncalibrated opinions. Users can't tell which claims are based on real data vs. hallucinated. Clarity Engine solves this by:

- Building a **deterministic context layer** with all pre-match facts
- Passing that context to an LLM with a **strict output schema**
- **Evaluating predictions** against actual match outcomes

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA SOURCES                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │    FBRef     │  │ Transfermarkt│  │ Football-Data│  │   ClubElo    │   │
│  │  (fixtures,  │  │  (injuries,  │  │    (.co.uk)  │  │  (ratings)   │   │
│  │     xG)      │  │   lineups)   │  │    (odds)    │  │              │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
│         │                 │                 │                 │            │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐   │
│  │   Understat  │  │              │  │              │  │              │   │
│  │  (PPDA, tilt)│  │              │  │              │  │              │   │
│  └──────┬───────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│         │                                                                  │
└─────────┼──────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INGESTION LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  src/ingestion/                                                             │
│  ├── scraper.py                  # FBRef fixtures + xG (Selenium)          │
│  ├── transfermarkt_injuries.py   # Injury history per player               │
│  ├── transfermarkt_lineups.py    # Match lineups + formations              │
│  ├── transfermarkt_match_ids.py  # Fixture → TM match ID mapping           │
│  ├── understat_enrich.py         # PPDA + Field Tilt metrics               │
│  └── elo_backfill.py             # ClubElo daily ratings                   │
│                                                                             │
│  scripts/                                                                   │
│  └── download_odds_historical.py # Football-data.co.uk CSV import          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         POSTGRESQL DATABASE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Hub Table:                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ fixtures                                                             │   │
│  │ ├── id (PK): "2025-08-16_Arsenal_Wolves"                            │   │
│  │ ├── date, home_team, away_team, season                              │   │
│  │ ├── home_goals, away_goals, result (post-match)                     │   │
│  │ └── home_xg, away_xg (post-match)                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         │ fixture_id (FK)                                                  │
│         ▼                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ lineups_     │  │ odds_        │  │ tm_match_    │  │ player_      │   │
│  │ historical   │  │ snapshots    │  │ mapping      │  │ injuries_    │   │
│  │              │  │              │  │              │  │ historical   │   │
│  │ - formation  │  │ - market_key │  │ - tm_match_id│  │ - injury_type│   │
│  │ - starters   │  │ - odds_dec   │  │ - home_team  │  │ - from_date  │   │
│  │ - bench      │  │ - captured_at│  │ - away_team  │  │ - end_date   │   │
│  │ (JSONB)      │  │ - source     │  │              │  │ - days_missed│   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
│                                                                             │
│  Supporting Tables:                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                     │
│  │ team_elo     │  │ team_form    │  │ evaluations  │                     │
│  │              │  │              │  │              │                     │
│  │ - elo_rating │  │ - xg_for     │  │ - narrative  │                     │
│  │ - rating_date│  │ - xg_against │  │ - score      │                     │
│  │              │  │ - ppda       │  │ - alignment  │                     │
│  └──────────────┘  └──────────────┘  └──────────────┘                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CONTEXT BUILDER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  src/analysis/context_builder_v2.py                                         │
│                                                                             │
│  Assembles all pre-match data into a structured MatchContext:               │
│                                                                             │
│  MatchContext                                                               │
│  ├── fixture_id: "2025-01-18_Liverpool_Bournemouth"                        │
│  ├── match_date: 2025-01-18                                                │
│  ├── home: TeamContext                                                      │
│  │   ├── identity: {name, elo, elo_delta}                                  │
│  │   ├── form: {last_5, xg_for, xg_against, ppda}                          │
│  │   ├── absences: {total_missing, players[]}                              │
│  │   └── lineup: {formation, starters[], bench[]}                          │
│  ├── away: TeamContext                                                      │
│  └── odds: {home_win, draw, away_win, source}                              │
│                                                                             │
│  KEY DESIGN: Time-Travel Safety                                             │
│  - Only includes data that was available BEFORE match kickoff               │
│  - Injuries filtered by: from_date <= match_date AND                        │
│                          (end_date IS NULL OR end_date > match_date)        │
│  - Form calculated from matches BEFORE this fixture                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NARRATIVE LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  src/analysis/narrative_schema.py                                           │
│  src/analysis/evaluator.py                                                  │
│                                                                             │
│  Narrative Generation Pipeline:                                             │
│                                                                             │
│  1. MatchContext (JSON) → LLM Prompt                                        │
│  2. LLM generates NarrativeOutput (strict JSON schema)                      │
│  3. Post-match: Evaluator scores narrative vs actual outcome                │
│                                                                             │
│  NarrativeOutput Schema:                                                    │
│  {                                                                          │
│    "match_id": "...",                                                       │
│    "headline": "...",                                                       │
│    "key_factors": [                                                         │
│      {"factor": "...", "impact": "positive|negative|neutral",              │
│       "evidence": "grounded in context data"}                               │
│    ],                                                                       │
│    "prediction": {                                                          │
│      "outcome": "home_win|draw|away_win",                                  │
│      "confidence": 0.0-1.0,                                                │
│      "reasoning": "..."                                                     │
│    },                                                                       │
│    "risks": ["..."],                                                        │
│    "narrative": "Full prose analysis..."                                    │
│  }                                                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DASHBOARD                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  src/dashboard_v3.py (Streamlit)                                            │
│                                                                             │
│  Views:                                                                     │
│  - Fixture Explorer: Browse matches, see context + narrative                │
│  - Data Coverage: Track gaps in injuries/lineups/odds                       │
│  - Evaluation Trends: Narrative quality over time (TODO)                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Pipeline Details

### 3.1 Data Sources

| Source | Data Type | Method | Rate Limit | Coverage |
|--------|-----------|--------|------------|----------|
| FBRef | Fixtures, xG, match results | Selenium scraping | Cloudflare protected | 100% |
| Transfermarkt | Injuries | requests + BeautifulSoup | 2s delay | 3,337 records |
| Transfermarkt | Lineups | requests + BeautifulSoup | 2s delay | 94% (358/380) |
| Football-Data.co.uk | Betting odds | CSV download | None | 58% (played matches) |
| ClubElo | Team ratings | REST API | Light | 100% |
| Understat | PPDA, Field Tilt | JSON API | Light | 100% |

### 3.2 Fixture ID Convention

All tables use a composite fixture ID format:
```
{YYYY-MM-DD}_{HomeTeam}_{AwayTeam}
```

Examples:
- `2025-08-16_Arsenal_Wolves`
- `2025-01-18_Liverpool_Bournemouth`

This serves as the primary key in `fixtures` and foreign key in satellite tables.

### 3.3 Team Name Normalization

Different sources use different team names. We use fuzzy matching (rapidfuzz) with a canonical mapping:

```python
# Canonical names (used in DB)
CANONICAL_TEAMS = [
    "Arsenal",
    "Brighton and Hove Albion",
    "Nottingham Forest",
    "Wolverhampton Wanderers",
    # ...
]

# Aliases for matching
TEAM_ALIASES = {
    "brighton": "Brighton and Hove Albion",
    "nott'm forest": "Nottingham Forest",
    "wolves": "Wolverhampton Wanderers",
    # ...
}
```

### 3.4 Odds Pipeline

```python
# scripts/download_odds_historical.py

# 1. Download CSV from football-data.co.uk
url = f"https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"

# 2. Parse bookmaker columns (Bet365, Pinnacle, William Hill)
BOOKMAKER_COLUMNS_OPEN = {
    "B365": {"HOME": "B365H", "DRAW": "B365D", "AWAY": "B365A"},
    "PS": {"HOME": "PSH", "DRAW": "PSD", "AWAY": "PSA"},
}
BOOKMAKER_COLUMNS_CLOSE = {
    "B365": {"HOME": "B365CH", "DRAW": "B365CD", "AWAY": "B365CA"},
    # ...
}

# 3. Average across bookmakers for each selection
# 4. Store both opening (48h pre-match) and closing (1h pre-match) odds
# 5. Match to fixtures table via (date, home_team, away_team) fuzzy match
```

### 3.5 Injuries Pipeline

```python
# src/ingestion/transfermarkt_injuries.py

# 1. Fetch squad page: /kader/verein/{team_id}/saison_id/{year}
# 2. Extract player IDs from DOM
# 3. For each player, fetch: /verletzungen/spieler/{player_id}
# 4. Parse injury table with pandas.read_html()
# 5. Store in player_injuries_historical

@dataclass
class InjuryRecord:
    player_id: str
    player_name: str
    team: str
    injury_type: str       # "Hamstring Injury", "Knee Injury"
    from_date: date
    end_date: Optional[date]
    days_missed: int
    games_missed: int
```

### 3.6 Lineups Pipeline

```python
# src/ingestion/transfermarkt_lineups.py

# 1. Get TM match ID from tm_match_mapping table
# 2. Fetch spielbericht page: /spielbericht/index/spielbericht/{match_id}
# 3. Parse formation and player lists from DOM
# 4. Store in lineups_historical (JSONB for starters/bench)

@dataclass
class MatchLineup:
    fixture_id: str
    match_id: str
    home_team: str
    away_team: str
    home_formation: str    # "4-3-3", "4-2-3-1"
    away_formation: str
    home_starters: List[PlayerInfo]
    away_starters: List[PlayerInfo]
    home_bench: List[PlayerInfo]
    away_bench: List[PlayerInfo]
```

---

## 4. Context Builder

The context builder (`src/analysis/context_builder_v2.py`) is the core assembly point that creates a complete pre-match picture.

### 4.1 MatchContext Schema

```python
@dataclass
class MatchContext:
    fixture_id: str
    match_date: date
    home: TeamContext
    away: TeamContext
    odds: Optional[OddsContext]

@dataclass
class TeamContext:
    identity: TeamIdentity      # name, elo, elo_delta
    form: TeamForm              # last_5 results, xG, PPDA
    absences: AbsenceContext    # injured/suspended players
    lineup: Optional[LineupContext]  # formation, starters

@dataclass
class AbsenceContext:
    total_missing: int
    players: List[AbsentPlayer]

@dataclass
class AbsentPlayer:
    player_name: str
    injury_type: str
    days_out: int
```

### 4.2 Time-Travel Safety

Critical design principle: **Only use data available before kickoff.**

```python
def get_active_injuries(team: str, match_date: date) -> List[AbsentPlayer]:
    """
    Returns players who were injured ON the match date.

    Filter: from_date <= match_date AND (end_date IS NULL OR end_date > match_date)
    """
    query = """
        SELECT player_name, injury_type, days_missed
        FROM player_injuries_historical
        WHERE team = %s
          AND from_date <= %s
          AND (end_date IS NULL OR end_date > %s)
    """
```

### 4.3 Example Context Output

```json
{
  "fixture_id": "2025-01-18_Liverpool_Bournemouth",
  "match_date": "2025-01-18",
  "home": {
    "identity": {"name": "Liverpool", "elo": 1985, "elo_delta": +12},
    "form": {
      "last_5": ["W", "W", "D", "W", "W"],
      "xg_for": 2.31,
      "xg_against": 0.87,
      "ppda": 8.2
    },
    "absences": {
      "total_missing": 2,
      "players": [
        {"player_name": "Diogo Jota", "injury_type": "Muscle Injury"},
        {"player_name": "Joe Gomez", "injury_type": "Hamstring Injury"}
      ]
    },
    "lineup": {
      "formation": "4-2-3-1",
      "starters": ["Alisson", "Alexander-Arnold", "Konaté", "van Dijk", ...]
    }
  },
  "odds": {
    "home_win": 1.29,
    "draw": 6.28,
    "away_win": 8.79,
    "source": "football-data-open"
  }
}
```

---

## 5. Narrative Generation

### 5.1 Prompt Structure

```
You are a football analyst. Given the following pre-match context,
generate a structured analysis.

CONTEXT:
{match_context_json}

OUTPUT FORMAT (strict JSON):
{narrative_schema}

RULES:
1. Every claim must reference evidence from the context
2. Confidence must align with odds-implied probability
3. Key factors must cite specific data points
```

### 5.2 Evaluation Loop

Post-match, we compare narrative predictions against actual outcomes:

```python
def evaluate_narrative(narrative: NarrativeOutput, actual_result: str) -> EvaluationResult:
    """
    Scores:
    - Outcome accuracy: Did predicted W/D/L match?
    - Confidence calibration: Was confidence aligned with reality?
    - Key factor relevance: Did cited factors matter?
    """
```

---

## 6. Database Schema

### 6.1 Core Tables

```sql
-- Hub table: all fixtures
CREATE TABLE fixtures (
    id TEXT PRIMARY KEY,                    -- "2025-08-16_Arsenal_Wolves"
    date DATE NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    season TEXT,                            -- "2025-2026"
    matchweek INTEGER,
    home_goals INTEGER,                     -- NULL until played
    away_goals INTEGER,
    result TEXT,                            -- "H", "D", "A"
    home_xg NUMERIC(4,2),
    away_xg NUMERIC(4,2),
    ingested_at TIMESTAMP DEFAULT NOW()
);

-- Satellite: lineups
CREATE TABLE lineups_historical (
    id SERIAL PRIMARY KEY,
    fixture_id TEXT REFERENCES fixtures(id),
    team_name TEXT NOT NULL,
    is_home BOOLEAN,
    formation TEXT,                         -- "4-3-3"
    starters JSONB,                         -- [{player_id, player_name, position}]
    bench JSONB,
    source TEXT DEFAULT 'transfermarkt',
    UNIQUE(fixture_id, team_name)
);

-- Satellite: odds
CREATE TABLE odds_snapshots (
    id SERIAL PRIMARY KEY,
    fixture_id TEXT REFERENCES fixtures(id),
    market_key TEXT NOT NULL,               -- "1X2"
    selection_key TEXT NOT NULL,            -- "HOME", "DRAW", "AWAY"
    odds_decimal NUMERIC(6,3),
    captured_at TIMESTAMP,
    source TEXT,                            -- "football-data-open", "football-data-close"
    data_source TEXT
);

-- Satellite: injuries (team-level, not fixture-level)
CREATE TABLE player_injuries_historical (
    id SERIAL PRIMARY KEY,
    player_id TEXT NOT NULL,
    player_name TEXT,
    team TEXT NOT NULL,
    injury_type TEXT,                       -- "Hamstring Injury"
    from_date DATE,
    end_date DATE,                          -- NULL = ongoing
    days_missed INTEGER,
    games_missed INTEGER,
    data_source TEXT DEFAULT 'transfermarkt',
    ingested_at TIMESTAMP DEFAULT NOW()
);

-- Team Elo ratings (daily)
CREATE TABLE team_elo (
    id SERIAL PRIMARY KEY,
    team TEXT NOT NULL,
    elo_rating NUMERIC(6,1),
    rating_date DATE,
    source TEXT DEFAULT 'clubelo'
);

-- TM match ID mapping
CREATE TABLE tm_match_mapping (
    id SERIAL PRIMARY KEY,
    fixture_id TEXT UNIQUE REFERENCES fixtures(id),
    tm_match_id TEXT NOT NULL,
    home_team TEXT,
    away_team TEXT,
    match_date DATE,
    matchday INTEGER,
    source TEXT DEFAULT 'transfermarkt'
);
```

### 6.2 Design Pattern: Hub-and-Spoke

```
                    ┌─────────────┐
                    │  fixtures   │
                    │   (hub)     │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │  lineups_   │ │   odds_     │ │ tm_match_   │
    │  historical │ │  snapshots  │ │   mapping   │
    └─────────────┘ └─────────────┘ └─────────────┘
```

All satellite tables reference `fixtures.id` as foreign key, enabling easy joins.

---

## 7. Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Database | PostgreSQL 15 |
| Web Scraping | requests, BeautifulSoup, Selenium |
| Fuzzy Matching | rapidfuzz |
| Data Processing | pandas |
| Dashboard | Streamlit |
| LLM | Claude API (Anthropic) |
| Scheduling | Python scripts (cron/manual) |

---

## 8. Current Coverage (Phase 1)

| Data Type | Coverage | Notes |
|-----------|----------|-------|
| Fixtures | 380/380 (100%) | Premier League 2025-26 |
| Lineups | 358/380 (94%) | 22 missing = promoted teams early matches |
| Odds | 220/380 (58%) | Only played matches have odds |
| Injuries | 3,337 records | 481 players across 20 teams |
| TM Mappings | 358/380 (94%) | Maps fixtures to Transfermarkt |
| Elo Ratings | 100% | Daily ratings from ClubElo |
| xG/Stats | 100% (post-match) | From FBRef after match completes |

---

## 9. Known Limitations

1. **FBRef Scraping**: Uses Selenium, can fail on Cloudflare blocks
2. **Transfermarkt Rate Limiting**: 2s delay required to avoid bans
3. **Future Match Odds**: Only available close to kickoff
4. **Suspensions**: Not explicitly tracked (only injuries)
5. **Real-time Data**: No live updates, batch-only

---

## 10. Next Steps (Phase 2)

1. **Evaluator Improvements**: Score narratives against actual outcomes
2. **Confidence Calibration**: Align LLM confidence with market-implied probabilities
3. **Dashboard Enhancements**: Surface evaluation trends
4. **Batch Pipeline**: Automated daily runs with alerting

---

## 11. Running the System

```bash
# 1. Database setup
python scripts/init_db.py

# 2. Backfill injuries (one-time)
python scripts/backfill_injuries.py

# 3. Build TM mappings (one-time)
python scripts/build_tm_mappings.py

# 4. Backfill lineups (one-time)
python scripts/backfill_lineups.py

# 5. Import odds (periodic)
python scripts/download_odds_historical.py

# 6. Run dashboard
streamlit run src/dashboard_v3.py

# 7. Generate context for a match
python -c "
from src.analysis.context_builder_v2 import build_match_context
ctx = build_match_context('2025-01-18_Liverpool_Bournemouth')
print(ctx.to_json())
"
```

---

## 12. Contact

For questions about this architecture, contact the project maintainer.
