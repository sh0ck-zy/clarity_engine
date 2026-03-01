# Sports Intelligence Ontology

> Definição completa do Knowledge Graph para análise de futebol.

---

## 1. ENTIDADES (Nodes)

### 1.1 Competition
```yaml
Competition:
  description: "Uma competição/liga"
  properties:
    id: string (PK)           # "premier-league-25-26"
    name: string              # "Premier League"
    country: string           # "England"
    tier: int                 # 1
    season: string            # "2025/2026"
    start_date: date
    end_date: date
    total_rounds: int         # 38
    total_teams: int          # 20
    
  examples:
    - { id: "pl-25-26", name: "Premier League", country: "England", tier: 1, season: "2025/2026" }
```

### 1.2 Team
```yaml
Team:
  description: "Um clube de futebol"
  properties:
    id: string (PK)           # "liverpool"
    fotmob_id: int            # ID do FotMob
    name: string              # "Liverpool"
    short_name: string        # "LIV"
    country: string           # "England"
    founded: int              # 1892
    stadium: string           # "Anfield"
    stadium_capacity: int     # 61276
    primary_color: string     # "#C8102E"
    logo_url: string
    
  examples:
    - { id: "liverpool", name: "Liverpool", short_name: "LIV", fotmob_id: 8650 }
    - { id: "arsenal", name: "Arsenal", short_name: "ARS", fotmob_id: 9825 }
```

### 1.3 Player
```yaml
Player:
  description: "Um jogador"
  properties:
    id: string (PK)           # "mohamed-salah"
    fotmob_id: int            # ID do FotMob
    name: string              # "Mohamed Salah"
    short_name: string        # "M. Salah"
    nationality: string       # "Egypt"
    birth_date: date
    age: int                  # computed
    height_cm: int
    preferred_foot: string    # "left"
    primary_position: string  # "RW"
    secondary_positions: [string]
    photo_url: string
    
  examples:
    - { id: "mohamed-salah", name: "Mohamed Salah", primary_position: "RW" }
```

### 1.4 Round
```yaml
Round:
  description: "Uma jornada da competição"
  properties:
    id: string (PK)           # "pl-25-26-r26"
    competition_id: string (FK)
    number: int               # 26
    name: string              # "Matchday 26"
    start_date: date
    end_date: date
    status: enum              # "completed", "in_progress", "scheduled"
    
  examples:
    - { id: "pl-25-26-r26", competition_id: "pl-25-26", number: 26 }
```

### 1.5 Match
```yaml
Match:
  description: "Um jogo"
  properties:
    id: string (PK)           # "pl-25-26-r26-liv-ars"
    fotmob_id: int            # ID do FotMob
    competition_id: string (FK)
    round_id: string (FK)
    home_team_id: string (FK)
    away_team_id: string (FK)
    
    # Temporal
    date: date
    kickoff_time: timestamp
    
    # Venue
    venue: string
    attendance: int
    referee: string
    
    # Result
    status: enum              # "scheduled", "live", "finished", "postponed"
    home_score: int
    away_score: int
    ht_home_score: int
    ht_away_score: int
    
    # Tactical
    home_formation: string    # "4-3-3"
    away_formation: string
    
  examples:
    - { id: "pl-25-26-r26-liv-ars", home_team_id: "liverpool", away_team_id: "arsenal" }
```

