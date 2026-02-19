# Clarity Engine - Estado Actual

## ✅ O Que Funciona

### Builder Principal: `RobustBuilder`
```python
from src.builders import RobustBuilder

builder = RobustBuilder()
ctx = builder.build_context("2026-02-06_Leeds_United_Nott'ham_Forest")
print(builder.format_for_llm(ctx))
builder.close()
```

**Localização:** `src/builders/robust_builder.py`

**Funcionalidades:**
- ✅ Usa fixtures directamente (dados sempre actuais)
- ✅ Enriquece com xG quando disponível
- ✅ Form interpreter incluído (CRISIS/HOT/MIXED/etc)
- ✅ Funciona mesmo com team_stats incompleto

### Scripts
```bash
# Testar análise
python scripts/test_analysis.py [fixture_id]

# Ver dados da DB
python scripts/inspect_db.py
```

---

## 📊 Estado da DB

| Tabela | Registos | Estado |
|--------|----------|--------|
| fixtures | ~380 | ✅ Limpo (duplicados removidos) |
| team_stats | 532 | ⚠️ Incompleto R22-R24 |
| odds_snapshots | 2382 | ✅ OK |
| player_injuries | 3344 | ✅ OK |

### team_stats por Round
- R18-R21: 10/10 completo
- R22: 6/10 parcial
- R23: 5/10 parcial
- R24: 5/10 parcial
- R25+: por jogar

---

## 📁 Estrutura

```
clarity_engine/
├── src/
│   ├── builders/
│   │   ├── robust_builder.py    ← PRINCIPAL
│   │   ├── form_interpreter.py  ← Interpreta W/L/D em narrativa
│   │   └── __init__.py
│   ├── data/
│   │   └── fetchers/            ← API-Football fetchers
│   ├── database/
│   │   └── config.py            ← Conexão PostgreSQL
│   └── analysis/
│       └── predictor.py         ← LLM caller
├── scripts/
│   └── test_analysis.py         ← Testar análises
├── prompts/
│   ├── v4_calibrated.txt
│   └── v5_probabilistic.txt
├── testes/                      ← Resultados de testes
└── archive/
    ├── old_builders/            ← Código antigo
    └── old_src/
```

---

## 🔧 Próximos Passos

1. **Backfill team_stats** - Buscar xG para R22-R24
2. **Integrar com LLM** - Criar pipeline builder → LLM → output
3. **Dashboard** - Actualizar para usar novo builder
4. **Validação** - Testar em mais jogos

---

## 📝 Notas

- Form interpreter detecta CRISIS quando 4+ derrotas seguidas
- Builder calcula form dos últimos 5 jogos da tabela `fixtures`
- xG só é adicionado se existir em `team_stats` para esses jogos
- Nomes de equipas normalizados (usa o nome da fixtures directamente)

---

*Última actualização: 2026-02-07 01:30*
