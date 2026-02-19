# Resumo dos Testes - Leeds vs Forest (2026-02-06)

## Resultado Real: **3-0 Leeds** ✅

---

## ⚠️ PROBLEMA CRÍTICO: DADOS INCOMPLETOS

Antes de avaliar modelos, descobrimos que os **dados estavam errados**.

### O que o Builder usou vs Realidade

| Equipa | Form no Builder | Form Real | Diferença |
|--------|-----------------|-----------|-----------|
| Leeds | L-D-D-D-W | **D-L-W-D-L** | ❌ Completamente diferente |
| Forest | W-L-L-L-L | **L-W-D-W-D** | ❌ Completamente diferente |

### Root Cause
- `team_stats` só tem dados até R21 (6 Jan 2026)
- R22-R24 (17 Jan - 1 Feb) **não têm stats**
- Builder calculou form de R17-R21, não R20-R24

---

## Implicações

### O modelo NÃO errou
A narrativa "Forest em colapso" era baseada em dados antigos. Com dados reais:
- Forest: 2W 2D 1L nos últimos 5 (forma mista)
- Leeds: 1W 2D 2L nos últimos 5 (forma mista)

### Próximos passos
1. ✅ Backfill team_stats para R22-R24
2. ✅ Dedupe fixtures (remover duplicados)
3. ✅ Normalizar nomes de equipas
4. ⬜ Re-testar com dados correctos

---

## Testes (Inválidos devido a dados errados)

| Builder | Prompt | Previsão | Avaliação |
|---------|--------|----------|-----------|
| v1 | v3 | 1-1 | ⚠️ Dados errados |
| v1 | v4 | 1-1 | ⚠️ Dados errados |
| v1 | narrative | 2-0 | ⚠️ Dados errados |
| v2 | * | - | ⚠️ Dados errados |

**Todos os testes são inválidos porque usaram dados incompletos.**

---

## Lição

> "Garbage in, garbage out."

Antes de avaliar/ajustar modelos, **garantir qualidade dos dados**.

Ver `AUDIT_DADOS.md` para detalhes completos.
