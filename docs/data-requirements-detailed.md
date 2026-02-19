# Comprehensive Data Requirements: What We Need & Why

**Date**: 2026-01-19
**Purpose**: Define EXACTLY what data we need and how it's used to beat ChatGPT

---

## Core Philosophy

> "Data without context is noise. Context without impact metrics is useless."

**Key Insight**: It's not enough to know "Salah is injured." We need:
1. **Impact**: How important is Salah to Liverpool's attack? (quantified)
2. **Context**: What does his absence do to team tactics/formation?
3. **Substitution effect**: Who replaces him and what's the quality drop?
4. **Historical patterns**: How has Liverpool performed without Salah?

This applies to **every** data point we collect.

---

## Data Requirements by Category

### 1. Deep Match Statistics

**Purpose**: Understand HOW teams play, not just what the score was

#### 1.1 Possession & Territory Control

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **Possession %** | Base metric, but context-dependent | FBref, WhoScored |
| **Possession in attacking third** | More valuable than overall possession | FBref |
| **Territorial advantage** | Field tilt / average touch position | Understat, FBref |
| **PPDA (Passes Per Defensive Action)** | Pressing intensity (lower = more pressing) | Understat |
| **Defensive line height** | High line = aggressive, low = defensive | FBref (via advanced stats) |

**How We Use It**:
- Predict match flow: High press teams struggle without rest
- Tactical matchups: High press vs possession team
- Fatigue indicators: PPDA increases when tired

#### 1.2 Chance Creation Quality

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **xG (Expected Goals)** | Shot quality | FBref, Understat |
| **xG per shot** | Efficiency of shot selection | Derived from xG |
| **Shots from box vs outside** | Quality vs quantity | FBref, WhoScored |
| **Big chances created** | Clear goal-scoring opportunities | WhoScored |
| **Key passes** | Final pass before shot | WhoScored, FBref |
| **Progressive passes** | Passes that move ball toward goal | FBref |
| **Progressive carries** | Dribbles that advance position | FBref |
| **Touches in penalty area** | Getting into dangerous positions | FBref |
| **xThreat (Expected Threat)** | Value added by ball movement | Requires calculation or specialized source |

**How We Use It**:
- Quality over quantity: Team with fewer shots but higher xG/shot is more clinical
- Identify reliance on specific creators (if one player has most key passes)
- Predict sustainability: High goals but low xG = luck, will regress

#### 1.3 Defensive Solidity

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **xG Against (xGA)** | Quality of chances conceded | FBref, Understat |
| **Shots against from box** | How often defense is breached | FBref |
| **Tackles in defensive third** | Last-ditch defending | FBref |
| **Interceptions** | Proactive defending | FBref |
| **Blocks** | Shot prevention | FBref |
| **Clearances** | Pressure indicator | FBref |
| **Errors leading to shot/goal** | Defensive mistakes | FBref |
| **High turnovers (conceded)** | Vulnerable to press | WhoScored |

**How We Use It**:
- Predict goals conceded: xGA is better than actual goals
- Identify defensive fragility: High errors = exploitable
- Matchup analysis: Weak press resistance vs high pressing opponent

#### 1.4 Set Piece Performance

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **Set piece goals (for/against)** | Can be 20-30% of goals | FBref, WhoScored |
| **Set piece xG** | Quality from set pieces | Understat, FBref |
| **Corners won/conceded** | Set piece opportunity creation | FBref |
| **Aerial duels won %** | Set piece effectiveness | FBref |
| **Direct free kick xG** | Danger from free kicks | Understat |

**How We Use It**:
- Add to match xG prediction: Base + set piece xG
- Identify specialists: Team with tall striker = corner threat
- Matchup analysis: Strong aerial team vs weak aerial defense

#### 1.5 Match Flow & Momentum

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **xG by 15-min intervals** | When goals were likely | Understat (via events) |
| **Shots by half** | First half dominance vs second half | FBref |
| **Possession by half** | Tactical adjustments | WhoScored |
| **Substitution impact** | Quality of bench | FBref (via events) |
| **Goals scored in last 15 min** | Fitness/mental strength | FBref (via events) |

**How We Use It**:
- Predict late goals: Teams that score late have mental edge
- Identify fitness issues: Team fading in second half
- Bench strength: Impact subs = squad depth

---

### 2. Player Impact Metrics

