# Clarity Engine - Agent Tools

## Overview

These tools provide the interface between the reasoning agent and the knowledge graph.
Each tool abstracts database queries and returns structured, interpretable data.

**Critical Rule:** All tools that access temporal data MUST accept `round_number` parameter and filter by it. This prevents data leakage when analyzing past matches.

## 14 Tools (Implemented)

### Team Tools (`src/tools/team_tools.py`)

#### `get_team_state(team, round_number=None)`
Full 8-layer KG snapshot for a team at a specific round.

**Layers:**
1. Identity - team_id, team_name
2. Position - league position, points, W/D/L
3. Form - last 5 results, form string, xG trends
4. Style - formation, avg possession
5. Attack - goals, xG, shots, big chances
6. Defense - goals against, xGA
7. Home/Away - venue splits
8. Trajectory - improving/stable/declining

**Example:**
```python
result = get_team_state("Arsenal")
# Returns: position, form visual, trajectory, xG insights
```

#### `get_team_form(team, matches=5, round_number=None)`
Detailed form analysis with xG performance context.

**Returns:**
- Form string and points
- Goals scored/conceded
- xG over/underperformance (luck factor)
- Trajectory trend

#### `get_team_profile(team, round_number=None)`
Playing style profile answering "How does this team play?"

**Classifies:**
- Possession style (dominant → deep defensive)
- Attack rating (elite → low output)
- Defense rating (elite → leaky)
- Home/away character

---

### Player Tools (`src/tools/player_tools.py`)

#### `get_key_players(team, round_number=None, top_n=5)`
Identifies most influential players by goals, assists, rating, minutes.

**Returns:**
- Top scorers, assist leaders
- Best rated players
- In-form players (rating >= 7.0 last 5)

#### `get_injuries_impact(team, round_number=None)`
Analyzes impact of missing players (heuristic based on playing time patterns).

**Detects:**
- Players with reduced minutes
- Regulars missing from recent matches
- Returning players
- Missing goal contribution %

---

### Match Tools (`src/tools/match_tools.py`)

#### `get_last_match_summary(team, round_number=None)`
Detailed breakdown of most recent match.

**Includes:**
- Result and scoreline
- Top performers with ratings
- Goal scorers

#### `get_h2h(team1, team2, limit=10)`
Historical head-to-head record between two teams.

**Analyzes:**
- Win/draw/loss record
- Goals scored/conceded
- Home/away splits
- Recent form in fixture

#### `get_matchup_analysis(team1, team2, venue_for_team1="home", round_number=None)`
Style clash prediction comparing how two teams match up.

**Compares:**
- Possession tendencies
- Attack vs defense metrics
- Form comparison
- Key advantages for each side
- Verdict (who's favored)

---

### Context Tools (`src/tools/context_tools.py`)

#### `get_psychological_state(team, round_number=None)`
Infers mental/psychological factors from data patterns.

**Factors:**
- Position pressure (CL race, relegation)
- Form trajectory
- Recent results pattern (streaks)
- xG luck factor

**Outputs:**
- Pressure score (0-100)
- Confidence score (0-100)
- Mindset classification

#### `search_news(team, query=None, days=7)` ⚠️ PLACEHOLDER
Recent news/narratives about a team.

**Status:** Needs BetHub news aggregator integration.

#### `get_odds(team1, team2, market="1x2")` ⚠️ PLACEHOLDER
Market consensus from betting odds.

**Status:** Needs API-Football integration.

#### `build_game_state_tree(team1, team2, venue_for_team1="home", round_number=None)`
Scenario builder for match flow prediction.

**Scenarios:**
- Kickoff state
- If team1 scores first
- If team2 scores first
- Tight at 60'
- Late drama

**Outputs:**
- Expected game flow
- How teams respond to different states
- Key moments to watch

---

## Usage

```python
from src.tools import (
    get_team_state, get_team_form, get_team_profile,
    get_key_players, get_injuries_impact,
    get_last_match_summary, get_h2h, get_matchup_analysis,
    get_psychological_state, search_news, get_odds, build_game_state_tree
)

# All tools return ToolResponse:
# - success: bool
# - data: Dict[str, Any]  
# - summary: str (human-readable)
# - error: Optional[str]

result = get_team_state("Arsenal")
if result.success:
    print(result.summary)
    print(result.data["position"])
```

## Response Format

All tools return a `ToolResponse` object:

```python
@dataclass
class ToolResponse:
    success: bool
    data: Dict[str, Any] = {}
    summary: str = ""  # Human-readable summary
    error: Optional[str] = None
```

## Team Resolution

Teams can be specified by:
- **Name:** "Arsenal", "Manchester City"
- **Partial name:** "City", "Man United"
- **ID:** 8456 (external APIs team ID)

## Data Sources

- **Primary:** external APIs (via `external data_matches`, `external data_player_performances`)
- **Aggregated:** `team_states`, `player_states` (per-round snapshots)
- **Secondary:** API-Football (odds, standings) - pending integration

## Next Steps

1. Integrate `search_news` with BetHub aggregator
2. Integrate `get_odds` with API-Football
3. Add per-match xG extraction from JSON stats
4. Build agent reasoning loop using these tools
