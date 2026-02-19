# RESUMO J26 - Análise de Prompts

**Data da análise:** 2026-02-15 00:16

## Matriz de Previsões

| Jogo | Real | v4_calibrated | v5_probabilistic | v6_know_ball |
|------|------|---------------|------------------|-------------|
| West Ham vs Man United | D | ✅ D | ❌ A | ❌ A |
| Man City vs Fulham | H | ❌ D | ✅ H | ✅ H |
| Sunderland vs Liverpool | A | ✅ A | ✅ A | ✅ A |
| Brentford vs Arsenal | D | ✅ D | ❌ A | ❌ A |
| Aston Villa vs Brighton | H | ❌ D | ✅ H | ✅ H |

## Pontuação Final

| Prompt | Acertos | % |
|--------|---------|---|
| v4_calibrated | 3/5 | 60% |
| v5_probabilistic | 3/5 | 60% |
| v6_know_ball | 3/5 | 60% |

## Análise por Jogo

### West Ham vs Man United
**Real:** 1-1 (D)

- **v4_calibrated:** ✅ D (1-1)
- **v5_probabilistic:** ❌ A (H:20% D:25% A:55%)
- **v6_know_ball:** ❌ A (0-2)

### Man City vs Fulham
**Real:** 3-0 (H)

- **v4_calibrated:** ❌ D (1-1)
- **v5_probabilistic:** ✅ H (H:55% D:25% A:20%)
- **v6_know_ball:** ✅ H (2-0)

### Sunderland vs Liverpool
**Real:** 0-1 (A)

- **v4_calibrated:** ✅ A (1-2)
- **v5_probabilistic:** ✅ A (H:20% D:25% A:55%)
- **v6_know_ball:** ✅ A (0-2)

### Brentford vs Arsenal
**Real:** 1-1 (D)

- **v4_calibrated:** ✅ D (1-1)
- **v5_probabilistic:** ❌ A (H:25% D:30% A:45%)
- **v6_know_ball:** ❌ A (0-1)

### Aston Villa vs Brighton
**Real:** 1-0 (H)

- **v4_calibrated:** ❌ D (1-1)
- **v5_probabilistic:** ✅ H (H:50% D:30% A:20%)
- **v6_know_ball:** ✅ H (2-1)

---

## 🔍 Análise Qualitativa

### Padrões Observados

**v4_calibrated (3/5 = 60%)**
- ✅ Excelente em EMPATES: acertou West Ham 1-1 e Brentford 1-1
- ❌ Tendência para empate: errou Man City e Aston Villa prevendo empates
- 📊 Prompt mais "conservador" - calibrado para ~30% draws

**v5_probabilistic (3/5 = 60%)**
- ✅ Bom em vitórias claras (City, Villa, Liverpool)
- ❌ Não previu nenhum empate nos 5 jogos
- 📊 Abordagem probabilística mais agressiva para favoritos

**v6_know_ball (3/5 = 60%)**
- ✅ Mesmo perfil do v5 - acertou as mesmas 3 partidas
- ❌ Também não previu empates (mesmo com foco em psicologia)
- 📊 Confiança mais alta (65% vs 55%) mas mesmos resultados

### Pontos Chave

| Insight | Observação |
|---------|------------|
| **Empates são o problema** | v5 e v6 erraram os 2 empates; v4 acertou ambos |
| **Favoritos** | Todos acertaram Liverpool fora |
| **Jogos "fechados"** | v4 melhor em prever 1-1 |
| **Overconfidence** | v6 com 65% confiança falhou em West Ham |

### Conclusões

1. **Nenhum prompt domina** - Todos com 60% em amostra pequena
2. **Trade-off empate vs vitória** - v4 bom em empates mas conservador demais
3. **v5 e v6 idênticos nos resultados** - Abordagem "know ball" não melhorou a previsão
4. **Draw detection precisa melhorar** - v5/v6 deveriam ter calibração para empates

### Sugestões de Melhoria

- **v5/v6**: Adicionar regra explícita: se draw_pct > 25%, considerar seriamente D
- **v4**: Reduzir viés para empate em jogos com favorito claro
- **Híbrido**: Usar v4 para jogos equilibrados, v5/v6 para favoritos claros

---

*Análise gerada automaticamente pelo Clarity Engine*