**Purpose**: Quantify EXACTLY how much each player matters

#### 2.1 Player Ratings (Baseline Impact)

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **WhoScored rating** | Event-based performance | WhoScored |
| **Sofascore rating** | Alternative algorithm | Sofascore |
| **Average rating over season** | Player baseline quality | WhoScored, Sofascore |
| **Rating vs opponents of similar quality** | Big game performance | Derived |

**How We Use It**:
- Starting XI strength: Average rating of starting 11
- Replacement quality: Starter rating - Backup rating = drop-off
- Form: Recent 5-match avg rating vs season avg

**CRITICAL**: Ratings alone are not enough. Need to understand WHY a player is rated highly.

#### 2.2 Player Offensive Impact

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **Goals per 90 minutes** | Scoring rate | FBref |
| **xG per 90** | Shot quality | FBref, Understat |
| **xG overperformance** | Finishing ability (xG - actual) | Derived |
| **Assists per 90** | Creativity | FBref |
| **xA (Expected Assists) per 90** | Chance creation quality | FBref |
| **Key passes per 90** | Final ball frequency | WhoScored, FBref |
| **Shot-creating actions per 90** | Involvement in chance creation | FBref |
| **Goal-creating actions per 90** | Direct goal involvement | FBref |
| **Progressive carries per 90** | Ball advancement | FBref |
| **Progressive passes per 90** | Forward passing | FBref |
| **Successful dribbles per 90** | 1v1 ability | FBref |
| **Touches in penalty area per 90** | Positioning | FBref |

**How We Use It**:
```python
# Example: Quantify Salah's impact
salah_missing = {
    'xg_per_90_loss': 0.65,  # Salah: 0.75, Backup: 0.10
    'xa_per_90_loss': 0.30,  # Salah: 0.35, Backup: 0.05
    'key_passes_loss': 1.8,  # Salah: 2.1, Backup: 0.3
    'progressive_carries_loss': 2.5
}

# Total expected goal impact: 0.65 xG + 0.30 xA = ~0.95 goals per match
# Liverpool's xG drops from 2.1 to 1.15 without Salah
```

#### 2.3 Player Defensive Impact

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **Tackles per 90** | Defensive engagement | FBref |
| **Interceptions per 90** | Reading of game | FBref |
| **Blocks per 90** | Shot prevention | FBref |
| **Clearances per 90** | Defensive actions | FBref |
| **Aerial duels won %** | Physical dominance | FBref |
| **Pressures per 90** | Pressing intensity | FBref |
| **Successful pressure %** | Press efficiency | FBref |
| **Tackles + interceptions in def 3rd** | Last-line defending | FBref |
| **Errors leading to shot** | Mistakes | FBref |

**How We Use It**:
- Quantify defensive midfielder impact (e.g., Rodri for Man City)
- Identify defensive weaknesses when backup plays
- Predict goals conceded increase

#### 2.4 Player Positional Impact

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **Position played** | Role in team | FBref |
| **Minutes played** | Match fitness | FBref |
| **Passing accuracy by zone** | Distribution quality | FBref |
| **Passing network centrality** | Team hub | Requires network analysis |
| **Average position (x, y coordinates)** | Tactical role | WhoScored (if available) |

**How We Use It**:
- Understand tactical system dependency on specific players
- Identify irreplaceable players (high centrality in passing network)

#### 2.5 Player Market Value (Proxy for Quality)

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **Transfermarkt market value** | Industry consensus on quality | Transfermarkt |
| **Market value percentile in squad** | Relative importance | Derived |
| **Market value of starting XI** | Team quality metric | Derived |
| **Value drop from starter to backup** | Quality gap | Derived |

**How We Use It**:
```python
# Example: Starting XI value as quality proxy
liverpool_xi_value = 850_000_000  # €850M
arsenal_xi_value = 920_000_000    # €920M

# Arsenal has 8% higher squad value = slight quality edge
# But needs context: Liverpool may have better form/tactics
```

---

### 3. Player Availability & Injury Impact

**Purpose**: Time-travel correctness - know who was actually available at match time

#### 3.1 Injury Data (Essential)

| Data Point | Why It Matters | Source |
|------------|---------------|--------|
| **Player name** | Identity | All sources |
| **Injury type** | Severity indicator | Transfermarkt, API-Football |
| **Body part injured** | Recurrence risk | Transfermarkt |
| **Injury date** | Timeline | Transfermarkt |
| **Expected return date** | Availability forecast | Transfermarkt, API-Football |
| **Actual return date** | True recovery time | Derived from lineups |
| **Matches missed** | Impact duration | Derived |
| **Recurrent injury flag** | Chronic issue | Derived |

