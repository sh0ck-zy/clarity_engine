# 🎯 CLARITY STATUS

**Última actualização**: 18 Feb 2026, 00:40

---

## ✅ Estado Actual: 14 Tools Operacionais

### Knowledge Graph
- **team_states**: 520 rows (20 teams × 26 rounds)
- **player_states**: 14,331 rows
- **manager_history**: 31 stints (NEW)

### Tools Implementados

| Tool | Status | Descrição |
|------|--------|-----------|
| `get_team_state` | ✅ | Snapshot 8 layers |
| `get_team_form` | ✅ | Últimos 5 jogos + xG |
| `get_team_profile` | ✅ | Estilo de jogo |
| `get_formation_history` | ✅ NEW | Lista formações com contexto |
| `get_manager_info` | ✅ NEW | Treinador + record + mudanças |
| `get_key_players` | ✅ | Jogadores-chave |
| `get_injuries_impact` | ✅ | Impacto ausências |
| `get_last_match_summary` | ✅ | Último jogo |
| `get_h2h` | ✅ FIXED | Confronto direto |
| `get_matchup_analysis` | ✅ | Previsão matchup |
| `get_psychological_state` | ✅ | Pressão/confiança |
| `search_news` | ⚠️ | Placeholder |
| `get_odds` | ⚠️ | Placeholder |
| `build_game_state_tree` | ✅ | Cenários do jogo |

### Bug Fix: Data Leakage
- `get_h2h` e `get_manager_info` não filtravam por round
- Mostravam dados "do futuro" ao analisar jogos passados
- **Corrigido**: todos os tools temporais agora filtram por `round_number`

---

## 🧪 Como Testar

```bash
cd ~/Projects/clarity_engine
source venv/bin/activate

# Teste formações
python -c "from src.tools import get_formation_history; print(get_formation_history('Manchester United').summary)"

# Teste manager
python -c "from src.tools import get_manager_info; print(get_manager_info('Manchester United').summary)"

# Teste H2H com filtro temporal
python -c "from src.tools import get_h2h; print(get_h2h('Arsenal', 'Liverpool', round_number=25).summary)"
```

---

## 📂 Ficheiros Novos

```
scripts/
└── populate_managers.py    # Extrai coaches do FotMob

src/tools/
├── manager_tools.py        # get_manager_info (NEW)
└── team_tools.py           # get_formation_history (NEW)
```

---

## 🔜 Próximos Passos

1. **News integration** — Conectar BetHub aggregator
2. **Odds integration** — Conectar API-Football  
3. **Regras do agent** — Documentar FACTOS vs ANÁLISE vs NÃO SEI
4. **Testar análises R27** — Validar com jogos futuros

---

## ⚠️ Regra Crítica

> Qualquer tool que acede a dados temporais DEVE receber `round_number` e filtrar por ele. Sem excepções.
