# Teste: Leeds vs Forest (2026-02-06)
## Builder: v1 + form_interpreter | Prompt: narrative_simple
## RESULTADO REAL: 3-0 Leeds ✅

---

## CONTEXTO ENRIQUECIDO (com interpretação narrativa)

```
LEEDS UNITED (Home)
- Elo: 1754
- Season: xG 1.41, xGA 1.46 (balanced)
- Form: L-D-D-D-W 
  → Interpretation: Grinding through tough period, just won last game. Building confidence.
  → Last 5 xG diff: -0.1 (creating as much as conceding)
  → Last 5 goal diff: +2 (actually winning the margins)
  → Played against strong opposition (avg Elo 1829)
- Recent PPDA: 11.5 (pressing well)
- HOME GAME

NOTTINGHAM FOREST (Away)  
- Elo: 1758
- Season: xG 1.17, xGA 1.41 (negative)
- Form: W-L-L-L-L
  → Interpretation: IN FREEFALL. 4 CONSECUTIVE LOSSES after one win.
  → Last 5 xG diff: -1.8 (getting dominated)
  → Last 5 goal diff: -5 (BLEEDING goals)
  → Also faced tough opposition (avg Elo 1841)
- Recent PPDA: 13.4 (less intense pressing)
- AWAY GAME (historically harder)

MATCHUP SUMMARY:
- Leeds stabilizing at home after tough run
- Forest in crisis mode - confidence shattered, leaking goals
- Despite similar Elo, MOMENTUM is completely different
```

---

## PROMPT (system message)

```
You are a football analyst. Based on the data below, predict the match outcome.

KEY INSIGHT: Form and momentum matter MORE than season averages when one team is in crisis.
A team with 4 consecutive losses is psychologically fragile - they concede early goals and collapse.

Return JSON:
{
  "prediction": "scoreline like 2-0 or 1-1",
  "winner": "Leeds/Forest/Draw",
  "confidence": 50-80,
  "reasoning": "2-3 sentences explaining why"
}
```

---

## ANÁLISE GERADA (gpt-4o)

```json
{
  "prediction": "2-0",
  "winner": "Leeds",
  "confidence": 75,
  "reasoning": "Leeds United are building confidence after a tough period and have just won their last game. They are playing at home and have been pressing well, which should help them capitalize on Nottingham Forest's current crisis. Forest are in freefall with four consecutive losses, indicating psychological fragility and a tendency to concede early goals. Given the contrasting momentum and Leeds' home advantage, they are likely to secure a win."
}
```

---

## AVALIAÇÃO

| Métrica | Previsto | Real | Resultado |
|---------|----------|------|-----------|
| Vencedor | Leeds | Leeds | ✅ CORRETO |
| Scoreline | 2-0 | 3-0 | 🟡 CLOSE (off by 1 goal) |
| Direction | Home Win | Home Win | ✅ CORRETO |

### Diagnóstico
- **Sucesso:** Interpretação narrativa fez o LLM entender a MAGNITUDE da crise do Forest
- **Key insight:** "IN FREEFALL", "BLEEDING goals", "psychological fragility" → LLM captou
- **Diferença dos outros prompts:** Contexto narrativo vs apenas números
- **Score accuracy:** 2-0 vs 3-0 - subestimou ligeiramente mas direcção correcta

---

## LIÇÃO APRENDIDA

```
DADOS BRUTOS          →  LLM vê "similar Elo, both struggling"  →  Empate
DADOS + NARRATIVA     →  LLM vê "Forest COLAPSO vs Leeds BUILD" →  Leeds Win
```

A camada de interpretação (`form_interpreter.py`) é CRÍTICA para o modelo entender magnitude.