#### 3.2 Suspension Data

| Data Point | Why It Matters | Source |
|------------|---------------|--------|
| **Yellow cards accumulated** | Suspension risk | FBref |
| **Red cards** | Immediate suspension | FBref |
| **Suspension length** | Matches missed | FBref, API-Football |
| **Suspension expiry date** | Return date | Derived |

#### 3.3 Availability Status at Match Time

```python
# For each match, we need:
match_availability = {
    'fixture_id': 12345,
    'date': '2023-11-10',
    'home_team': 'Liverpool',

    # Missing players
    'home_missing': [
        {
            'player_id': 123,
            'player_name': 'Mohamed Salah',
            'position': 'RW',
            'reason': 'Hamstring injury',
            'market_value': 80_000_000,
            # IMPACT METRICS
            'avg_rating_season': 7.8,
            'xg_per_90': 0.75,
            'xa_per_90': 0.35,
            'key_passes_per_90': 2.1,
            # REPLACEMENT
            'replacement': 'Harvey Elliott',
            'replacement_rating': 6.9,
            'replacement_xg_per_90': 0.15,
            'replacement_xa_per_90': 0.20,
            # CALCULATED IMPACT
            'xg_loss_per_90': 0.60,
            'xa_loss_per_90': 0.15,
            'total_goal_impact': -0.75  # Expected goals lost
        },
        {
            'player_id': 124,
            'player_name': 'Virgil van Dijk',
            'position': 'CB',
            'reason': 'Suspension (2 yellows)',
            # ... impact metrics ...
            'total_goal_impact': +0.40  # Expected goals conceded (defensive loss)
        }
    ],

    # Net impact
    'total_xg_impact': -0.75,  # Attack weaker
    'total_xga_impact': +0.40,  # Defense weaker
    'net_goal_swing': -1.15    # Expected goal differential hit
}
```

**How We Use It**:
1. Adjust team xG: Liverpool base xG 2.1 → 1.35 (without Salah)
2. Adjust team xGA: Liverpool base xGA 0.9 → 1.3 (without Van Dijk)
3. Update match prediction: Liverpool expected goals from 2.1 to 1.35
4. Confidence adjustment: More uncertainty without key players

---

### 4. Lineup & Formation Data

**Purpose**: Understand tactical setup and identify weak links

#### 4.1 Lineup Data (Historical & Predicted)

| Data Point | Why It Matters | Source |
|------------|---------------|--------|
| **Starting XI (both teams)** | Actual team on pitch | API-Football, FBref |
| **Formation** | Tactical system | API-Football, FBref |
| **Player positions in formation** | Specific roles | API-Football |
| **Bench players** | Substitution options | API-Football |
| **Captain** | Leadership | API-Football |

#### 4.2 Formation Analysis

| Metric | Why It Matters | How We Calculate |
|--------|---------------|------------------|
| **Formation matchup** | Tactical advantage | Compare formations |
| **Formation historical performance** | Track record | Aggregate by formation |
| **Formation vs specific opponent** | H2H tactics | Historical analysis |
| **Formation flexibility** | In-game adaptability | Count formation changes |

**Example**:
```python
# Liverpool 4-3-3 vs Arsenal 4-2-3-1
matchup_analysis = {
    'formation_home': '4-3-3',
    'formation_away': '4-2-3-1',

    # Historical performance
    'home_formation_win_rate': 0.65,
    'away_formation_win_rate': 0.58,

    # Matchup analysis
    'matchup_advantage': 'Neutral',  # 4-3-3 vs 4-2-3-1 is even
    'midfield_battle': 'Home edge',  # 3 CMs vs 2 DMs + 1 CAM
    'wing_overloads': 'Home edge',   # 4-3-3 has natural width
}
```

#### 4.3 Starting XI Quality Metrics

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **Average rating of XI** | Team quality | Avg(WhoScored ratings) |
| **Total market value of XI** | Squad value | Sum(Transfermarkt values) |
| **Total xG per 90 of XI** | Offensive firepower | Sum(player xG/90) |
| **Total xG against per 90 of XI** | Defensive solidity | Sum(defender metrics) |
| **Experience (avg caps/apps)** | Big game readiness | FBref |
| **Bench strength** | Substitution impact | Avg(bench player ratings) |

