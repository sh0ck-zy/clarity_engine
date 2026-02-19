# Funcionalidades Implementadas - Clarity Engine

## 📊 1. Dashboard Streamlit (Operacional)

### 1.1. Modo Overview (Visualização de Rondas)
- Visualização de análises por época e ronda
- Detecção automática da ronda atual baseada na data
- Tabela com todas as partidas da ronda mostrando:
  - Status (Finalizado, Por jogar, Em curso)
  - Confiança da análise (%)
  - Score previsto vs Score real
  - Headline da análise
  - Versão do prompt usado
- Preview estilo Telegram com formatação HTML
- Campo de texto editável para cópia das análises
- Geração/Atualização de análises individuais com seletor de prompt
- Opção de forçar recálculo (bypass cache)

### 1.2. Modo A/B Workbench (Comparação de Prompts)
- Comparação lado-a-lado de dois prompts diferentes
- Visualização em 3 tabs por prompt:
  - 📱 Produto: Preview Telegram
  - 🧠 Cérebro: Gráfico de pesos de fatores + raciocínio
  - 📂 JSON: Resposta completa em JSON
- Integração com match_reality para mostrar resultado real quando disponível
- Histórico geral de comparações (audit trail)

### 1.3. Modo Data Simulator (Análise What-If)
- Carregamento de contexto real de uma partida
- Editor JSON para modificar contexto manualmente
- Seletor de prompt para simulação
- Execução de simulação com contexto modificado
- Visualização de resultados com preview Telegram e raciocínio Glass Box
- Persistência de resultados em session_state

## 🧠 2. Motor de Análise (ClarityEngine)

### 2.1. Construção de Contexto (MatchContextBuilder)
- Análise de identidade da equipa (métricas da época):
  - Elo atual
  - PPDA médio da época
  - Field Tilt médio
  - xG/xGA médio
  - Diferença de xG
- Análise de forma (últimos 5 jogos):
  - Resultados (W/L/D)
  - Diferença de xG acumulada
  - Diferença de golos acumulada
  - PPDA médio
  - Field Tilt médio
  - Elo médio dos oponentes
  - Dias de descanso
- Contexto adicional (estrutura para lesões, fatores externos)

### 2.2. Previsão (ClarityEngine)
- Integração com OpenAI (GPT-5.1)
- Sistema de cache em base de dados (análises anteriores)
- Suporte a múltiplos prompts (hybrid, contrarian, v3)
- Forçar refresh (bypass cache)
- Estrutura de resposta JSON padronizada:
  - Prediction (scoreline, confidence)
  - Evidence chain (market_verdict)
  - Glass box logic (reasoning, factor_weights)
  - Narrative (game_flow)
  - Risk factors
  - Headline
- Armazenamento estruturado em `analysis_reports`

### 2.3. Auditoria de Realidade (RealitySeeker)
- Verificação pós-jogo usando Google Gemini + Google Search
- Auditoria forense de estatísticas:
  - Validação de xG contra reportes qualitativos
  - Detecção de "stats lying" (xG enganoso)
  - Análise de fatores de sorte (luck_factor 0-10)
  - Identificação de eventos-chave (cartões, penalties, erros)
- Estrutura de resposta:
  - Truth vector (vencedor real, cenário tático, luck factor)
  - Stat audit (fidelidade xG, explicação)
  - Model calibration notes (o que correu mal, eventos-chave)
- Armazenamento em `match_reality`

## 📥 3. Ingestão de Dados

### 3.1. Scraper FBRef (Selenium)
- Extração de fixtures da Premier League
- Captura de scores e status dos jogos
- Extração de xG básico
- Extração de ronda (Gameweek)
- Armazenamento em `fixtures` e `team_stats`
- Tratamento de jogos agendados vs finalizados

### 3.2. Enriquecimento Understat
- Extração de métricas táticas:
  - PPDA (Passes per Defensive Action)
  - Deep Completions
  - Field Tilt (calculado a partir de deep completions)
- Mapeamento de nomes de equipas (FBRef ↔ Understat)
- Atualização de `team_stats` com dados táticos

### 3.3. Backfill de Elo
- Integração com API ClubElo
- Preenchimento de valores Elo em falta
- Mapeamento de nomes de equipas para API
- Atualização incremental apenas para datas com Elo em falta

### 3.4. Pipeline de Atualização
- Script orquestrador (`update_from_sources.py`)
- Execução sequencial: Scraper → Understat → Elo
- Opções de skip por etapa
- Execução individual por etapa

## 🗄️ 4. Base de Dados

### 4.1. Schema
- **fixtures**: Partidas (id, date, season, teams, scores, status, round)
- **team_stats**: Estatísticas por equipa por jogo (xg, xga, ppda, field_tilt, elo)
- **analysis_reports**: Cache de análises LLM (predição, confiança, recommendation, JSON completo)
- **match_reality**: Auditoria pós-jogo (score real, luck factor, narrative, eventos-chave)
- **market_odds**: Estrutura para odds de mercado (não totalmente implementado)

