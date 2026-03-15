# v1.6 Strategy — Match Intelligence com Cerebro Tactico

## Diagnostico Honesto do v1.5

### O que funciona
- **Pipeline de producao**: dados -> features -> modelo -> report -> rendering. Solido.
- **Caching e time-travel safety**: dados historicos correctos, sem data leakage.
- **Validation framework**: rubric pre-match + validator + evaluation records.
- **Rendering**: Telegram v1.5 format funcional.
- **Infraestrutura de dados**: FotMob scraper, team_states, fotmob_matches, ELO.

### O que falha
- **Cerebro fraco**: O LLM (GPT-4o) recebe numeros contabilisticos e tenta "ler o jogo" sem peças tacticas.
- **Dados contabilisticos**: xG, posse, pontos, posicao — nao tacticos. Faltam: transicoes, pressao, cruzamentos, bola parada, matchup profiles.
- **LLM sem reasoning**: GPT-4o segue instrucoes bem mas pensa superficialmente. Nao cruza factores, nao detecta contradicoes.
- **Avaliacao de forma**: mede "tens 3 evidencias?" mas nao "as evidencias estao certas?".

---

## Licao do Teste GPT-5.4

Um prompt simples no GPT-5.4 com web search produziu analise superior ao sistema v1.5. Porquê:
1. **Contexto fresco** — web search trazia noticias, lesoes, declaracoes do treinador.
2. **Reasoning profundo** — thinking model considera interaccoes entre factores.
3. **Training data rico** — o modelo ja tem padroes tacticos de futebol no training data.

**Conclusao**: O gargalo nao e o pipeline — e o que entra (dados pobres) e o que pensa (modelo fraco).

---

## Separacao de Metas

### Meta A: Melhor Analista de Futebol (foco actual)
Produzir analises claramente superiores a jornalistas, tipsters e previews genericas. Medir por qualidade analitica, nao por ROI.

### Meta B: Tipster Lucrativo (longo prazo)
Gerar edge consistente contra o mercado. Requer: Meta A + calibracao probabilistica + value detection. Nao e o foco agora.

---

## Arquitectura Alvo — 6 Camadas

```
1. DADOS          → team_states, fotmob_matches, web context (noticias, press conferences)
2. FEATURES       → tactical_rubric.json (~20 factores tacticos por jogo)
3. REASONING      → thinking model com perguntas estruturadas (mecanismos, matchup, riscos)
4. PROBABILIDADES → ml_anchor (modelo probabilistico) + signals determiniscos
5. DECISAO        → lean + confianca + cenarios
6. CONTEUDO       → narrativa + rendering (Telegram, etc.)
```

---

## Principios de Design v1.6

### 1. Representacao explicita do jogo
Rubric tactica com ~20 factores preenchidos ANTES do LLM. O LLM "ve o jogo" em vez de improvisar a partir de xG.

### 2. Reasoning estruturado
Perguntas especificas ao LLM — "Quais sao os 3 mecanismos mais decisivos?" — em vez de "pensa livremente".

### 3. Thinking model
Reasoning profundo > seguir instrucoes. Claude Opus, o3, ou GPT-5.4 com extended thinking.

### 4. Auditabilidade
Cada factor tem score, derivacao, e justificacao. Se o LLM diz "transicao e o risco", o tactical_rubric mostra se isso e suportado pelos dados.

### 5. Medir substancia, nao forma
Avaliacao pos-jogo: os mecanismos estavam certos? Nao "tinha 3 evidencias?".

---

## O que NAO muda
- Pipeline de dados (FotMob scraper, team_states, fotmob_matches)
- Caching e time-travel safety
- ML probabilistico (report.json, ml_anchor.json)
- Rendering (Telegram, X)
- Validation framework (expandido, nao substituido)
- match_signals.json (camada deterministica mantida)

---

## Roadmap

### Step 1: Tactical Rubric (FUNDACAO)
Criar `tactical_rubric.py` com ~20 factores tacticos derivados dos dados existentes.
Adicionado ao match_pack antes do LLM.

### Step 2: Thinking Model (UPGRADE)
Suportar Claude Opus 4.6 / GPT-o3 / GPT-5.4 como providers.
Multi-provider: OpenAI + Anthropic.

### Step 3: Structured Reasoning (PROFUNDIDADE)
Reestruturar prompt com rubric + perguntas de reasoning.
O LLM responde a perguntas tacticas especificas, nao improvisa livremente.

### Step 4: Web Context (FRESCURA)
Integrar search_news e press_conference no match_pack.
Tornar web context parte do pipeline, nao opcional.

### Step 5: Evaluation Upgrade (MEDICAO)
Expandir rubric pos-jogo: mecanismo correcto? game script acertado? riscos materializados?

---

## Como Medir Progresso

### Nivel 1: Qualidade Analitica (foco actual)
- Mecanismos tacticos identificados correctamente?
- Game script proximo da realidade?
- Key question relevante para o jogo?
- Narrativa especifica (nao generica)?

### Nivel 2: Forecast Accuracy (futuro proximo)
- Lean direction accuracy
- Confidence calibration
- Scenario hit rate

### Nivel 3: Betting Edge (longo prazo)
- Value bets identificados
- ROI positivo a 100+ jogos
- Edge vs mercado consistente

---

## Verificacao

Para validar v1.6 vs v1.5:
1. Escolher 5-10 jogos ja jogados com analise v1.5
2. Gerar v1.6 para os mesmos jogos (dados pre-jogo, time-travel safe)
3. Comparar lado a lado: v1.5 vs v1.6 vs resultado real
4. Medir: mecanismos correctos, game script, riscos previstos, qualidade narrativa
5. Benchmark: comparar com prompt directa no ChatGPT