**Example**:
```python
liverpool_xi_strength = {
    'avg_rating': 7.45,  # Average WhoScored rating
    'market_value': 850_000_000,
    'total_xg_per_90': 2.1,  # Sum of all attackers' xG/90
    'total_xa_per_90': 1.8,
    'defensive_quality': 0.9,  # Expected xGA (lower is better)
    'experience_avg_apps': 185,  # Average career apps
    'bench_avg_rating': 6.8
}

# Compare to opponent to get match quality differential
```

---

### 5. Team Form & Scheduling Context

**Purpose**: Capture recent performance and fatigue factors

#### 5.1 Form Metrics

| Metric | Why It Matters | Lookback Window | Source |
|--------|---------------|-----------------|--------|
| **Points from last N matches** | Recent results | 5 matches | FBref |
| **Goals scored last N** | Attacking form | 5 matches | FBref |
| **Goals conceded last N** | Defensive form | 5 matches | FBref |
| **xG difference last N** | True form (luck-adjusted) | 5 matches | FBref, Understat |
| **Win streak** | Momentum | Current | FBref |
| **Clean sheets in last N** | Defensive confidence | 5 matches | FBref |
| **Failed to score in last N** | Attacking struggles | 5 matches | FBref |

**Example**:
```python
liverpool_form = {
    'last_5_points': 13,  # W3 D4 L0 (out of 15 possible)
    'last_5_gf': 11,
    'last_5_ga': 3,
    'last_5_xg_diff': +7.2,  # (xG 10.5) - (xGA 3.3)
    'win_streak': 3,
    'clean_sheets': 3,
    'failed_to_score': 0
}

# Analysis: Excellent form, overperforming xG slightly
```

#### 5.2 Schedule & Rest

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **Days since last match** | Recovery time | Derived from fixtures |
| **Matches in last 7 days** | Fixture congestion | Derived |
| **Matches in last 14 days** | Cumulative fatigue | Derived |
| **Matches in next 7 days** | Rotation likelihood | Derived from fixtures |
| **Days until next match** | Recovery window | Derived |
| **Competition (league/cup)** | Priority level | Fixtures data |
| **Away travel distance** | Travel fatigue | Requires geo calculation |

**Example**:
```python
liverpool_schedule_context = {
    'rest_days': 3,  # 3 days since last match
    'matches_last_7d': 2,  # Played midweek + weekend
    'matches_last_14d': 4,  # Congested schedule
    'matches_next_7d': 2,  # Another busy week ahead
    'days_to_next_match': 3,
    'upcoming_competition': 'Champions League',  # Big match after this
    'travel_km_last_match': 450,  # Flew to Newcastle
    'rotation_risk': 'High'  # Likely to rotate squad
}

# Analysis: Fatigue + rotation risk = weakened team likely
```

#### 5.3 Venue Context

| Metric | Why It Matters | Source |
|--------|---------------|--------|
| **Home/Away** | Home advantage | Fixtures |
| **Home win rate** | Home strength | Historical data |
| **Away win rate** | Travel performance | Historical data |
| **Venue (stadium name)** | Specific stadium | Fixtures |
| **Attendance** | Crowd impact | Match stats (if available) |

**Example**:
```python
home_advantage = {
    'venue': 'Anfield',
    'liverpool_home_win_rate': 0.75,
    'liverpool_home_avg_goals': 2.4,
    'liverpool_home_avg_conceded': 0.8,
    'anfield_atmosphere_rating': 9.5,  # Qualitative
    'opponent_away_win_rate': 0.35
}

# Analysis: Significant home advantage for Liverpool
```

---

### 6. Odds & Market Intelligence

**Purpose**: Capture market wisdom and identify betting value

#### 6.1 Odds Time-Series (CRITICAL)

| Timestamp | Why It Matters | Bookmakers Needed |
|-----------|---------------|-------------------|
| **Opening odds** | Initial market view | Pinnacle, Bet365, WilliamHill |
| **72h before** | Early sharp money | Pinnacle |
| **48h before** | Midweek adjustment | Pinnacle, Bet365 |
| **24h before** | Team news starts leaking | All |
| **4h before** | POST team news announcement | All (CRITICAL) |
| **1h before** | POST confirmed lineups | All |
| **Closing (5min before)** | Final market position | All (especially Pinnacle) |

