# CLARITY — Master TODO & Action Plan
### "AI that knows BALL" — Gerado 4 Fev 2026

---

## 🔴 PROBLEMAS ATUAIS (Estado Real)

### Base de Dados
| # | Problema | Impacto | Prioridade |
|---|---------|---------|------------|
| 1 | Elo Liverpool = 1500 (campeões!) — backfill parado | Análise distorcida | 🔴 ALTO |
| 2 | Posições das lesões todas "MF" — scraper não categoriza | Injury impact errado | 🔴 ALTO |
| 3 | Rest days Man City = 32 dias (devia ser ~7) — cálculo partido | Contexto errado | 🔴 ALTO |
| 4 | Odds = None para jogos futuros — CSV só tem jogos passados | Sem odds pré-jogo | 🔴 ALTO |
| 5 | H2H = 1 jogo apenas — dados históricos limitados | Contexto fraco | 🟡 MÉDIO |
| 6 | xG nos match_reality vazio para jogos recentes | Reality check incompleto | 🟡 MÉDIO |
| 7 | `market_odds` tabela vazia (duplica `odds_snapshots`) | Lixo na DB | 🟢 BAIXO |
| 8 | Lesões paradas a 17 Jan (18 dias sem update) | Dados stale | 🔴 ALTO |

### Codebase
| # | Problema | Impacto | Prioridade |
|---|---------|---------|------------|
| 9 | FBRef scraper bloqueado por Cloudflare | Sem ingestão automática de xG | 🔴 ALTO |
| 10 | `realtime_ingestion.py` é placeholder (NotImplementedError) | Não faz nada | 🔴 ALTO |
| 11 | API-Football integration está no repo ERRADO (clarity-odds-core) | Código espalhado | 🟡 MÉDIO |
| 12 | 4 versões de dashboard (dashboard.py, _old, _v3, _v4) | Confusão | 🟢 BAIXO |
| 13 | Prompts focados em betting, não em "know ball" | Output errado | 🔴 ALTO |
| 14 | Team name mapping inconsistente (Man City vs Manchester City) | Dados duplicados | 🔴 ALTO |
| 15 | Zero testes automatizados a correr | Sem safety net | 🟡 MÉDIO |

### Produto
| # | Problema | Impacto | Prioridade |
|---|---------|---------|------------|
| 16 | Zero delivery — ninguém recebe nada | Sem produto | 🔴 CRÍTICO |
| 17 | Sem Telegram bot/canal | Sem distribuição | 🔴 CRÍTICO |
| 18 | Análise = JSON cru, não formatado | Ilegível | 🔴 ALTO |
| 19 | Sem league-specific context (PL ≠ Liga PT) | Análise genérica | 🟡 MÉDIO |
| 20 | Sem post-match learning | Não aprende | 🟡 MÉDIO |

---

## 🏗️ NOVA ARQUITECTURA — Multi-Source Pipeline

### Princípio: 3 fontes de dados, cross-validated

```
SOURCE 1: API (Determinístico)
  └─ football-data.co.uk → resultados, odds (CSV, grátis)
  └─ API-Football → fixtures, injuries, lineups, odds real-time
  └─ Understat → xG detalhado

SOURCE 2: SCRAPED (Determinístico)
  └─ Transfermarkt → injuries, transfers, market values, lineups
  └─ FBRef → stats avançados (se Cloudflare resolvido, senão Understat)
  └─ ClubElo.com → Elo ratings

SOURCE 3: AGENT (LLM-assisted, validado)
  └─ Gap filling → dados que faltam das fontes 1 e 2
  └─ News/morale → estado mental da equipa, notícias
  └─ Tactical notes → como a equipa tem jogado realmente
  └─ League meta-knowledge → padrões da liga

           ┌──────────┐
           │CROSS-CHECK│
           │ VALIDATOR │
           └─────┬─────┘
                 ↓
        ┌────────────────┐
        │ CLARITY CONTEXT │  ← JSON unificado, validado
        │     (v2)        │     pronto para análise
        └────────────────┘
```

### Team Name Registry (resolver problema #14)

```python
# src/data/team_registry.py — SINGLE SOURCE OF TRUTH
TEAMS = {
    "liverpool": {
        "canonical": "Liverpool",
        "aliases": ["Liverpool", "LFC"],
        "api_football_id": 40,
        "transfermarkt_id": "fc-liverpool",
        "fbref_id": "822bd0ba",
        "clubelo_name": "Liverpool",
        "csv_name": "Liverpool",
    },
    "manchester_city": {
        "canonical": "Manchester City",
        "aliases": ["Man City", "Manchester City", "MCFC"],
        "api_football_id": 50,
        "transfermarkt_id": "manchester-city",
        ...
    },
    ...
}
```

