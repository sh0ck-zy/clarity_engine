# Auditoria de Dados - 2026-02-07

## Problemas Encontrados

### 1. team_stats Incompleto ❌
**Impacto:** Form calculada está errada

```
Forest tinha form real: L-W-D-W-D (R20-R24)
Builder mostrou: W-L-L-L-L (R17-R21)

Leeds tinha form real: D-L-W-D-L (R20-R24)
Builder mostrou: L-D-D-D-W (R16-R20?)
```

**Rounds sem team_stats:**
- R22 (17 Jan)
- R23 (25-26 Jan)
- R24 (31 Jan - 1 Feb)

### 2. Fixtures Duplicados ❌
Cada jogo aparece 2x com nomes diferentes:

| Versão 1 | Versão 2 |
|----------|----------|
| Leeds United | Leeds |
| Nott'ham Forest | Forest |
| Newcastle Utd | Newcastle |

Um tem `round`, outro não.

### 3. Nomes Inconsistentes ❌
- `team_stats.team_name = 'Nott'ham Forest'`
- `fixtures.home_team` usa vários formatos

---

## Verificação de Dados Reais (Wikipedia)

### Leeds United - Últimos 5 antes de R25
| Round | Data | Adversário | Score | Resultado |
|-------|------|------------|-------|-----------|
| R20 | 4 Jan | Man Utd (H) | 1-1 | D |
| R21 | 7 Jan | Newcastle (A) | 3-4 | L |
| R22 | 17 Jan | Fulham (H) | 1-0 | W |
| R23 | 26 Jan | Everton (A) | 1-1 | D |
| R24 | 31 Jan | Arsenal (H) | 0-4 | L |

**Form Real: D-L-W-D-L**

### Nottingham Forest - Últimos 5 antes de R25
| Round | Data | Adversário | Score | Resultado |
|-------|------|------------|-------|-----------|
| R20 | 3 Jan | Aston Villa (A) | 1-3 | L |
| R21 | 6 Jan | West Ham (A) | 2-1 | W |
| R22 | 17 Jan | Arsenal (H) | 0-0 | D |
| R23 | 25 Jan | Brentford (A) | 2-0 | W |
| R24 | 1 Feb | Crystal Palace (H) | 1-1 | D |

**Form Real: L-W-D-W-D**

---

## Acções Necessárias

### Prioridade 1: Backfill team_stats
```bash
# Fetch stats para R22-R24
python scripts/fetch_team_stats.py --rounds 22,23,24
```

### Prioridade 2: Dedupe fixtures
```sql
-- Manter apenas fixtures com round preenchido
DELETE FROM fixtures 
WHERE round IS NULL 
  AND id IN (
    SELECT f1.id FROM fixtures f1
    JOIN fixtures f2 ON f1.date = f2.date 
      AND f1.home_team ILIKE '%' || SPLIT_PART(f2.home_team, ' ', 1) || '%'
    WHERE f2.round IS NOT NULL
  );
```

### Prioridade 3: Normalizar nomes
Criar tabela `team_aliases`:
```sql
CREATE TABLE team_aliases (
  canonical_name TEXT PRIMARY KEY,
  aliases TEXT[]
);

INSERT INTO team_aliases VALUES
  ('Leeds United', ARRAY['Leeds', 'Leeds Utd']),
  ('Nottingham Forest', ARRAY['Nott''ham Forest', 'Forest']),
  ('Newcastle United', ARRAY['Newcastle Utd', 'Newcastle']);
```

---

## Conclusão

**O modelo NÃO estava errado. Os DADOS estavam incompletos.**

A análise "Leeds em crise" vs "Forest a colapsar" foi baseada em dados de 3 semanas antes, não nos dados actuais.

Com dados correctos:
- Forest: L-W-D-W-D (forma mista, não em crise)
- Leeds: D-L-W-D-L (forma mista também)

O jogo era mais equilibrado do que os dados mostravam.