### 4.2. Views Analíticas
- **team_performance_view**: Junta fixtures + stats com métricas calculadas (xg_diff, points_earned)

### 4.3. Operações
- Save/Update fixtures com UPSERT
- Save/Update team_stats com UPSERT
- Queries otimizadas com índices

## 🔧 5. Scripts de Utilidade

### 5.1. Gestão de Base de Dados
- `init_db.py`: Criação do schema inicial
- `inspect_db.py`: Inspeção de tabelas e dados
- `diagnose_db.py`: Diagnóstico de problemas na BD
- `add_reports_table.py`: Adição da tabela analysis_reports
- `check_data.py`: Verificação de integridade dos dados
- `check_elo_names.py`: Verificação de mapeamento de nomes Elo

### 5.2. Processamento de Dados
- `fill_xga.py`: Preenchimento de valores xGA em falta
- `run.py`: Utilitário para reset de tabelas AI

### 5.3. Pipeline Principal
- `update_from_sources.py`: Pipeline completo de ingestão
- `main.py`: CLI principal para execução de análises

## 🚀 6. Sistema de Batch Processing

### 6.1. Previsões
- `run_specific_match`: Análise de um jogo específico (modo teste)
- `run_next_pending_batch`: Processamento em batch de jogos pendentes
- `run_round_predictions`: Processamento completo de uma ronda

### 6.2. Auditoria de Realidade
- `run_specific_reality_check`: Auditoria de um jogo específico
- `run_truth_batch`: Batch de auditoria para jogos finalizados
- `run_round_truth`: Auditoria completa de uma ronda

### 6.3. CLI (main.py)
- `--test <fixture_id>`: Teste de um jogo
- `--truth-single <fixture_id>`: Auditoria de um jogo
- `--round <N> --mode [predict|truth|both]`: Processamento por ronda
- `--batch`: Batch genérico de previsões
- `--truth`: Batch genérico de auditoria
- `--prompt <version>`: Seletor de prompt

## 📝 7. Sistema de Prompts

### 7.1. Versões Implementadas
- **hybrid** (v1): Prompts seguros estilo jornalista
- **contrarian** (v2): Prompts arriscados estilo auditor
- **v3**: Enhanced hybrid com consciência de crise

### 7.2. Gestão
- Carregamento de prompts a partir de ficheiros .txt
- Sistema de nomes e metadados
- Backward compatibility para scripts legados

## 🎨 8. Interface e Apresentação

### 8.1. Formatação Telegram
- Renderização HTML estilo bubble do Telegram
- Badges dinâmicos (CLARITY PICK, VALUE LEAN, TRAP/SKIP) baseados em confiança
- Formatação de texto rica com emojis
- Preview em tempo real

### 8.2. Visualizações
- Gráfico de barras para pesos de fatores (Glass Box Logic)
- Tabelas interativas com Streamlit
- Métricas destacadas (confiança, scores)
- Indicadores visuais de status (cores, ícones)

### 8.3. Navegação
- Sidebar com seleção de modo
- Seletor de época/ronda/jogo reutilizável
- Filtros e ordenação
- Detalhes expandíveis

## ⚙️ 9. Configuração e Ambiente

### 9.1. Gestão de Ambiente
- Suporte a `.env` para variáveis de ambiente
- Configuração de base de dados (DATABASE_URL ou fallback manual)
- API Keys (OPENAI_API_KEY, GEMINI_API_KEY)

### 9.2. Logging
- Sistema de logging para RealitySeeker
- Mensagens de console informativas durante processamento
- Tratamento de erros com mensagens claras

## 🔍 10. Funcionalidades Especiais

### 10.1. Cache Inteligente
- Cache de análises em base de dados
- Evita chamadas LLM desnecessárias
- Força refresh quando necessário (custo controlado)

### 10.2. Glass Box Logic
- Transparência no raciocínio (reasoning explicado)
- Pesos de fatores visíveis (factor_weights)
- Explicabilidade das decisões

### 10.3. Mapeamento de Nomes
- Normalização de nomes entre fontes (FBRef, Understat, Elo API)
- Mapeamento manual para casos especiais
- Tratamento de variações de nomes

### 10.4. Tratamento de Erros
- Rollback de transações em caso de erro
- Mensagens de erro descritivas
- Continuidade do processamento em batch mesmo com erros individuais

---

## 📈 Estatísticas do Sistema

- **Fontes de Dados**: 3 (FBRef, Understat, ClubElo API)
- **Modelos LLM**: 2 (OpenAI GPT-5.1, Google Gemini 2.5 Flash)
- **Tabelas Principais**: 5 (fixtures, team_stats, analysis_reports, match_reality, market_odds)
- **Modos Dashboard**: 3 (Overview, A/B Workbench, Data Simulator)
- **Versões de Prompt**: 3 (hybrid, contrarian, v3)
- **Métricas Rastreadas**: 10+ (xG, xGA, PPDA, Field Tilt, Elo, etc.)

