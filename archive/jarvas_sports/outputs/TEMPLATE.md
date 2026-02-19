# Match Intelligence Template

## Pre-Match (guardar antes do jogo)

```yaml
match: [Home] vs [Away]
round: XX
date: YYYY-MM-DD
generated_at: YYYY-MM-DD HH:MM

# A história deste jogo
story: |
  [2-3 parágrafos explicando o contexto e o que esperar]

# Dinâmicas esperadas
dynamics:
  possession: "[Team] XX-XX%"
  expected_xg: "[Team1] X.X-X.X | [Team2] X.X-X.X"
  tempo: "Alto / Médio / Baixo"

# Batalhas que vão decidir o jogo
key_matchups:
  - "[Player1] vs [Player2] — [porquê]"
  - "[Player1] vs [Player2] — [porquê]"

# De onde vem o perigo
danger_zones:
  home: "[Descrição]"
  away: "[Descrição]"

# Cenários
scenarios:
  if_home_scores_first: "[O que acontece]"
  if_away_scores_first: "[O que acontece]"
  if_0_0_at_60: "[O que acontece]"

# Quão previsível é isto?
variance: LOW / MEDIUM / HIGH
variance_why: "[Explicação]"

# Jogadores a observar
players_to_watch:
  home: ["Player1", "Player2"]
  away: ["Player1", "Player2"]
```

## Post-Match (validação)

```yaml
match: [Home] vs [Away]
actual_result: X-X
validated_at: YYYY-MM-DD

# Comparação
validation:
  dynamics:
    possession:
      predicted: "[Team] XX%"
      actual: "[Team] XX%"
      verdict: ✅/❌
    
    xg:
      predicted: "X.X - X.X"
      actual: "X.X - X.X"
      verdict: ✅/❌

  key_matchups:
    - matchup: "[desc]"
      verdict: ✅/❌
      notes: "[o que aconteceu]"

  variance:
    predicted: MEDIUM
    was_upset: true/false
    verdict: ✅/❌

# Score geral
overall_score: XX%

# O que aprendemos
learnings:
  - "[Insight 1]"
  - "[Insight 2]"
```