**Data Structure**:
```python
odds_timeline = {
    'fixture_id': 12345,
    'snapshots': [
        {
            'timestamp': '2023-11-07T15:00:00Z',  # 3 days before
            'label': 'opening',
            'seconds_before_kickoff': 259200,
            'bookmakers': {
                'pinnacle': {'home': 2.08, 'draw': 3.45, 'away': 3.70},
                'bet365': {'home': 2.00, 'draw': 3.40, 'away': 3.80},
                'williamhill': {'home': 2.05, 'draw': 3.50, 'away': 3.75}
            }
        },
        # ... more snapshots ...
        {
            'timestamp': '2023-11-10T11:00:00Z',  # 4h before
            'label': '4h_before',
            'seconds_before_kickoff': 14400,
            'bookmakers': {
                'pinnacle': {'home': 1.91, 'draw': 3.52, 'away': 4.10},
                # Odds dropped after Salah ruled out
            }
        },
        {
            'timestamp': '2023-11-10T14:55:00Z',  # Closing
            'label': 'closing',
            'seconds_before_kickoff': 300,
            'bookmakers': {
                'pinnacle': {'home': 1.85, 'draw': 3.68, 'away': 4.35},
            }
        }
    ]
}
```

#### 6.2 Odds Movement Analysis

| Metric | Why It Matters | How We Calculate |
|--------|---------------|------------------|
| **Total line movement %** | Market direction | (closing - opening) / opening |
| **Movement at 4h mark** | Reaction to team news | Compare before/after |
| **Sharp vs public movement** | Who's betting | Pinnacle vs recreational books |
| **Steam move detection** | Synchronized sharp action | Rapid movement across books |
| **Reverse line movement** | Contrarian sharp action | Line moves opposite to bet % |

**Example**:
```python
odds_movement_analysis = {
    'opening_home': 2.08,
    'closing_home': 1.85,
    'total_movement_pct': -11.1,  # Line shortened (home backed)

    # Timeline analysis
    '4h_before_home': 1.91,
    'movement_before_team_news': -8.2,  # Opening to 4h before
    'movement_after_team_news': -3.1,   # 4h before to close

    # Market efficiency
    'pinnacle_close': 1.85,
    'market_avg_close': 1.80,  # Recreational books lower
    'pinnacle_premium': 0.05,  # Pinnacle has sharper line

    # Signals
    'sharp_money_direction': 'Home',
    'public_money_direction': 'Away',  # Reverse line movement
    'steam_detected': True,
    'contrarian_indicator': True
}
```

#### 6.3 Closing Line Value (CLV)

| Metric | Why It Matters |
|--------|---------------|
| **Pinnacle closing odds** | Gold standard for true probability |
| **Your model odds** | Your prediction |
| **CLV** | Model odds vs Pinnacle close |

**Formula**:
```python
# Example: You predict Liverpool win at 2.00 (50% implied prob)
# Pinnacle closes at 1.85 (54% implied prob)

your_implied_prob = 1 / 2.00  # 0.50 = 50%
pinnacle_implied_prob = 1 / 1.85  # 0.541 = 54.1%

clv = your_implied_prob - pinnacle_implied_prob  # -0.041 = -4.1%

# Negative CLV = Your model is worse than market
# Positive CLV = Your model found value (beat the market)

# Goal: Achieve positive CLV consistently (>1% is good)
```

---

### 7. Historical Match Outcomes (Labels)

**Purpose**: Training labels for ML and calibration

#### 7.1 Match Results

| Data Point | Why It Matters | Source |
|------------|---------------|--------|
| **Final score** | Match outcome | All sources |
| **Result (H/D/A)** | Classification label | Derived |
| **Halftime score** | Early performance | FBref |
| **Goals by period** | Timing of goals | FBref (via events) |

#### 7.2 Match Events

| Data Point | Why It Matters | Source |
|------------|---------------|--------|
| **Goals (scorer, minute, type)** | Goal context | FBref, WhoScored |
| **Assists** | Chance creation | FBref |
| **Red cards** | Game-changing events | FBref |
| **Penalties awarded/scored** | xG adjustment needed | FBref |
| **Own goals** | Random variance | FBref |
| **VAR interventions** | Controversial decisions | WhoScored (if available) |