---

## 📋 ACTION PLAN — Por Fases

### FASE 0: Limpeza (HOJE — 4 Feb)
> Objectivo: Codebase limpo, dados corretos, zero lixo

- [ ] **0.1** Criar `src/data/team_registry.py` com mapeamento canónico das 20 equipas
- [ ] **0.2** Fix Elo backfill — correr `elo_backfill.py` ou scrape ClubElo.com
- [ ] **0.3** Fix posições nas lesões — mapear player → position via Transfermarkt
- [ ] **0.4** Fix rest days — bug no cálculo do context_builder_v2
- [ ] **0.5** DROP `market_odds` (vazia) ou popular com dados de `odds_snapshots`
- [ ] **0.6** Limpar dashboards: manter 1, arquivar resto
- [ ] **0.7** Limpar fixtures duplicados restantes

### FASE 1: Data Pipeline Sólido (5-6 Feb)
> Objectivo: Dados frescos e corretos para qualquer jogo

- [ ] **1.1** Integrar football-data.co.uk CSV como source primária (resultados + odds)
  - Script: `src/ingestion/footballdata_csv.py`
  - Cron: correr diariamente
- [ ] **1.2** Portar API-Football provider de clarity-odds-core → clarity_engine
  - `src/ingestion/providers/api_football.py`
  - Para: injuries real-time, odds pre-match, lineups
- [ ] **1.3** Fix Transfermarkt scraper para lesões actuais
  - `src/ingestion/transfermarkt_injuries.py` — já existe, precisa de update
- [ ] **1.4** Scraper ClubElo para Elo ratings atualizados
  - `src/ingestion/elo_scraper.py` — novo
- [ ] **1.5** Cross-check validator
  - `src/validation/cross_check.py` — novo
  - Se API diz "Saka fit" mas Transfermarkt diz "out" → FLAG
  - Se Elo API = 1500 mas ClubElo = 1935 → usar ClubElo
- [ ] **1.6** Criar `src/ingestion/run_pipeline.py` — master script
  ```
  python run_pipeline.py --date 2026-02-08
  → Busca fixtures do dia
  → Busca stats, injuries, odds
  → Cross-check
  → Guarda tudo na DB
  ```

### FASE 2: Context Builder V3 (6-7 Feb)
> Objectivo: JSON rico, validado, pronto para análise

- [ ] **2.1** Novo MatchContext schema com campos extra:
  - `team_trajectory` (últimos 10 jogos, não 5)
  - `key_player_dependency` (quem faz falta se sair)
  - `tactical_profile` (pressing, build-up, counter)
  - `league_context` (padrões da liga)
  - `weather` (se chove, se frio)
  - `referee_tendencies` (cartões, penalties)
- [ ] **2.2** Agent enrichment com validação
  - Agent preenche gaps
  - Tudo marcado "source: agent"
  - Fact-check contra dados determinísticos
- [ ] **2.3** Coverage score real (não fake 100%)
  - Cada campo tem: valor + source + confidence
  - Coverage = % de campos com dados reais

### FASE 3: "Know Ball" Prompt (7 Feb)
> Objectivo: Prompt que gera análise de qualidade pro Telegram

- [ ] **3.1** Novo prompt `v6_knowball.txt`
  - Não é sobre betting/odds
  - É sobre: como vai ser o jogo e porquê
  - Secções: Factos → Métricas → Narrativa → Alertas
  - Liga-specific angles
  - Referencia APENAS dados do context JSON
- [ ] **3.2** Prompt por liga (futuro)
  - `prompts/league_pl.txt`
  - `prompts/league_ligapt.txt`
- [ ] **3.3** Output formatter para Telegram
  - `src/output/telegram_formatter.py`
  - Emoji, secções claras, inline buttons

### FASE 4: Delivery (7-8 Feb)
> Objectivo: 10 amigos recebem análises no Telegram

- [ ] **4.1** Criar canal Telegram "Clarity Football"
- [ ] **4.2** Script para gerar análise e postar no canal
  ```
  python generate_and_post.py --fixture "2026-02-08_Liverpool_Manchester_City"
  ```
- [ ] **4.3** Gerar análises para todos os jogos do fim de semana
- [ ] **4.4** Partilhar canal com 10 amigos

### FASE 5: Post-Match & Learning (9-10 Feb)
> Objectivo: Sistema aprende com cada jogo

