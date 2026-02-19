# TASK.md — Current Sprint

## Goal
Build V0.1 of Clarity Engine: an agentic system that generates pre-match football intelligence.

---

## Current Phase: 1.5 — Enhanced Tools ✅

### Completed (17-18 Feb)

#### 12 MVP Tools ✅
All working, tested, documented in `docs/TOOLS.md`

#### New Tools ✅
| Tool | Purpose |
|------|---------|
| `get_formation_history` | Lista formações com contexto (adversário, resultado) |
| `get_manager_info` | Treinador actual, record, mudanças |

#### Manager Data ✅
- Tabela `manager_history` criada
- Script `scripts/populate_managers.py`
- 31 manager stints extraídos do FotMob

#### Data Leakage Fix ✅
- `get_h2h` agora filtra por `round_number`
- `get_manager_info` calcula `is_current` dinamicamente
- **Regra:** Todos os tools temporais DEVEM filtrar por round

---

## Next Phase: 2 — Integration & Rules

### 2.1 Agent Rules (Prioridade Alta)

**Problema:** Agent (Claude) inventa factos não suportados pelos tools.

**Solução:**
1. [ ] Documentar regras em `docs/AGENT_RULES.md`
2. [ ] Separação interna: FACTOS (tools) / ANÁLISE (inferência) / NÃO SEI (gaps)
3. [ ] Checklist antes de gerar output

### 2.2 News Integration

**Objectivo:** Conectar ao BetHub news aggregator

**Tasks:**
1. [ ] Copiar/adaptar código de `~/Projects/bethub/webapp/src/lib/news-aggregator/`
2. [ ] Criar `search_news` tool funcional
3. [ ] Filtrar: só factos (lesões, suspensões, mudanças)
4. [ ] Source quality scoring

### 2.3 Odds Integration

**Objectivo:** Conectar API-Football para odds

**Tasks:**
1. [ ] Verificar endpoint `/odds` do API-Football
2. [ ] Criar `get_odds` tool funcional
3. [ ] Mapear `fotmob_match_id` → `fixture_id`

---

## Decisões de Design (18 Feb)

| Decisão | Escolha | Razão |
|---------|---------|-------|
| Formação | Lista recente, não moda | Agent detecta padrões |
| Métricas | Valores brutos, não labels | Agent interpreta |
| Treinador | Essencial, não opcional | Muda tudo |
| Temporal | Sempre filtrar por round | Evitar data leakage |

---

## Quick Reference

```bash
# Activate
cd ~/Projects/clarity_engine && source venv/bin/activate

# Test new tools
python -c "from src.tools import get_formation_history; print(get_formation_history('Arsenal').summary)"
python -c "from src.tools import get_manager_info; print(get_manager_info('Chelsea').summary)"

# Full analysis
python -c "
from src.tools import *
# ... call all tools with round_number=25
"
```

---

*Last updated: 2026-02-18 00:40*