### 1.6 MatchPerformance
```yaml
MatchPerformance:
  description: "Performance de um jogador num jogo específico"
  properties:
    id: string (PK)           # "pl-25-26-r26-liv-ars-salah"
    match_id: string (FK)
    player_id: string (FK)
    team_id: string (FK)
    
    # Basic
    is_starter: boolean
    position_played: string
    shirt_number: int
    minutes_played: int
    
    # Rating
    rating: decimal           # 0-10
    
    # Offensive
    goals: int
    assists: int
    xg: decimal
    xa: decimal
    xgot: decimal             # xG on target
    shots: int
    shots_on_target: int
    
    # Passing
    passes: int
    passes_accurate: int
    pass_accuracy: decimal
    key_passes: int
    chances_created: int
    
    # Defensive
    tackles: int
    interceptions: int
    clearances: int
    blocks: int
    defensive_actions: int
    
    # Duels
    duels_won: int
    duels_lost: int
    aerial_duels_won: int
    
    # Discipline
    yellow_cards: int
    red_cards: int
    fouls_committed: int
    fouls_won: int
    
    # Substitution
    sub_in_minute: int
    sub_out_minute: int
    
  examples:
    - { match_id: "...", player_id: "mohamed-salah", rating: 8.2, goals: 1, xg: 0.65 }
```

### 1.7 MatchStats
```yaml
MatchStats:
  description: "Estatísticas de equipa num jogo"
  properties:
    id: string (PK)           # "pl-25-26-r26-liv-ars-liv"
    match_id: string (FK)
    team_id: string (FK)
    is_home: boolean
    
    # Goals
    goals: int
    xg: decimal
    
    # Possession
    possession: decimal       # percentage
    
    # Shots
    shots: int
    shots_on_target: int
    shots_off_target: int
    shots_blocked: int
    shots_inside_box: int
    shots_outside_box: int
    big_chances: int
    big_chances_missed: int
    
    # Passing
    passes: int
    passes_accurate: int
    pass_accuracy: decimal
    long_balls: int
    long_balls_accurate: int
    crosses: int
    crosses_accurate: int
    
    # Defense
    tackles: int
    interceptions: int
    clearances: int
    blocks: int
    
    # Set pieces
    corners: int
    free_kicks: int
    
    # Discipline
    fouls: int
    yellow_cards: int
    red_cards: int
    offsides: int
    
    # Goalkeeper
    saves: int
```

---

## 2. ENTIDADES TEMPORAIS (State Snapshots)

### 2.1 TeamState
```yaml
TeamState:
  description: "Estado de uma equipa num momento específico (por round)"
  properties:
    id: string (PK)           # "liverpool-r26"
    team_id: string (FK)
    round_id: string (FK)
    as_of_date: date
    
    # Position
    position: int             # 3
    points: int               # 52
    played: int               # 25
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    
    # Form (last 5)
    form_string: string       # "WWDWL"
    form_points: int          # 10 out of 15
    
    # xG metrics (last 5)
    xg_for_last5: decimal
    xg_against_last5: decimal
    xg_diff_last5: decimal
    
    # Goals (last 5)
    goals_for_last5: int
    goals_against_last5: int
    clean_sheets_last5: int
    
    # Home/Away split
    home_wins: int
    home_draws: int
    home_losses: int
    away_wins: int
    away_draws: int
    away_losses: int
    
    # Trend
    form_trend: enum          # "improving", "stable", "declining"
    position_change_last5: int
    
    # Calculated
    ppg: decimal              # points per game
    xg_per_game: decimal
    xga_per_game: decimal
    
  indexes:
    - [team_id, round_id] UNIQUE
    - [round_id, position]
```

### 2.2 PlayerState
```yaml
PlayerState:
  description: "Estado de um jogador num momento específico (por round)"
  properties:
    id: string (PK)           # "salah-r26"
    player_id: string (FK)
    team_id: string (FK)
    round_id: string (FK)
    as_of_date: date
    
    # Season totals
    appearances: int
    starts: int
    minutes: int
    
    # Goals & Assists
    goals: int
    assists: int
    goal_contributions: int   # goals + assists
    
    # xG season
    xg_total: decimal
    xa_total: decimal
    xg_per90: decimal
    xa_per90: decimal
    
    # Form (last 5)
    goals_last5: int
    assists_last5: int
    xg_last5: decimal
    avg_rating_last5: decimal
    minutes_last5: int
    
    # Rating
    avg_rating_season: decimal
    rating_trend: enum        # "improving", "stable", "declining"
    
    # Per 90 stats
    shots_per90: decimal
    key_passes_per90: decimal
    
  indexes:
    - [player_id, round_id] UNIQUE
    - [team_id, round_id]
```

