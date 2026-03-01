# Match Context Pipeline (Dados -> Codigo -> Uso por Versao)

Este documento explica, de ponta a ponta, como o "match context" e construido
no Clarity Engine, que dados alimentam o processo e como cada versao do codigo
usa esses dados. A ideia e servir de onboarding para um agent novo.

---

## 1) Visao geral (o que e "match context")

O match context e o pacote de dados pre-jogo que fundamenta todas as analises.
Ele e **deterministico** (so factos), **time-travel safe** (apenas dados antes
do kickoff) e e a unica fonte permitida para o LLM gerar a narrativa.

O fluxo basico:

```
Fontes externas -> Ingestao -> PostgreSQL -> Context Builder -> LLM -> Cache
```

---

## 2) Dados: fontes e ingestao

Fontes principais (ver `src/ingestion/`):
- FBRef (fixtures, scores, xG)
- Understat (PPDA, field tilt, stats taticas)
- ClubElo (ratings Elo)
- Transfermarkt (injuries e lineups)
- Odds historicas (CSV/API -> `market_odds`/`odds_snapshots`)

Ingestao tipica:
- `src/ingestion/scraper.py` (fixtures + team_stats base)
- `src/ingestion/understat_enrich.py` (PPDA, field tilt)
- `src/ingestion/elo_backfill.py` (Elo por jogo)
- `src/ingestion/transfermarkt_injuries.py`
- `src/ingestion/transfermarkt_lineups.py`

---

## 3) Dados: tabelas que o context builder usa

As tabelas abaixo sao usadas diretamente no builder (nomes como em SQL):

Basicas:
- `fixtures` (hub central: id, date, season, league, home_team, away_team, scores, status, round)
- `team_stats` (xg, xga, ppda, field_tilt, elo por fixture e equipa)

Historicas / adicionais:
- `player_injuries_historical` (lesoes ativas por equipa e data)
- `lineups_historical` (formacao + starters/bench por fixture)
- `market_odds` (odds 1X2 pre-match)
- `odds_snapshots` (odds historicas com captured_at)
- `player_market_values` (opcional, usado no builder_v2)

---

## 4) Schema canonico (MatchContext)

Definido em `src/analysis/context_schema.py`. E o formato **canonico** para
contexto deterministico.

Estrutura (alto nivel):
- `fixture_id`, `match_date`, `season`, `league`, `round_number`
- `home`, `away` (TeamContext)
  - `identity` (Elo + medias da epoca)
  - `form` (ultimos 5 jogos, pontos, xG, descanso)
  - `absences` (lesoes/ausencias)
  - `lineup` (se existir)
- `head_to_head`
- `schedule` (descanso e congestao)
- `league_position`
- `odds`
- `coverage_score`, `missing_fields`, `data_warnings`

Este schema e validado por:
- `validate_context()` (campos obrigatorios, ranges)
- `calculate_coverage_score()` (qualidade dos dados)

---

## 5) Como o match context e construido (ContextBuilderV2)

Arquivo: `src/analysis/context_builder_v2.py`

Sequencia principal em `build_context()`:
1) Carrega fixture (`fixtures`)
2) Constroi `home_context` e `away_context`
3) Constroi comparativos:
   - `head_to_head` (fixtures anteriores e finalizados)
   - `schedule` (descanso + jogos nos ultimos 7/14 dias)
   - `league_position` (classificacao calculada pre-jogo)
   - `odds` (market_odds ou odds_snapshots antes do kickoff)
4) Monta `MatchContext` (schema estrito)
5) Calcula `coverage_score`

Time-travel safety:
- Queries usam `date < match_date` e `status = 'FINISHED'`
- Odds usam `captured_at < match_date`
- Injuries so contam se ativas na data do jogo

---

## 6) Validacao e seguranca

Ferramentas de validacao:
- `src/analysis/time_travel_guard.py`
  - Detecta leaks (form, h2h, odds, resultados)
- `src/analysis/data_validator.py`
  - Reporta coverage, warnings e contexto bruto para o dashboard
- `src/analysis/narrative_schema.py`
  - Heuristica para impedir factos que nao estao no contexto

---

## 7) Versoes de context builder (legado vs atual)

### V1 - MatchContextBuilder (legacy)
Arquivo: `src/analysis/builder.py`

Formato (dict simples):
```
{
  "home": {
    "name": "...",
    "identity": { "elo", "season_ppda", "season_field_tilt", "season_overall_xg", ... },
    "form": { "last_5_results", "last_5_xg_diff", "days_rest", ... },
    "context": { "key_injuries": [], "is_home": true }
  },
  "away": { ... },
  "market_odds": { "home_win": null, "draw": null, "away_win": null }
}
```

Uso:
- `src/analysis/predictor.py` (prompts v1-v4)
- `src/analysis/probabilistic_predictor.py` (prompt v5_probabilistic)

Nota: Sem schema estrito, sem h2h, sem schedule, sem league_position.

---

### V2 - MatchContextBuilderV2 (transicao)
Arquivo: `src/analysis/builder_v2.py`

Evolucao do V1:
- Adiciona `absences` a partir de `player_injuries_historical`
- Usa `player_market_values` (se existir) para rankear lesoes
- Mantem output em dict (nao usa dataclass)

Uso:
- Atualmente nao e o builder principal do predictor (ver v1). Serve
  como versao intermediaria para enriquecer o contexto.

---

### V3 - ContextBuilderV2 (schema estrito)
Arquivo: `src/analysis/context_builder_v2.py`

Evolucao principal:
- Usa `MatchContext` (dataclass) de `context_schema.py`
- Gera `head_to_head`, `schedule`, `league_position`, `odds`
- `absences` e `lineup` (quando disponiveis)
- `coverage_score`, `missing_fields`, `data_warnings`

