# Matriz de Comparação - R24 (31 Jan - 2 Feb 2026)

## Validação de Builders

| Builder | Fonte de Dados | Status |
|---------|---------------|--------|
| **Robust** | fixtures (actual) | ✅ CORRECTO |
| Old v1 | team_stats (desactualizado) | ❌ INCORRECTO |

---

## R24 - Jogos e Contexto

### 1. Brighton 1-1 Everton (D)
| | Robust | Verificado |
|---|--------|------------|
| Brighton | D-W-D-D-L (GD:+1) STAGNANT | ✅ |
| Everton | W-L-D-W-D (GD:+1) MIXED | ✅ |

---

### 2. Liverpool 4-1 Newcastle (H)
| | Robust | Verificado |
|---|--------|------------|
| Liverpool | D-D-D-D-L (GD:-1) STAGNANT | ✅ |
| Newcastle | W-W-W-D-L (GD:+3) GOOD | ✅ |

**Nota:** Liverpool em má forma mas ganhou 4-1. Newcastle boa forma mas perdeu.

---

### 3. Wolves 0-2 Bournemouth (A)
| | Robust | Verificado |
|---|--------|------------|
| Wolves | D-W-D-D-L (GD:+1) STAGNANT | ✅ |
| Bournemouth | D-L-W-D-W (GD:+1) STABILIZING | ✅ |

---

### 4. Chelsea 3-2 West Ham (H)
| | Robust | Verificado |
|---|--------|------------|
| Chelsea | D-D-L-W-W (GD:+3) MIXED | ✅ |
| West Ham | D-L-L-W-W (GD:-1) MIXED | ✅ |

---

### 5. Leeds 0-4 Arsenal (A)
| | Robust | Verificado |
|---|--------|------------|
| Leeds | D-D-L-W-D (GD:+0) STAGNANT | ✅ |
| Arsenal | W-W-D-D-L (GD:+3) MIXED | ✅ |

**Nota:** Arsenal não em forma brilhante (L no último) mas goleou 4-0.

---

### 6. Aston Villa 0-1 Brentford (A)
| | Robust | Verificado |
|---|--------|------------|
| Villa | L-W-D-L-W (GD:+0) STABILIZING | ✅ |
| Brentford | D-W-W-L-L (GD:+1) MIXED | ✅ |

---

### 7. Man Utd 3-2 Fulham (H)
| | Robust | Verificado |
|---|--------|------------|
| Man Utd | D-D-D-W-W (GD:+3) STAGNANT | ✅ |
| Fulham | D-D-W-L-W (GD:+1) STABILIZING | ✅ |

---

### 8. Forest 1-1 Crystal Palace (D)
| | Robust | Verificado |
|---|--------|------------|
| Forest | L-L-W-D-W (GD:-1) STABILIZING | ✅ |
| Palace | D-L-D-L-L (GD:-5) POOR | ✅ |

---

### 9. Tottenham 2-2 Man City (D)
| | Robust | Verificado |
|---|--------|------------|
| Spurs | D-D-L-L-D (GD:-2) STAGNANT | ✅ |
| City | D-D-D-L-W (GD:+0) STABILIZING | ✅ |

---

### 10. Sunderland 3-0 Burnley (H)
| | Robust | Verificado |
|---|--------|------------|
| Sunderland | D-D-L-W-L (GD:-4) MIXED | ✅ |
| Burnley | L-L-D-D-D (GD:-4) STAGNANT | ✅ |

---

## Observações

1. **Robust Builder funciona** - todos os forms verificados correctos
2. **Old v1 obsoleto** - usa team_stats que está desactualizado
3. **Futebol é imprevisível:**
   - Liverpool má forma → ganha 4-1
   - Newcastle boa forma → perde 1-4
   - Arsenal forma mista → ganha 4-0

---

## Próximos Passos

1. ✅ Descartar Old v1 - usar apenas Robust
2. ⬜ Testar prompts (v3, v4, v5) com Robust
3. ⬜ Adicionar Leeds vs Forest (R25) à análise

---

## R25 - Leeds 3-0 Forest

| | Robust | Real |
|---|--------|------|
| Leeds | D-L-W-D-L (GD:-4) MIXED | ✅ Verificado |
| Forest | L-W-D-W-D (GD:+1) MIXED | ✅ Verificado |

**Contexto:**
- Leeds: "UNDER PRESSURE - need a result"
- Forest: "NEUTRAL - no psychological edge"
- Resultado: **3-0 Leeds** (home win)

**Análise:**
- Dados NÃO indicavam goleada (ambos MIXED)
- Leeds em casa + under pressure = motivação extra?
- Forest sem urgência = complacência?
- **Lesson:** Form labels não prevêem magnitude