#### 7.3 Advanced Match Stats

| Data Point | Why It Matters | Source |
|------------|---------------|--------|
| **Actual xG (both teams)** | Expected outcome | FBref, Understat |
| **Actual shots** | Volume | FBref |
| **Shots on target** | Quality | FBref |
| **Possession %** | Control | FBref |
| **Pass completion %** | Execution | FBref |

**How We Use It**:
```python
# Training example
training_label = {
    # Prediction features (before match)
    'predicted_home_xg': 1.35,
    'predicted_away_xg': 1.50,
    'predicted_prob_home': 0.35,
    'predicted_prob_draw': 0.28,
    'predicted_prob_away': 0.37,
    'model_odds_home': 2.86,  # 1 / 0.35

    # Market (before match)
    'pinnacle_close_home': 1.85,
    'pinnacle_implied_prob': 0.541,

    # Actual outcome (after match)
    'actual_home_score': 1,
    'actual_away_score': 2,
    'actual_result': 'A',  # Away win
    'actual_home_xg': 1.2,
    'actual_away_xg': 1.8,

    # Evaluation
    'prediction_correct': False,
    'xg_prediction_error': abs(1.35 - 1.2),  # 0.15 (good)
    'market_beat': False,  # Predicted home less likely than market
    'clv': -0.191  # -19.1% CLV (model way off)
}

# Use this to:
# 1. Train models
# 2. Calibrate probabilities
# 3. Measure prediction accuracy
# 4. Evaluate market efficiency
```

---

## Free Scraping Strategy for Historical Backfill

### Sources That Are Scrapable for Free

#### 1. FBref (StatsBomb Data) - BEST FREE SOURCE

**What's Available**:
- ✓ Match results going back to 2017+ (some leagues to 1888!)
- ✓ Detailed match statistics (xG, shots, possession, passing, etc.)
- ✓ Player statistics (season totals and per-90 metrics)
- ✓ Squad data and lineups
- ✓ ALL the metrics we need for deep match stats

**How to Scrape**:
- Library: `soccerdata` (Python) - already in your requirements.txt!
- Alternative: `worldfootballR` (R package)
- Custom: BeautifulSoup + requests (slower, but controllable)

**Rate Limiting**:
- ⚠️ FBref will block if you scrape too aggressively
- Recommended: 3-5 second delay between requests
- Use caching (soccerdata does this automatically)

**Example**:
```python
import soccerdata as sd
import time

# Despite earlier API errors, soccerdata can still scrape FBref HTML
# Just need to handle rate limiting properly

fbref = sd.FBref(leagues='ENG-Premier League', seasons=['2021', '2022', '2023', '2024'])

# This will scrape over time with built-in delays
try:
    schedule = fbref.read_schedule()  # Match results
    team_stats = fbref.read_team_season_stats()  # Team aggregates
    player_stats = fbref.read_player_season_stats()  # Player stats

    # Get specific match stats
    for fixture in schedule.itertuples():
        # Can get detailed match stats per fixture
        time.sleep(3)  # Rate limiting
except Exception as e:
    print(f"Scraping error: {e}")
```

#### 2. Transfermarkt - Player Values & Injuries

**What's Available**:
- ✓ Player market values (historical)
- ✓ Injury history (type, dates, matches missed)
- ✓ Transfer history
- ✓ Player profiles

**How to Scrape**:
- Library: `worldfootballR` (R) - best option
- Pre-scraped dataset: https://github.com/salimt/football-datasets (93k+ players!)
- Custom scraper: Possible but complex (dynamic pages)

**Pre-Built Dataset Option**:
```bash
# Use the salimt/football-datasets repo
git clone https://github.com/salimt/football-datasets.git

# Contains:
# - player_market_values/
# - player_injury_histories/
# - player_transfer_histories/
# - player_profiles/

# This saves you from scraping Transfermarkt yourself!
```

#### 3. Understat - xG Data

**What's Available**:
- ✓ Match-level xG (both teams)
- ✓ Shot-level data (xG per shot, location, situation)
- ✓ Player xG and xA
- ✓ PPDA and deep completions

**Status**:
- ❌ Currently broken in soccerdata (website changed)
- ✓ BUT can scrape directly via their JSON endpoints