---

## 3. RELAÇÕES (Edges)

```yaml
Relations:
  
  # Competition structure
  ROUND_OF:
    from: Round
    to: Competition
    properties: {}
    
  # Match structure  
  FIXTURE_IN:
    from: Match
    to: Round
    properties: {}
    
  HOME_TEAM:
    from: Match
    to: Team
    properties: {}
    
  AWAY_TEAM:
    from: Match
    to: Team
    properties: {}
    
  # Team participation
  COMPETES_IN:
    from: Team
    to: Competition
    properties:
      season: string
      joined_date: date
      
  # Player participation
  PLAYS_FOR:
    from: Player
    to: Team
    properties:
      from_date: date
      to_date: date         # null if current
      shirt_number: int
      is_captain: boolean
      contract_until: date
      
  PLAYED_IN:
    from: Player
    to: Match
    properties:
      # This is essentially MatchPerformance
      # Can be modeled as edge or as node
      
  # State snapshots (temporal)
  STATE_AT:
    from: Team
    to: TeamState
    properties: {}
    
  STATE_AT:
    from: Player
    to: PlayerState
    properties: {}
```

---

## 4. INTELLIGENCE DERIVADA

### 4.1 MatchupIntelligence
```yaml
MatchupIntelligence:
  description: "Análise pré-jogo derivada dos states"
  properties:
    match_id: string (FK)
    
    # From TeamStates
    home_position: int
    away_position: int
    position_diff: int
    
    home_form: string
    away_form: string
    form_advantage: enum      # "home", "away", "neutral"
    
    home_xg_avg: decimal
    away_xg_avg: decimal
    xg_advantage: enum
    
    # From H2H
    h2h_matches: int
    h2h_home_wins: int
    h2h_draws: int
    h2h_away_wins: int
    h2h_pattern: string       # "home_dominant", "away_dominant", "balanced"
    
    # Predictions (derived)
    predicted_home_xg: decimal
    predicted_away_xg: decimal
    predicted_total_goals: decimal
    predicted_winner: enum    # "home", "draw", "away"
    confidence: decimal
```

### 4.2 PlayerForm
```yaml
PlayerForm:
  description: "Análise de forma do jogador"
  properties:
    player_id: string (FK)
    round_id: string (FK)
    
    # Form indicators
    is_hot: boolean           # goals in 3+ of last 5
    is_cold: boolean          # no g/a in last 5
    rating_trend: enum
    
    # Comparison to season avg
    goals_vs_avg: decimal     # +/- vs season average
    rating_vs_avg: decimal
    
    # xG performance
    is_overperforming: boolean  # goals > xG
    is_underperforming: boolean
```

---

## 5. SCHEMA SQL (Postgres)

