# 🧠 PHASE 1: Football Intelligence System

## Objectivo
Transformar Clarity de "stats engine" para "AI que entende futebol".

---

## O Problema (Identificado às 4:30 AM)

O sistema actual:
- ✅ Tem stats (xG, Elo, forma)
- ❌ Não sabe COMO as equipas jogam
- ❌ Não contextualiza lesões (adaptação)
- ❌ Não identifica jogadores decisivos
- ❌ Não captura narrativas

## A Solução: 6 Pilares

Baseado em reverse engineering de análises reais (Liverpool-City, Arsenal-Chelsea):

| Pilar | Pergunta | Fonte |
|-------|----------|-------|
| 1. Perfil Táctico | Como jogam? | API + Agent |
| 2. Vulnerabilidades | O que explorar? | Agent + Stats |
| 3. Jogadores Decisivos | Quem decide? | API + Agent |
| 4. Contexto Ausências | Impacto real? | TM + Lógica |
| 5. Narrativas | Qual a história? | Agent |
| 6. Estado Actual | Como estão agora? | API + Calculado |

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                    CLARITY ENGINE V3                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │ API Football │  │ Transfermarkt│  │ Agent Search│      │
│  │   (Stats)    │  │  (Injuries)  │  │  (Tactics)  │      │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘      │
│         │                │                │              │
│         └────────────────┼────────────────┘              │
│                          ▼                               │
│              ┌───────────────────┐                       │
│              │  Context Builder  │                       │
│              │       V3          │                       │
│              └─────────┬─────────┘                       │
│                        ▼                                 │
│              ┌───────────────────┐                       │
│              │  Match Context V3 │                       │
│              │   (6 Pilares)     │                       │
│              └─────────┬─────────┘                       │
│                        ▼                                 │
│              ┌───────────────────┐                       │
│              │  Analysis Engine  │                       │
│              │   (LLM + Rules)   │                       │
│              └─────────┬─────────┘                       │
│                        ▼                                 │
│              ┌───────────────────┐                       │
│              │   Final Output    │                       │
│              │  (Análise Real)   │                       │
│              └───────────────────┘                       │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Ficheiros a Criar/Modificar

### Já Feito ✅
- [x] `src/models/match_context_v3.py` — Schema com 6 pilares
- [x] `src/data/team_registry.py` — Nomes canónicos (Phase 0)

### Em Progresso 🔄
- [ ] `src/builders/context_builder_v3.py` — Novo builder
- [ ] `src/builders/absence_analyzer.py` — Lógica de adaptação
- [ ] `src/agents/tactical_agent.py` — Busca perfil táctico
- [ ] `src/agents/narrative_agent.py` — Busca storylines

### Próximo 📋
- [ ] `src/agents/player_agent.py` — Jogadores decisivos
- [ ] `src/analysis/matchup_analyzer.py` — Análise táctica do confronto
- [ ] `prompts/v6_football_intelligence.txt` — Nova prompt

---

## Lógica de Adaptação de Lesões

```python
def calculate_real_impact(absence: Absence) -> float:
    """
    Ajusta o impacto de uma ausência baseado na adaptação da equipa.
    
    Se jogador está fora há 3+ jogos, equipa já se adaptou.
    O impacto real é menor porque os resultados recentes
    já reflectem a ausência.
    """
    base_impact = absence.base_impact  # 0-10
    games_missed = absence.games_missed
    
    if games_missed >= 5:
        # Totalmente adaptados
        return base_impact * 0.1
    elif games_missed >= 3:
        # Maioritariamente adaptados
        return base_impact * 0.3
    elif games_missed >= 1:
        # Parcialmente adaptados
        return base_impact * 0.7
    else:
        # Ausência nova, impacto total
        return base_impact
```

---

## Agent Search: Queries Exemplo

### Para Perfil Táctico:
```
"[Team] tactical analysis 2025-26 formation playing style"
"[Team] how do they play under [Manager]"
"[Team] defensive setup pressing intensity"
```

### Para Vulnerabilidades:
```
"[Team] defensive weaknesses 2025-26"
"How to beat [Team] tactics"
"[Team] goals conceded analysis"
```

### Para Narrativas:
```
"[Team A] vs [Team B] rivalry history"
"[Team] relegation battle pressure"
"[Player] vs former club storyline"
```

---

## Próximos Passos (Quando Boss Acordar)

1. **Resolver APIs** — Billing OpenAI/Google
2. **Validar Schema V3** — Boss aprova estrutura?
3. **Priorizar** — Fix sistema vs análises manuais para MW25?
4. **Testar com Leeds vs Forest** — Usar novo schema

---

## Notas

- Leeds vs Forest é às 20:00 de hoje (6 Feb)
- Liverpool vs City é domingo às 16:30
- Boss quer análises que "entendam bola", não spreadsheets
