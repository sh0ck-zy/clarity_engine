# Análise de Prompts - Clarity Engine

## V1 Hybrid (archive/)

**Filosofia:** Básico, transparente, sem regras especiais

### ✅ Bom
- Simples e directo
- Output estruturado (JSON)
- Pede "evidence chain" e "risk factors"
- Menciona conflitos Identity vs Form vs Matchup

### ❌ Mau
- Sem calibração de confiança (pode dar 85% fácil)
- Não menciona frequência real de empates
- Assume que "variance" explica tudo
- Genérico demais - não força pensamento crítico

**Veredicto:** Demasiado ingénuo. Vai sobrevalorizar favoritos.

---

## V2 Contrarian (archive/)

**Filosofia:** Apostar CONTRA o público, fade the hype

### ✅ Bom
- Foca em "market inefficiencies"
- Respeita xG sobre resultados recentes
- Chama equipas de "Frauds" quando métricas não batem
- Anti-hype - boa para big teams em má forma

### ❌ Mau
- Demasiado cínico - pode ignorar forma real
- Weight baixo para form (3) vs identity (8) - desactualizado
- Pode falhar em jogos "simples" por procurar value demais
- Tom agressivo pode enviesar análise

**Veredicto:** Bom para value bets, mau para previsões directas.

---

## V3 Enhanced (archive/)

**Filosofia:** Regras de "Crisis Dynamic" e "Stylistic Ambush"

### ✅ Bom
- Lógica estruturada: "Check X, if yes, then Y"
- Considera "Home Pressure Paradox" 
- Tem cenários (A/B) para diferentes situações
- Melhor que v1/v2 em situações de crise

### ❌ Mau
- Regras podem não aplicar (Elo >1800 hardcoded)
- Não menciona frequência de empates (~30%)
- Pode ser overfit a cenários específicos
- Ainda permite confidence alta sem justificação

**Veredicto:** Boas ideias mas regras demasiado rígidas.

---

## V4 Calibrated (prompts/)

**Filosofia:** Calibração estatística, respeitar base rates

### ✅ Bom
- **DRAW FREQUENCY:** Força 30-35% empates
- **CONFIDENCE SCALE:** 50-55 normal, 76+ raro
- **CHAOS FACTOR:** Reconhece variância do futebol
- Draw Detection Checklist - força pensar em empates
- Upset Detection - força pensar em surpresas
- "Anti-patterns to avoid" - evita clichés

### ❌ Mau
- Pode sobrevalorizar empates por seguir regras demais
- Checklist pode ser seguida mecanicamente
- Ainda pede scoreline específico (difícil de acertar)
- Longo demais - pode confundir o modelo

**Veredicto:** MELHOR para previsões gerais. Mais realista.

---

## V5 Probabilistic (prompts/)

**Filosofia:** Probabilidades, não winners

### ✅ Bom
- **NÃO PEDE WINNER** - pede probabilidades
- Base rates claros (Home 45%, Draw 27%, Away 28%)
- Factores que aumentam/diminuem cada outcome
- Soma DEVE ser 100% - força consistência
- "Key uncertainty" - obriga a admitir dúvida
- Mais honesto sobre incerteza

### ❌ Mau
- Não dá scoreline (se precisarmos)
- Pode ser menos "actionable" para apostas
- Requer mais processamento posterior
- Menos "exciting" que uma previsão directa

**Veredicto:** MELHOR para honestidade. Output mais útil para decisões.

---

## Resumo Comparativo

| Prompt | Realismo | Calibração | Empates | Utility |
|--------|----------|------------|---------|---------|
| V1 | ⭐⭐ | ❌ | ❌ | ⭐⭐ |
| V2 | ⭐⭐⭐ | ❌ | ❌ | ⭐⭐ |
| V3 | ⭐⭐⭐ | ⭐ | ❌ | ⭐⭐⭐ |
| V4 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| V5 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## Recomendação

**Para "saber bola" (narrativa + previsão):** V4 Calibrated

**Para decisões/probabilidades:** V5 Probabilistic

**Descartar:** V1, V2 (desactualizados)

**Guardar ideias de:** V3 (Crisis Dynamic logic)

---

## Próximo Passo

Criar **V6** que combine:
- Probabilidades do V5
- Calibração do V4
- Crisis Detection do V3
- Output híbrido (probs + narrativa curta)
