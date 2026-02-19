# Teste: Leeds vs Forest (2026-02-06)
## Builder: v1 | Prompt: v4_calibrated
## RESULTADO REAL: 3-0 Leeds ✅

---

## CONTEXTO (enviado ao LLM)

```json
{
  "home": {
    "name": "Leeds United",
    "identity": {"elo": 1754, "season_ppda": 13.7, "season_field_tilt": 44.4, "season_overall_xg": 1.41, "season_overall_xga": 1.46, "season_overall_xg_diff": -0.05},
    "form": {"last_5_results": "L-D-D-D-W", "last_5_xg_diff": -0.1, "last_5_goal_diff": 2, "last_5_ppda": 11.5, "last_5_field_tilt": 48.0, "last_5_opponent_avg_elo": 1829, "days_rest": 30},
    "context": {"key_injuries": [], "is_home": true}
  },
  "away": {
    "name": "Nott'ham Forest",
    "identity": {"elo": 1758, "season_ppda": 12.5, "season_field_tilt": 46.5, "season_overall_xg": 1.17, "season_overall_xga": 1.41, "season_overall_xg_diff": -0.24},
    "form": {"last_5_results": "W-L-L-L-L", "last_5_xg_diff": -1.8, "last_5_goal_diff": -5, "last_5_ppda": 13.4, "last_5_field_tilt": 46.3, "last_5_opponent_avg_elo": 1841, "days_rest": 31},
    "context": {"key_injuries": [], "is_home": false}
  },
  "market_odds": {"home_win": null, "draw": null, "away_win": null}
}
```

---

## ANÁLISE GERADA (gpt-4o)

```json
{
    "headline": "Leeds and Forest Battle of Strugglers",
    "chaos_assessment": {
        "draw_triggers": ["Similar Elo ratings", "Both teams in mixed form", "Leeds' 3 draws in last 5"],
        "upset_triggers": ["Forest's counter-attacking ability"],
        "variance_level": "Medium"
    },
    "narrative": {
        "game_flow": "0-0 at halftime, both teams pushing for a goal in second half, ultimately settling for a draw.",
        "tactical_dynamic": "Leeds' pressing style against Forest's more conservative approach.",
        "key_battle": "Leeds' midfield pressing against Forest's ability to transition quickly through Brennan Johnson."
    },
    "prediction": {
        "scoreline": "1-1",
        "result": "D",
        "total_goals": "Under 2.5 - Both teams have struggled to score consistently",
        "confidence": 55,
        "confidence_reasoning": "Leeds' recent form suggests they can hold Forest, but neither team has shown enough to be confident of a win."
    },
    "glass_box_logic": {
        "primary_factor": "Form",
        "factor_weights": { "identity": 5, "form": 7, "matchup": 6, "chaos": 4 },
        "reasoning": "Form is the strongest indicator here due to both teams' recent performances and similar Elo ratings."
    },
    "evidence_chain": {
        "for_prediction": [
            "Leeds' last 5 results include 3 draws",
            "Forest's recent poor form with 4 losses",
            "Similar Elo ratings indicating evenly matched teams"
        ],
        "against_prediction": [
            "Leeds' slightly better recent goal difference",
            "Forest's ability to counter-attack could exploit Leeds",
            "Leeds' home advantage might tip the balance"
        ],
        "market_verdict": "Draw seems reasonable given the teams' form and similar ratings."
    },
    "risk_factors": [
        "Potential for a red card disrupting the game",
        "In-game injuries affecting team dynamics",
        "Forest's counter-attacking threat"
    ]
}
```

---

## AVALIAÇÃO

| Métrica | Previsto | Real | Resultado |
|---------|----------|------|-----------|
| Vencedor | Draw | Leeds | ❌ ERRADO |
| Scoreline | 1-1 | 3-0 | ❌ ERRADO |
| Total Goals | Under 2.5 | Over (3) | ❌ ERRADO |

### Diagnóstico
- **Problema principal:** Prompt v4 tem regras de "Draw Detection" que fizeram o modelo sobrevalorizar empate
- **Observação:** O modelo viu "Forest's recent poor form with 4 losses" mas mesmo assim previu empate
- **Root cause:** O checklist de draws fez o modelo focar em "similar Elo" ignorando o COLAPSO total do Forest
- **Ironia:** O modelo listou "Leeds' home advantage might tip the balance" como contra-argumento... e era verdade!
- **Solução:** Adicionar camada de interpretação que diga explicitamente "CRISIS MODE" vs "STABILIZING"