**Alternative Approach**:
```python
import requests
import json

def scrape_understat_direct(league='EPL', season='2023'):
    """
    Understat exposes JSON data that can be scraped.
    Bypasses the soccerdata library issues.
    """
    # Their data is in JSON format embedded in JavaScript
    # Can extract and parse directly

    url = f"https://understat.com/league/{league}/{season}"
    response = requests.get(url)

    # Extract JSON data from page (requires parsing)
    # This is doable but requires custom code
    pass
```

**Or**: Just use FBref xG data (powered by StatsBomb, equally good)

#### 4. WhoScored - Event Data & Ratings

**Status**:
- ⚠️ Requires Selenium (anti-scraping measures)
- ⚠️ More complex to scrape reliably
- ⚠️ May break frequently

**Alternative**:
- Use Sofascore instead (easier to scrape)
- Or use FBref player stats as proxy for ratings

#### 5. Football-Data.co.uk - Historical Odds

**What's Available**:
- ✓ Historical match results with odds
- ✓ Multiple bookmakers (Bet365, Pinnacle, etc.)
- ✓ CSV files downloadable directly!
- ✓ Goes back to 2000 for major leagues

**How to Get It**:
```python
import pandas as pd

# Direct CSV download (NO SCRAPING NEEDED!)
url = "https://www.football-data.co.uk/mmz4281/2324/E0.csv"  # EPL 2023-24
df = pd.read_csv(url)

# Columns include:
# - Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR
# - B365H, B365D, B365A (Bet365 odds)
# - PSH, PSD, PSA (Pinnacle odds)
# - Many more bookmakers

# For multiple seasons:
seasons = ['2122', '2223', '2324', '2425']
base_url = "https://www.football-data.co.uk/mmz4281/{}/E0.csv"

all_data = []
for season in seasons:
    df = pd.read_csv(base_url.format(season))
    all_data.append(df)

historical_odds = pd.concat(all_data, ignore_index=True)
```

**Limitation**: Only closing odds (not timestamps), but it's FREE and goes back 20+ years!

---

## Recommended Free Scraping Architecture

### Phase 1: Core Historical Data (FREE)

```python
# 1. Match Results & Team Stats (FBref)
import soccerdata as sd

fbref = sd.FBref(leagues='ENG-Premier League', seasons=['2021', '2022', '2023', '2024'])

# Scrape with rate limiting
fixtures = fbref.read_schedule()  # All matches
team_stats = fbref.read_team_season_stats()  # Season aggregates
team_match_stats = fbref.read_team_match_stats()  # Per-match stats
player_stats = fbref.read_player_season_stats()  # All players

# Store in database
store_to_db(fixtures, 'fixtures_historical')
store_to_db(team_match_stats, 'team_match_stats')
store_to_db(player_stats, 'player_stats')
```

```python
# 2. Player Values & Injuries (Transfermarkt dataset)
import git
import pandas as pd

# Clone the pre-scraped dataset
repo_url = "https://github.com/salimt/football-datasets.git"
git.Repo.clone_from(repo_url, './football-datasets')

# Load player data
injuries = pd.read_csv('./football-datasets/player_injury_histories.csv')
market_values = pd.read_csv('./football-datasets/player_market_values.csv')

# Store in database
store_to_db(injuries, 'player_injuries')
store_to_db(market_values, 'player_market_values')
```

```python
# 3. Historical Odds (Football-Data.co.uk CSVs)
import pandas as pd

def scrape_historical_odds(league_code='E0', seasons=['2122', '2223', '2324']):
    """
    Download CSV files directly from Football-Data.co.uk
    """
    base_url = f"https://www.football-data.co.uk/mmz4281/{{}}/{league_code}.csv"

    all_odds = []
    for season in seasons:
        url = base_url.format(season)
        df = pd.read_csv(url)
        df['season'] = season
        all_odds.append(df)

    return pd.concat(all_odds, ignore_index=True)

odds_data = scrape_historical_odds(seasons=['2122', '2223', '2324', '2425'])
store_to_db(odds_data, 'historical_odds')
```

### Phase 2: Derived Features (Calculate Ourselves)

