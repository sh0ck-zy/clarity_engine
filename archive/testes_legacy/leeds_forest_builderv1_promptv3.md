# Teste: Leeds vs Forest (2026-02-06)
## Builder: v1 | Prompt: v3
## RESULTADO REAL: 3-0 Leeds ✅

---

## CONTEXTO (enviado ao LLM)

```json
{
  "home": {
    "name": "Leeds United",
    "identity": {
      "elo": 1754,
      "season_ppda": 13.7,
      "season_field_tilt": 44.4,
      "season_overall_xg": 1.41,
      "season_overall_xga": 1.46,
      "season_overall_xg_diff": -0.05
    },
    "form": {
      "last_5_results": "L-D-D-D-W",
      "last_5_xg_diff": -0.1,
      "last_5_goal_diff": 2,
      "last_5_ppda": 11.5,
      "last_5_field_tilt": 48.0,
      "last_5_opponent_avg_elo": 1829,
      "days_rest": 30
    },
    "context": {
      "key_injuries": [],
      "is_home": true
    }
  },
  "away": {
    "name": "Nott'ham Forest",
    "identity": {
      "elo": 1758,
      "season_ppda": 12.5,
      "season_field_tilt": 46.5,
      "season_overall_xg": 1.17,
      "season_overall_xga": 1.41,
      "season_overall_xg_diff": -0.24
    },
    "form": {
      "last_5_results": "W-L-L-L-L",
      "last_5_xg_diff": -1.8,
      "last_5_goal_diff": -5,
      "last_5_ppda": 13.4,
      "last_5_field_tilt": 46.3,
      "last_5_opponent_avg_elo": 1841,
      "days_rest": 31
    },
    "context": {
      "key_injuries": [],
      "is_home": false
    }
  },
  "market_odds": {
    "home_win": null,
    "draw": null,
    "away_win": null
  }
}
```

---

## ANÁLISE GERADA (gpt-4o)

```json
{
    "headline": "Leeds and Forest in a Battle of Strugglers",
    "narrative": {
        "game_flow": "Leeds will try to control the game, but Forest aims to exploit any defensive lapses.",
        "tactical_dynamic": "Anxious Possession vs Defensive Resilience."
    },
    "prediction": {
        "scoreline": "1-1",
        "total_goals": "Under 2.5",
        "confidence": 60,
        "dominant_team_xg": 1.4
    },
    "evidence_chain": {
        "observed_stats": "Leeds' last 5 xG Diff: -0.1, Forest's last 5 xG Diff: -1.8, Leeds' field tilt: 48.0%",
        "context_rebuttal": "Leeds' xG is decent but their form is inconsistent, and Forest's defense can hold firm.",
        "market_verdict": "Draw No Bet on Leeds, Under 2.5 goals."
    },
    "risk_factors": ["Leeds' inconsistent form", "Forest's recent defensive struggles", "Potential for a low-scoring draw"],
    "glass_box_logic": {
        "primary_factor": "Form",
        "factor_weights": { "identity": 5, "form": 8, "matchup": 6 },
        "reasoning": "Leeds' slight edge in form and home advantage is balanced by Forest's potential to counter, leading to a likely draw."
    }
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
- **Problema principal:** O modelo interpretou Forest como tendo "Defensive Resilience" quando os dados mostram COLAPSO total (W-L-L-L-L, -5 GD, -1.8 xG diff)
- **Root cause:** Dados numéricos não transmitem magnitude/urgência. O LLM não captou que Forest está em CRISE.
- **Solução:** Adicionar camada de interpretação narrativa aos dados (form_interpreter.py)