Uso:
- `src/api/main.py` (endpoint `/api/context/{fixture_id}`)
- `src/analysis/data_validator.py`
- Dashboard v4 (visualizacao de contexto)

**Status:** Producao (recomendado para novo desenvolvimento)

---

### V4 - EnrichedContextBuilder (AI agent enrichment)
Arquivo: `src/agents/enriched_context.py`

Evolucao principal:
- Usa V3 como base (ContextBuilderV2)
- Adiciona `ExtractionAgent` para enriquecimento via web search
- Usa `ExtractionValidator` com cross-checks anti-alucinacao
- Merge inteligente: DB data (truth) + Agent data (enrichment)
- Fallback gracioso para DB-only se agent falhar

Features novas:
- **Injury enrichment** via web scraping (real-time updates)
- **H2H enrichment** (mais detalhes historicos da web)
- **Team news/morale** context via Google Search
- **Validation layer** previne dados falsos/alucinados
- `EnrichmentResult` com metadata de qualidade

Arquitetura anti-alucinacao:
```
DB Data (truth) → Base context
     │
     ▼
Agent (Gemini + Google Search) → Structured JSON
     │
     ▼
Validator (cross-checks) → Reject se invalido
     │  (points = won*3 + drawn?)
     │  (GD = GF - GA?)
     │  (result matches score?)
     ▼
Merge → Enriched context (never wrong data!)
```

Exemplo de uso:
```python
from src.agents.enriched_context import EnrichedContextBuilder

builder = EnrichedContextBuilder(use_agent=True)
result = builder.build_enriched_context(
    fixture_id,
    enrich_injuries=True,
    enrich_h2h=True,
    enrich_news=True
)
context = result.context  # MatchContext enriched
print(f"Quality: {result.enrichment_quality}")
print(f"Agent data used: {result.agent_data_used}")
```

Validacao cross-checks:
- Form: result (W/D/L) deve coincidir com score
- Form: goals_scored_last_5 = soma dos scores individuais
- Table: points = won*3 + drawn
- Table: played = won + drawn + lost
- Table: goal_difference = goals_for - goals_against
- H2H: wins + draws + losses = total matches

**Status:** Experimental (limitado por quotas API). Ver `docs/context-builders-comparison.md` para comparacao detalhada.

---

## 8) Prompts e versoes de analise

Prompts em `prompts/`:
- `v1_hybrid.txt` -> prompt key `hybrid`
- `v2_contrarian.txt` -> `contrarian`
- `v3_enhanced.txt` -> `v3`
- `v4_calibrated.txt` -> `v4`
- `v5_probabilistic.txt` -> usado pelo `ProbabilisticPredictor`

Mapa de uso:
- `src/analysis/predictor.py` usa `PROMPTS` (v1-v4) + builder V1
- `src/analysis/probabilistic_predictor.py` usa v5 + builder V1

Nota importante:
Prompts v1-v4 assumem um contexto simples em JSON (legacy). Se mudar para
`ContextBuilderV2`, a estrutura muda e o prompt deve ser ajustado.

---

## 9) Onde o contexto aparece no produto

Fluxos principais:
- CLI / batch: `main.py` -> `ClarityEngine` -> builder V1 -> prompts v1-v4
- API: `/api/context/{fixture_id}` -> builder V3 (schema estrito)
- Dashboard v4: usa `DataValidator` para reconstituir contexto on-demand
- Avaliacao: usa `analysis_reports` + `match_reality` (nao depende do contexto direto)

Contexto nao e persistido no `analysis_reports` (so o output do LLM).
Se precisa de contexto historico, use `DataValidator.get_raw_context_json()`
ou reconstroi via builder.

---

## 10) Checklist rapido para um agent novo

1) Preciso de contexto canonico? -> use `ContextBuilderV2`
2) Quero gerar analise LLM existente? -> `ClarityEngine` (builder V1)
3) Quero evitar leaks? -> `TimeTravelGuard` + `DataValidator`
4) Vou mexer em prompts? -> veja `prompts/` + `src/analysis/prompts.py`

---

## 11) Referencias diretas (arquivos)

### Context Builders
- `src/analysis/builder.py` (V1 Legacy)
- `src/analysis/builder_v2.py` (V2 Transicao)
- `src/analysis/context_builder_v2.py` (V3 Producao)
- `src/agents/enriched_context.py` (V4 Enriched - NEW!)

### Agent Enrichment (V4)
- `src/agents/extraction_agent.py` (ExtractionAgent)
- `src/agents/extraction_validator.py` (ExtractionValidator)
- `src/agents/extraction_schemas.py` (Schemas e dataclasses)

### Schema & Validation
- `src/analysis/context_schema.py` (MatchContext dataclass)
- `src/analysis/time_travel_guard.py` (Time-travel safety)
- `src/analysis/data_validator.py` (Coverage validator)
- `src/analysis/narrative_schema.py` (Narrative validation)

### Prediction & Prompts
- `src/analysis/predictor.py` (ClarityEngine)
- `src/analysis/probabilistic_predictor.py` (ProbabilisticPredictor)
- `src/analysis/prompts.py` (Prompt loader)
- `prompts/v1_hybrid.txt`, `prompts/v2_contrarian.txt`, `prompts/v3_enhanced.txt`,
  `prompts/v4_calibrated.txt`, `prompts/v5_probabilistic.txt`

### Testing & Comparison
- `scripts/test_agents.py` (Agent validation tests - 6 tests pass!)
- `scripts/compare_context_builders.py` (Round 24 comparison)
- `docs/context-builders-comparison.md` (Detailed comparison report)
