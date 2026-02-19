# CLARITY ENGINE - Agent Context Document

> Este documento fornece todo o contexto necessario para um agente AI comecar do zero e contribuir para o projeto.

---

## 1. VISAO GERAL DO PROJETO

### 1.1 O Que E o Clarity Engine?

O **Clarity Engine** e um sistema de inteligencia de futebol que gera analises pre-jogo taticas e narrativas baseadas em dados verificaveis. O objetivo principal e produzir previsoes de jogos que sejam consistentemente melhores que ferramentas genericas como ChatGPT.

### 1.2 Filosofia Central

1. **Separacao Contexto vs Narrativa**: Dados deterministicos (factos) sao separados da narrativa gerada pelo LLM
2. **Fundamentacao em Dados Reais**: Todas as afirmacoes sao baseadas em dados verificaveis (lesoes, lineups, forma, odds, xG)
3. **Avaliacao Pos-Jogo**: Qualidade da narrativa e avaliada apos o jogo contra resultados reais
4. **Glass Box Logic**: Raciocinio transparente mostrando pesos dos fatores e drivers de decisao

### 1.3 Utilizador Alvo

Analistas de futebol e operacoes de apostas que procuram previsoes calibradas e baseadas em evidencias com raciocinio claro.

---

## 2. STACK TECNOLOGICO

### 2.1 Tecnologias Principais

| Componente | Tecnologia | Versao |
|------------|------------|--------|
| Linguagem | Python | 3.12 |
| Base de Dados | PostgreSQL | 15 |
| Dashboard | Streamlit | >=1.28.0 |
| API REST | FastAPI | >=0.109.0 |
| LLM Previsoes | OpenAI GPT | gpt-5.1 |
| LLM Auditoria | Google Gemini | gemini-2.5-flash |
| Web Scraping | Selenium + BeautifulSoup | 4.38.0 |

### 2.2 Dependencias Chave (requirements.txt)

```
openai==2.8.1                    # Cliente API GPT
google-genai==0.3.0              # Cliente API Gemini
pandas==2.3.3                    # Manipulacao de dados
psycopg2-binary==2.9.11          # Driver PostgreSQL
selenium==4.38.0                 # Automacao browser (FBRef)
webdriver-manager==4.0.2         # Gestao Chrome driver
beautifulsoup4 (via lxml)        # Web parsing
rapidfuzz==3.6.2                 # Fuzzy name matching
streamlit>=1.28.0                # Dashboard UI
fastapi>=0.109.0                 # REST API
```

### 2.3 Variaveis de Ambiente (.env)

```bash
DATABASE_URL=postgresql://user@localhost:5432/clarity_football
OPENAI_API_KEY=sk-proj-...
GEMINI_API_KEY=AIzaSy...
```

---

## 3. ARQUITETURA DO SISTEMA

### 3.1 Diagrama de Fluxo de Dados

```
FONTES DE DADOS (FBRef, Understat, ClubElo, Transfermarkt)
    |
    v
CAMADA DE INGESTAO (src/ingestion/)
    |
    v
BASE DE DADOS POSTGRESQL (Hub-and-Spoke Schema)
    |
    v
CONTEXT BUILDER (src/analysis/context_builder_v2.py)
    |
    v
ANALISE LLM (src/analysis/predictor.py - GPT-5.1)
    |
    v
CACHE NA BD (analysis_reports)
    |
    v
DASHBOARD STREAMLIT (src/dashboard.py)
    |
    v
AUDITORIA POS-JOGO (src/analysis/reality.py - Gemini)
    |
    v
AVALIACAO (src/analysis/evaluator.py)
```

### 3.2 Workflow em 4 Fases

| Fase | Descricao | Estado |
|------|-----------|--------|
| **Fase 1** | Assemblagem de Dados Pre-Jogo | COMPLETA |
| **Fase 2** | Geracao de Narrativa (LLM) | OPERACIONAL |
| **Fase 3** | Auditoria Pos-Jogo (Reality Check) | OPERACIONAL |
| **Fase 4** | Avaliacao e Calibracao | EM PROGRESSO |

---

## 4. ESTRUTURA DO PROJETO

