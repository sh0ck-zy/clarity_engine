# TOOLS.md — Jarvas Sports

## Scripts Disponíveis

### get_match_context.py
Puxa contexto para um jogo (forma, xG, H2H).

```bash
cd ~/Projects/clarity_engine
source .venv/bin/activate
python jarvas_sports/tools/get_match_context.py "Home Team" "Away Team" <round>
```

Exemplo:
```bash
python jarvas_sports/tools/get_match_context.py "Arsenal" "Liverpool" 27
```

## Database Queries Úteis

### Ver jogos de uma ronda
```sql
SELECT home_team_name, away_team_name, home_score, away_score, match_date
FROM fotmob_matches 
WHERE round_number = 27
ORDER BY match_date;
```

### Ver stats detalhadas de um jogo
```sql
SELECT stats, shotmap, momentum
FROM fotmob_matches 
WHERE home_team_name = 'Arsenal' AND round_number = 26;
```

### Top performers de uma ronda
```sql
SELECT player_name, team_id, rating, goals, assists
FROM fotmob_player_performances
WHERE match_id IN (SELECT fotmob_match_id FROM fotmob_matches WHERE round_number = 26)
ORDER BY rating DESC
LIMIT 10;
```