- [ ] **5.1** Post-match auto-ingestion (resultado + stats)
- [ ] **5.2** Compare prediction vs reality
- [ ] **5.3** Store "match insights" (o que decidiu o jogo)
- [ ] **5.4** Começar knowledge brain (factores decisivos)

---

## 📁 ESTRUTURA FINAL do clarity_engine

```
clarity_engine/
├── src/
│   ├── data/
│   │   ├── team_registry.py        🆕 Mapeamento canónico
│   │   └── league_meta.py          🆕 Padrões por liga
│   │
│   ├── ingestion/
│   │   ├── providers/
│   │   │   ├── api_football.py     📦 Portado de clarity-odds-core
│   │   │   └── base.py             📦 Portado de clarity-odds-core
│   │   ├── footballdata_csv.py     🆕 CSV ingestion
│   │   ├── elo_scraper.py          🆕 ClubElo scraper
│   │   ├── transfermarkt_injuries.py   ♻️ Existente, precisa fix
│   │   ├── transfermarkt_lineups.py    ✅ Existente
│   │   └── run_pipeline.py         🆕 Master ingestion script
│   │
│   ├── validation/
│   │   ├── cross_check.py          🆕 Multi-source validation
│   │   └── schema_validator.py     ♻️ Melhorar
│   │
│   ├── analysis/
│   │   ├── context_builder_v3.py   🆕 Novo context builder
│   │   ├── context_schema.py       ♻️ Expandir schema
│   │   └── prompts.py              ♻️ Adicionar v6
│   │
│   ├── agents/
│   │   ├── enriched_context.py     ✅ Existente (bom!)
│   │   ├── extraction_agent.py     ✅ Existente
│   │   └── extraction_validator.py ✅ Existente
│   │
│   ├── output/
│   │   ├── telegram_formatter.py   🆕 Format para Telegram
│   │   └── card_generator.py       🆕 Pillow cards (futuro)
│   │
│   └── telegram/                   🆕 (Fase 4+)
│       ├── bot.py
│       └── handlers/
│
├── prompts/
│   ├── v6_knowball.txt             🆕 "Know ball" prompt
│   ├── league_pl.txt               🆕 PL-specific angles
│   └── (v1-v5 → archive/)         📦 Arquivar
│
├── scripts/
│   └── generate_and_post.py        🆕 Gerar + postar no Telegram
│
└── config/
    └── data_sources.json           🆕 API keys, URLs, configs
```

---

## 🗑️ PARA ELIMINAR / ARQUIVAR

```
ELIMINAR:
  - market_odds table (vazia)
  - src/dashboard_old.py
  
ARQUIVAR (mover para archive/):
  - src/dashboard.py, dashboard_v3.py, dashboard_v4.py → archive/dashboards/
  - prompts/v1_hybrid.txt → archive/prompts/
  - prompts/v2_contrarian.txt → archive/prompts/
  - prompts/v3_enhanced.txt → archive/prompts/
  
REPOS EXTERNOS:
  - clarity-odds-core: portar API-Football + bot, depois arquivar repo
  - bethub: manter arquivado, ressuscitar na Fase 5+
```

---

## ⏱️ TIMELINE

```
4 Feb (HOJE):  Fase 0 — Limpeza + team registry
5 Feb:         Fase 1 — Data pipeline
6 Feb:         Fase 1 cont. + Fase 2 início
7 Feb:         Fase 2 + Fase 3 — Context V3 + prompt know ball
7 Feb noite:   Fase 4 — Canal Telegram + primeiras análises
8 Feb:         🚀 Amigos recebem Liverpool vs City
9 Feb:         Fase 5 — Post-match learning
```

---

## 💡 VISÃO: O que torna o Clarity diferente do ChatGPT

```
1. DADOS REAIS (API + scrape) — não artigos web
2. CÁLCULOS DETERMINÍSTICOS — código, não "na cabeça" do LLM
3. CROSS-VALIDATION — 3 fontes concordam antes de usar
4. LEAGUE META-KNOWLEDGE — padrões que só existem em cada liga
5. PLAYER DEPENDENCY — o que perde sem cada jogador
6. TEAM TRAJECTORY — como estão a jogar, não só resultados
7. POST-MATCH LEARNING — sistema que melhora com cada jogo
8. FACT-CHECK — narrativa verificada contra dados
9. DELIVERY AUTOMÁTICA — user não faz nada, recebe
10. ESCALA — 1 análise serve 100k users por €2/mês
```