```python
# After collecting raw data, calculate:

# 1. Rest days (from fixtures)
def calculate_rest_days(team_id, match_date):
    previous_match = get_previous_match(team_id, before_date=match_date)
    return (match_date - previous_match['date']).days

# 2. Form metrics (from results)
def calculate_form(team_id, match_date, num_matches=5):
    recent = get_recent_matches(team_id, before_date=match_date, limit=num_matches)
    return {
        'points': sum_points(recent),
        'goals_for': sum(recent['goals_scored']),
        'goals_against': sum(recent['goals_conceded'])
    }

# 3. Player impact (from player stats)
def calculate_player_impact(player_id, season):
    stats = get_player_stats(player_id, season)

    return {
        'xg_per_90': stats['xg'] / (stats['minutes'] / 90),
        'xa_per_90': stats['xa'] / (stats['minutes'] / 90),
        'key_passes_per_90': stats['key_passes'] / (stats['minutes'] / 90),
        'rating_avg': stats['avg_rating']
    }

# 4. Team strength (from player stats + market values)
def calculate_team_strength(team_id, match_date, lineup):
    """
    For a given lineup, calculate team strength metrics
    """
    players = get_players_in_lineup(lineup)

    total_market_value = sum(p['market_value'] for p in players)
    avg_rating = sum(p['avg_rating'] for p in players) / len(players)
    total_xg_per_90 = sum(p['xg_per_90'] for p in players if p['position'] in ['FW', 'MF'])

    return {
        'market_value': total_market_value,
        'avg_rating': avg_rating,
        'offensive_strength': total_xg_per_90
    }
```

### Cost: FREE (Just Time & Storage)

**Time Required**:
- FBref scraping: 2-3 days (with rate limiting)
- Transfermarkt dataset: 30 minutes (download + process)
- Football-Data.co.uk odds: 10 minutes (direct CSV download)
- Feature engineering: 1-2 days (write scripts)

**Total**: ~1 week of development

**Storage**: ~500MB-1GB for 4 seasons

**Ongoing Cost**: $0/month

---

## Hybrid Approach: Free Backfill + Paid Real-Time

### Recommendation

**Historical Data (one-time backfill)**: Use FREE scraping
- FBref: Match stats, player stats, lineups
- Transfermarkt: Player values, injuries
- Football-Data.co.uk: Historical odds (closing)

**Production Data (ongoing)**: Use PAID APIs
- API-Football ($19/month): Real-time lineups, injuries, fixtures
- The Odds API ($50/month): Live odds with timestamps

**Why This Works**:
1. **Backfill is expensive on paid APIs** (consume lots of quota)
2. **Backfill can be slow** (we have time, can scrape over days)
3. **Historical data doesn't change** (scrape once, use forever)
4. **Real-time data needs reliability** (can't afford scraper breaking during live predictions)

**Total Cost**:
- Backfill: FREE (just time)
- Production: $70/month

---

## Next Steps

1. **Define Priority Metrics** (This Week):
   - Which metrics are MUST-HAVE vs nice-to-have?
   - Which metrics have biggest impact on predictions?

2. **Build Free Scraping Pipeline** (Week 1-2):
   ```bash
   # Create scraping scripts
   scripts/scrape_fbref_historical.py
   scripts/download_transfermarkt_dataset.py
   scripts/download_odds_historical.py
   scripts/derive_features.py
   ```

3. **Test Data Quality** (Week 2):
   - Validate completeness
   - Check for missing data
   - Compare to paid API samples

4. **Make Decision** (Week 3):
   - Is free scraping good enough for backfill?
   - Do we need paid APIs for historical data?
   - Or hybrid approach?

---

**Bottom Line**: We CAN get 80-90% of needed historical data for FREE via scraping. The remaining 10-20% (real-time odds timestamps, predicted lineups) requires paid APIs, but only for production, not historical backfill.

Let's start with free scraping for historical data, then add paid APIs for real-time production later.

---

## Sources

- [soccerdata GitHub](https://github.com/probberechts/soccerdata)
- [FBref Football Statistics](https://fbref.com/en/)
- [WhoScored Statistics](https://www.whoscored.com/)
- [worldfootballR Documentation](https://jaseziv.github.io/worldfootballR/articles/extract-fbref-data.html)
- [football-datasets GitHub (93k players)](https://github.com/salimt/football-datasets)
- [Football-Data.co.uk Free CSVs](https://www.football-data.co.uk/)
- [Sky Sports - Advanced Stats Explained](https://www.skysports.com/football/news/11095/12829539/expected-goals-expected-assists-pressures-carries-high-turnovers-and-more-advanced-stats-explained)
- [FBref xG Model Explained](https://fbref.com/en/expected-goals-model-explained/)
