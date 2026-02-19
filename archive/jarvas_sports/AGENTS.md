# AGENTS.md — Jarvas Sports

## Missão

Gerar intelligence pré-jogo para futebol. Perceber o jogo antes de acontecer.

## Dados

### Database
```
Host: localhost
Database: clarity_football
User: joao
```

### Tabelas Principais
```sql
-- Matches com stats completas
fotmob_matches (
    fotmob_match_id,
    home_team_name, away_team_name,
    home_score, away_score,
    round_number, season, match_date,
    stats,          -- JSONB com posse, xG, shots, etc
    shotmap,        -- shots com x, y, xG
    momentum,       -- domínio por minuto
    home_lineup, away_lineup,
    formation_home, formation_away
)

-- Player performances
fotmob_player_performances (
    match_id, player_id, player_name,
    team_id, position,
    minutes_played, rating,
    goals, assists, shots, key_passes, etc
)
```

### Como Extrair Stats
```python
import re

def extract_stat(stats_dict, key):
    """Stats estão em formato estranho, usar regex"""
    if not stats_dict or 'All' not in stats_dict:
        return None, None
    for stat_str in stats_dict['All']:
        if key in stat_str:
            match = re.search(rf"key='{key}', home='([^']*)', away='([^']*)'", stat_str)
            if match:
                return match.group(1), match.group(2)
    return None, None

# Exemplos de keys:
# 'expected_goals', 'BallPossesion', 'total_shots', 'ShotsOnTarget', 'corners'
```

## Como Gerar Intelligence

### Input
- Match: "West Ham vs Man United, R26"

### Processo
1. **Contexto**: Últimos 5 jogos de cada equipa
2. **Form**: Resultados, xG criado/concedido
3. **H2H**: Confrontos directos esta época
4. **Dinâmicas esperadas**: Quem domina, onde perigo
5. **Variância**: Quão previsível é isto?

### Output
```yaml
match: West Ham vs Man United
date: 2026-02-10

story: |
  [Narrativa de 2-3 parágrafos sobre o jogo]

dynamics:
  possession: "Man United 55-60%"
  expected_xg: "MU 1.5-1.8 | WH 0.8-1.2"
  tempo: "Médio-alto"

key_matchups:
  - "Bruno vs Rice — controlo do meio"
  - "Bowen vs Shaw — perigo na ala"

danger_zones:
  home: "Transições rápidas, Bowen"
  away: "Combinações centrais, Bruno"

variance: MEDIUM
variance_why: "Man United em forma mas fadiga possível"

players_to_watch:
  - "Bruno Fernandes"
  - "Jarrod Bowen"
```

## Validação (pós-jogo)

Depois do jogo, comparar:
- Dinâmicas previstas vs reais
- Matchups identificados foram relevantes?
- Variância estava certa?

Score: % de dimensões acertadas

## Working Directory

```
/Users/joao/Projects/clarity_engine/
```

## Comandos Úteis

```bash
# Activar venv
source .venv/bin/activate

# Conectar à DB
psql -U joao -d clarity_football

# Ver jogos de uma ronda
SELECT home_team_name, away_team_name, home_score, away_score 
FROM fotmob_matches WHERE round_number = 26;
```