```
clarity_engine/
├── src/
│   ├── analysis/              # Motor de analise (14 modulos)
│   │   ├── context_builder_v2.py    # Assemblagem de contexto
│   │   ├── context_schema.py        # Definicoes de schema
│   │   ├── predictor.py             # Interface LLM (ClarityEngine)
│   │   ├── narrative_schema.py      # Schema de output
│   │   ├── reality.py               # Auditoria pos-jogo (RealitySeeker)
│   │   ├── evaluator.py             # Scoring de qualidade
│   │   ├── prompts.py               # Carregador de prompts
│   │   ├── builder.py               # Context builder original
│   │   └── validation.py            # Motor de validacao
│   │
│   ├── database/              # Conexao e operacoes BD
│   │   ├── config.py                # get_connection()
│   │   ├── schema.sql               # Schema completo
│   │   └── operations.py
│   │
│   ├── ingestion/             # Conectores de dados (6 modulos)
│   │   ├── scraper.py               # FBRef (Selenium)
│   │   ├── understat_enrich.py      # Understat API
│   │   ├── elo_backfill.py          # ClubElo API
│   │   ├── transfermarkt_injuries.py
│   │   ├── transfermarkt_lineups.py
│   │   └── transfermarkt_match_ids.py
│   │
│   ├── data/                  # Feature engineering
│   │   ├── feature_engineering.py
│   │   ├── team_strength.py
│   │   └── player_impact.py
│   │
│   ├── jobs/
│   │   └── batch_runner.py          # Orquestracao (BatchRunner)
│   │
│   ├── dashboard.py           # Streamlit principal (~1500 linhas)
│   ├── api/                   # FastAPI (stubs)
│   └── web/                   # Vite frontend (stubs)
│
├── prompts/                   # Templates de prompt
│   ├── v1_hybrid.txt
│   ├── v2_contrarian.txt
│   ├── v3_enhanced.txt
│   └── v4_evaluator.txt
│
├── scripts/                   # Scripts utilitarios (15+)
│   ├── init_db.py
│   ├── backfill_injuries.py
│   ├── backfill_lineups.py
│   ├── build_tm_mappings.py
│   ├── download_odds_historical.py
│   └── ...
│
├── main.py                    # CLI principal
├── requirements.txt
└── docs/
```

---

## 5. SCHEMA DA BASE DE DADOS

### 5.1 Modelo Hub-and-Spoke

A tabela `fixtures` e o hub central. Todas as outras tabelas sao "spokes" que referenciam `fixtures.id`.

### 5.2 Tabelas Principais