```sql
-- Core entities
CREATE TABLE competitions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT,
    tier INT,
    season TEXT NOT NULL,
    start_date DATE,
    end_date DATE,
    total_rounds INT,
    total_teams INT
);

CREATE TABLE teams (
    id TEXT PRIMARY KEY,
    fotmob_id INT UNIQUE,
    name TEXT NOT NULL,
    short_name TEXT,
    country TEXT,
    stadium TEXT,
    logo_url TEXT
);

CREATE TABLE players (
    id TEXT PRIMARY KEY,
    fotmob_id INT UNIQUE,
    name TEXT NOT NULL,
    short_name TEXT,
    nationality TEXT,
    birth_date DATE,
    primary_position TEXT,
    photo_url TEXT
);

CREATE TABLE rounds (
    id TEXT PRIMARY KEY,
    competition_id TEXT REFERENCES competitions(id),
    number INT NOT NULL,
    start_date DATE,
    end_date DATE,
    status TEXT DEFAULT 'scheduled'
);

CREATE TABLE matches (
    id TEXT PRIMARY KEY,
    fotmob_id INT UNIQUE,
    competition_id TEXT REFERENCES competitions(id),
    round_id TEXT REFERENCES rounds(id),
    home_team_id TEXT REFERENCES teams(id),
    away_team_id TEXT REFERENCES teams(id),
    date DATE NOT NULL,
    kickoff_time TIMESTAMP,
    venue TEXT,
    attendance INT,
    referee TEXT,
    status TEXT DEFAULT 'scheduled',
    home_score INT,
    away_score INT,
    home_formation TEXT,
    away_formation TEXT
);

-- Temporal states
CREATE TABLE team_states (
    id TEXT PRIMARY KEY,
    team_id TEXT REFERENCES teams(id),
    round_id TEXT REFERENCES rounds(id),
    as_of_date DATE,
    position INT,
    points INT,
    played INT,
    wins INT,
    draws INT,
    losses INT,
    goals_for INT,
    goals_against INT,
    form_string TEXT,
    xg_for_last5 DECIMAL(5,2),
    xg_against_last5 DECIMAL(5,2),
    UNIQUE(team_id, round_id)
);

CREATE TABLE player_states (
    id TEXT PRIMARY KEY,
    player_id TEXT REFERENCES players(id),
    team_id TEXT REFERENCES teams(id),
    round_id TEXT REFERENCES rounds(id),
    as_of_date DATE,
    appearances INT,
    minutes INT,
    goals INT,
    assists INT,
    xg_total DECIMAL(5,2),
    avg_rating DECIMAL(3,1),
    UNIQUE(player_id, round_id)
);

-- Performance data
CREATE TABLE match_performances (
    id TEXT PRIMARY KEY,
    match_id TEXT REFERENCES matches(id),
    player_id TEXT REFERENCES players(id),
    team_id TEXT REFERENCES teams(id),
    is_starter BOOLEAN,
    minutes_played INT,
    rating DECIMAL(3,1),
    goals INT DEFAULT 0,
    assists INT DEFAULT 0,
    xg DECIMAL(5,3),
    xa DECIMAL(5,3),
    shots INT,
    passes INT,
    tackles INT,
    UNIQUE(match_id, player_id)
);

CREATE TABLE match_stats (
    id TEXT PRIMARY KEY,
    match_id TEXT REFERENCES matches(id),
    team_id TEXT REFERENCES teams(id),
    is_home BOOLEAN,
    possession DECIMAL(4,1),
    shots INT,
    shots_on_target INT,
    xg DECIMAL(5,2),
    passes INT,
    pass_accuracy DECIMAL(4,1),
    corners INT,
    fouls INT,
    UNIQUE(match_id, team_id)
);

-- Indexes
CREATE INDEX idx_matches_round ON matches(round_id);
CREATE INDEX idx_matches_date ON matches(date);
CREATE INDEX idx_team_states_round ON team_states(round_id);
CREATE INDEX idx_player_states_round ON player_states(round_id);
CREATE INDEX idx_performances_match ON match_performances(match_id);
CREATE INDEX idx_performances_player ON match_performances(player_id);
```

---

## 6. ETL: FotMob → KG

```
fotmob_matches           →  matches + match_stats
fotmob_player_perfs      →  match_performances
                         
Derivar:                 
  matches (per round)    →  team_states
  match_performances     →  player_states
```

---

## 7. PRÓXIMOS PASSOS

1. [ ] Validar esta ontologia
2. [ ] Criar as tabelas no Postgres
3. [ ] Escrever ETL para popular do FotMob
4. [ ] Calcular team_states e player_states
5. [ ] Criar queries para intelligence
6. [ ] Ligar ao UI

---

## 8. PERGUNTAS EM ABERTO

1. Usar Postgres relacional ou Neo4j para o grafo?
2. Granularidade temporal: por round ou por dia?
3. Quais métricas derivadas são prioritárias?
4. Como lidar com jogadores que mudam de equipa?