#### `fixtures` (Hub Central)
```sql
CREATE TABLE fixtures (
    id TEXT PRIMARY KEY,              -- "2024-08-17_Arsenal_Wolves"
    date DATE NOT NULL,
    season TEXT NOT NULL,             -- "2024-2025"
    league TEXT DEFAULT 'Premier League',
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score INT,
    away_score INT,
    status TEXT DEFAULT 'SCHEDULED',  -- 'FINISHED', 'SCHEDULED', 'POSTPONED'
    round INT,                        -- Gameweek number
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### `team_stats` (Metricas por Jogo)
```sql
CREATE TABLE team_stats (
    fixture_id TEXT REFERENCES fixtures(id),
    team_name TEXT NOT NULL,
    is_home BOOLEAN NOT NULL,
    xg DECIMAL(4,2),
    xga DECIMAL(4,2),
    ppda DECIMAL(4,1),
    field_tilt DECIMAL(4,1),
    elo INT,
    PRIMARY KEY (fixture_id, team_name)
);
```

#### `analysis_reports` (Cache de Previsoes LLM)
```sql
CREATE TABLE analysis_reports (
    id SERIAL PRIMARY KEY,
    fixture_id TEXT REFERENCES fixtures(id),
    prompt_version TEXT NOT NULL,     -- "hybrid", "contrarian", "v3"
    model_name TEXT NOT NULL,         -- "gpt-5.1"
    created_at TIMESTAMP DEFAULT NOW(),
    headline TEXT,
    predicted_score TEXT,
    confidence INT,
    betting_recommendation TEXT,
    weights JSONB,                    -- Factor weights (Glass Box)
    full_json JSONB,                  -- Full LLM response
    actual_score TEXT,
    is_correct BOOLEAN,
    pnl DECIMAL(6,2)
);
```

#### `match_reality` (Auditoria Pos-Jogo)
```sql
CREATE TABLE match_reality (
    fixture_id TEXT PRIMARY KEY REFERENCES fixtures(id),
    score_home INT,
    score_away INT,
    xg_home DECIMAL(4,2),
    xg_away DECIMAL(4,2),
    key_events JSONB,
    narrative_summary TEXT,
    luck_factor TEXT,
    source_type TEXT DEFAULT 'forensic_auditor',
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### `analysis_evaluations` (Avaliacao de Qualidade)
```sql
CREATE TABLE analysis_evaluations (
    id SERIAL PRIMARY KEY,
    report_id INT REFERENCES analysis_reports(id),
    fixture_id TEXT REFERENCES fixtures(id),
    prompt_version TEXT NOT NULL,
    narrative_score INT,              -- 0-100
    narrative_feedback TEXT,
    score_accuracy BOOLEAN,
    tip_accuracy BOOLEAN,
    evaluation_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### `lineups_historical` (Lineups Transfermarkt)
```sql
CREATE TABLE lineups_historical (
    fixture_id TEXT REFERENCES fixtures_historical(fixture_id),
    team_id INT NOT NULL,
    formation TEXT,
    lineup_type TEXT NOT NULL,
    players JSONB NOT NULL,           -- Lista de jogadores
    data_source TEXT NOT NULL,
    PRIMARY KEY (fixture_id, team_id, lineup_type)
);
```

#### `player_injuries_historical` (Historico de Lesoes)
```sql
CREATE TABLE player_injuries_historical (
    player_id INT NOT NULL,
    season TEXT,
    injury_reason TEXT,
    from_date DATE NOT NULL,
    end_date DATE,
    days_missed INT,
    games_missed INT,
    data_source TEXT NOT NULL,
    PRIMARY KEY (player_id, from_date, injury_reason)
);
```

### 5.3 Convencao de Fixture ID

```
{YYYY-MM-DD}_{HomeTeam}_{AwayTeam}

Exemplos:
- 2025-08-16_Arsenal_Wolves
- 2025-01-18_Liverpool_Bournemouth
```

---

## 6. MODULOS CHAVE EM DETALHE

### 6.1 ContextBuilderV2 (`src/analysis/context_builder_v2.py`)

**Responsabilidade**: Assemblar contexto deterministico pre-jogo.

**Classes Principais**:
- `ContextBuilderV2`: Builder principal
- `MatchContext`: Contexto completo do jogo
- `TeamContext`: Contexto de uma equipa (identity, form, absences, lineup)

**Metodo Principal**:
```python
def build_context(self, fixture_id: str) -> Optional[MatchContext]:
    """
    Assembla contexto completo para um fixture.
    Garante time-travel safety (so usa dados pre-kickoff).
    """
```

**Time-Travel Safety**: Principio critico - todas as queries filtram por `date <= match_date` para nao usar informacao futura.

### 6.2 ClarityEngine (`src/analysis/predictor.py`)

**Responsabilidade**: Interface com LLM para gerar previsoes.

**Fluxo**:
1. Verifica cache na BD
2. Assembla contexto via `MatchContextBuilder`
3. Carrega prompt apropriado
4. Chama OpenAI API
5. Salva resultado na BD

```python
class ClarityEngine:
    def __init__(self, model="gpt-5.1"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.builder = MatchContextBuilder()

    def run_analysis(self, fixture_id, prompt_key="hybrid", force_refresh=False):
        # 1. Check Cache
        # 2. Build Context
        # 3. Get Prompt
        # 4. Call LLM
        # 5. Save to Cache
```

### 6.3 RealitySeeker (`src/analysis/reality.py`)

**Responsabilidade**: Auditoria pos-jogo usando Gemini + Google Search.

**Fluxo**:
1. Busca stats internas da BD
2. Chama Gemini com prompt de auditoria forense
3. Usa Google Search para encontrar relatorios de jogo
4. Gera "truth vector" estruturado
5. Salva em `match_reality`

**Output Estruturado**:
```json
{
  "truth_vector": {
    "actual_winner": "Home/Away/Draw",
    "tactical_scenario": "Domination without Chances",
    "luck_factor": "3"
  },
  "stat_audit": {
    "xg_fidelity": "Medium",
    "stat_lie_detected": true,
    "explanation": "xG inflated by late shots when chasing game"
  }
}
```

### 6.4 BatchRunner (`src/jobs/batch_runner.py`)

**Responsabilidade**: Orquestracao de operacoes em batch.

**Metodos Principais**:
```python
# Previsoes
run_round_predictions(round_id, season, prompt_version)
run_specific_match(fixture_id, prompt_version)
run_next_pending_batch(limit, prompt_version)

# Auditoria (Truth)
run_round_truth(round_id, season)
run_specific_reality_check(fixture_id)
run_truth_batch(limit)

# Avaliacao
evaluate_analyses_batch(season, prompt_version, limit)
```

---

## 7. SISTEMA DE PROMPTS

### 7.1 Versoes Disponiveis

| Versao | Ficheiro | Estilo |
|--------|----------|--------|
| `hybrid` | v1_hybrid.txt | Jornalista seguro |
| `contrarian` | v2_contrarian.txt | Auditor arriscado |
| `v3` | v3_enhanced.txt | Enhanced com crisis awareness |

### 7.2 Estrutura do Prompt v3 (Enhanced)

```
YOU ARE: 'Clarity', transparent Football Intelligence Engine

INPUT DATA:
- Identity: Season-long baseline (Elo, xG Diff, Field Tilt)
- Form: Recent performance (Last 5 games, Points, Goals)
- Matchup: Calculated styles (PPDA)

CRITICAL ANALYSIS LOGIC:
1. THE "CRISIS" DYNAMIC
   - High-Elo Favorite in poor form?
   - Scenario A: vs Transitions Team -> UPSET RISK
   - Scenario B: vs Passive Team -> STRUGGLE WIN

2. THE "STYLISTIC AMBUSH"
   - High Line vs Deep Block trap games

3. THE "HOME PRESSURE" PARADOX
   - Crisis at home = toxic crowd factor

OUTPUT FORMAT:
{
    "headline": "...",
    "narrative": { "game_flow": "...", "tactical_dynamic": "..." },
    "prediction": { "scoreline": "...", "confidence": 0-100 },
    "evidence_chain": { "observed_stats": [...], "market_verdict": "..." },
    "glass_box_logic": {
        "primary_factor": "Identity/Form/Matchup",
        "factor_weights": { "identity": 5, "form": 8, "matchup": 6 }
    }
}
```

---

## 8. CLI E COMANDOS

### 8.1 main.py - CLI Principal

```bash
# Analise de jogo especifico
python main.py --test <fixture_id>

# Previsoes para ronda inteira
python main.py --round 14 --mode predict --prompt v3

# Auditoria pos-jogo para ronda
python main.py --round 14 --mode truth

# Ambos (previsao + auditoria)
python main.py --round 14 --mode both --prompt hybrid

# Batch de pendentes
python main.py --batch --prompt hybrid
```

### 8.2 Scripts Utilitarios

```bash
# Inicializar schema BD
python scripts/init_db.py

# Backfill de lesoes
python scripts/backfill_injuries.py

# Backfill de lineups
python scripts/backfill_lineups.py

# Importar odds historicas
python scripts/download_odds_historical.py

# Mapear FBRef -> Transfermarkt
python scripts/build_tm_mappings.py
```

### 8.3 Dashboard

```bash
# Iniciar dashboard Streamlit
streamlit run src/dashboard.py
# Abre em localhost:8501
```

**4 Modos Operacionais**:
1. **COCKPIT**: Vista de analista com KPIs e leaderboard de prompts
2. **VALIDATE**: Geracao de dados e validacao de narrativas
3. **OPERATE**: Gerar analises em batch
4. **MONITOR**: Tracking de performance

---

## 9. FONTES DE DADOS

### 9.1 Fontes Primarias

| Fonte | Dados | Metodo | Notas |
|-------|-------|--------|-------|
| **FBRef** | Fixtures, Scores, xG | Selenium (Cloudflare) | Premier League |
| **Understat** | PPDA, Field Tilt | JSON API | Metricas taticas |
| **ClubElo** | Elo Ratings | REST API | Ratings diarios |
| **Transfermarkt** | Lesoes, Lineups | BeautifulSoup | 2s delay entre requests |
| **Football-Data.co.uk** | Odds 1X2 | CSV Manual | So jogos passados |

### 9.2 Cobertura de Dados Atual

| Tipo | Cobertura | Estado |
|------|-----------|--------|
| Fixtures | 380/380 (100%) | Completo PL 2025-26 |
| Lineups | 358/380 (94%) | Transfermarkt |
| Odds | 220/380 (58%) | So jogos passados |
| Lesoes | 3,337 registos | 481 jogadores |
| Elo Ratings | 100% | ClubElo diario |

---

## 10. PADROES ARQUITETURAIS

### 10.1 Hub-and-Spoke Database

Todas as tabelas satelite referenciam `fixtures.id` como foreign key.

### 10.2 Time-Travel Safety

**Principio Critico**: So usar dados disponiveis antes do kickoff.

```sql
WHERE from_date <= match_date
  AND (end_date IS NULL OR end_date > match_date)
```

### 10.3 Normalizacao de Nomes de Equipas

Usa fuzzy matching (rapidfuzz) com mapeamento canonico para lidar com variacoes FBRef <-> Understat <-> ClubElo.

### 10.4 Estrategia de Caching

- Cache backed por BD (verifica antes de chamar LLM)
- Evita chamadas API redundantes
- Opcao `force_refresh` para bypass

### 10.5 Glass Box Logic

Cada previsao inclui:
- Cadeia de raciocinio primaria
- Pesos dos fatores (ex: {form: 0.3, xG: 0.25, injuries: 0.2})
- Drivers de confianca
- Fontes de incerteza

---

## 11. LIMITACOES CONHECIDAS

1. **FBRef Scraping**: Dependencia de Selenium, bloqueio Cloudflare, mudancas DOM
2. **Transfermarkt Rate Limiting**: Requer delays de 2s entre requests
3. **Odds de Jogos Futuros**: So disponiveis perto do kickoff (58% cobertura)
4. **Suspensoes**: Nao rastreadas explicitamente (so lesoes)
5. **Dados Real-time**: So batch, sem updates ao vivo
6. **Multi-Liga**: Principalmente PL, infraestrutura para expansao existe
7. **soccerdata**: Instalado mas nao integrado (problemas de dependencia)

---

## 12. AREAS PARA MELHORIA

### 12.1 Prioridade Alta

- [ ] Completar suite de avaliacao (Fase 4)
- [ ] Integrar APIs real-time (API-Football, The Odds API)
- [ ] Melhorar cobertura de odds para jogos futuros
- [ ] Adicionar tracking de suspensoes

### 12.2 Prioridade Media

- [ ] Expandir para outras ligas (La Liga, Bundesliga)
- [ ] Otimizar prompts via A/B testing sistematico
- [ ] Melhorar calculo de impacto de lesoes
- [ ] Dashboard de performance de prompts mais detalhado

### 12.3 Prioridade Baixa

- [ ] Frontend React/Vite (stubs existem)
- [ ] API REST completa (FastAPI stubs existem)
- [ ] Integrar soccerdata library
- [ ] ML features para previsoes hibridas

---

## 13. COMO COMECAR A CONTRIBUIR

### 13.1 Setup Inicial

```bash
# 1. Clonar e instalar dependencias
cd clarity_engine
pip install -r requirements.txt

# 2. Configurar variaveis de ambiente
cp .env.example .env
# Editar .env com as API keys

# 3. Inicializar base de dados
python scripts/init_db.py

# 4. Testar uma analise
python main.py --test "2025-01-18_Liverpool_Bournemouth"

# 5. Iniciar dashboard
streamlit run src/dashboard.py
```

### 13.2 Fluxo de Desenvolvimento

1. **Explorar**: Usar dashboard para entender o sistema
2. **Identificar**: Escolher area de melhoria
3. **Implementar**: Seguir padroes existentes
4. **Testar**: Verificar com jogos especificos
5. **Validar**: Confirmar que analises sao coerentes

### 13.3 Pontos de Entrada Recomendados

| Tarefa | Ficheiro Inicial |
|--------|------------------|
| Melhorar prompts | `prompts/*.txt` |
| Adicionar fonte dados | `src/ingestion/` |
| Melhorar context builder | `src/analysis/context_builder_v2.py` |
| Melhorar avaliacao | `src/analysis/evaluator.py` |
| Features de dashboard | `src/dashboard.py` |
| Novos scripts | `scripts/` |

---

## 14. GLOSSARIO

| Termo | Definicao |
|-------|-----------|
| **xG** | Expected Goals - probabilidade de golo baseada na qualidade do remate |
| **xGA** | Expected Goals Against - xG da equipa adversaria |
| **PPDA** | Passes Allowed Per Defensive Action - metrica de pressing |
| **Field Tilt** | % de posse no terco ofensivo |
| **Elo** | Sistema de rating (como xadrez) |
| **Time-Travel Safety** | Garantia de so usar dados pre-jogo |
| **Glass Box Logic** | Raciocinio transparente com pesos visiveis |
| **Reality Check** | Auditoria pos-jogo via Gemini |
| **Fixture ID** | Formato: `YYYY-MM-DD_Home_Away` |

---

## 15. CONTACTOS E RECURSOS

- **Repositorio**: clarity_engine (local)
- **Dashboard**: `streamlit run src/dashboard.py`
- **Docs Tecnicas**: `docs/` folder
- **PRD**: `docs/prd/` folder

---

*Documento gerado automaticamente. Ultima atualizacao: 2026-02-01*
