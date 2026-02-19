# Teste: Leeds vs Forest (2026-02-06)
## Builder: v2 | Prompt: v3
## RESULTADO REAL: 3-0 Leeds ✅

---

## CONTEXTO (enviado ao LLM - Builder V2)

⚠️ **NOTA:** Builder v2 usou dados DIFERENTES do v1:
- Form strings diferentes (LDWLD vs L-D-D-D-W)
- Incluiu injuries (Chris Wood, John Victor)
- Incluiu H2H e narratives

```json
{
  "home": {
    "name": "Leeds United",
    "identity": {"elo": 1754, "season_ppda": 13.7, "season_field_tilt": 44.4, "season_overall_xg": 1.23, "season_overall_xga": 1.27, "season_overall_xg_diff": -0.04},
    "form": {"last_5_results": "LDWLD", "points": 26, "position": 17, "home_record": "5W-4D-3L", "goal_diff": -11},
    "context": {"key_injuries": [], "is_home": true}
  },
  "away": {
    "name": "Nottingham Forest",
    "identity": {"elo": 1758, "season_ppda": 12.5, "season_field_tilt": 46.5, "season_overall_xg": 1.03, "season_overall_xga": 1.23, "season_overall_xg_diff": -0.21},
    "form": {"last_5_results": "DWDWL", "points": 26, "position": 17, "away_record": "4W-2D-6L", "goal_diff": -11},
    "context": {
      "key_injuries": [
        {"player": "John Victor", "reason": "Knee surgery", "games_out": 4},
        {"player": "Chris Wood", "reason": "Knee surgery", "games_out": 7}
      ],
      "is_home": false
    }
  },
  "h2h": {"matches": 1, "home_wins": 0, "draws": 0, "away_wins": 1, "pattern": "high_scoring", "last_result": "3-1"},
  "narratives": {"six_pointer": true, "derby": false, "home_stakes": "Avoiding relegation battle", "away_stakes": "Avoiding relegation battle"}
}
```

---

## ANÁLISE

❌ **NÃO GERADO** - Dados do builder v2 não correspondem aos dados correctos da DB

### Problemas identificados:
1. Form "DWDWL" para Forest vs "W-L-L-L-L" (dados reais) - **INCONSISTENTE**
2. Chris Wood listado como lesionado mas estava disponível
3. Ausência de xG diff dos últimos 5 jogos (dado crítico)

---

## LIÇÃO

Builder v2 introduziu **ruído** em vez de sinal:
- Dados de form incorrectos/desatualizados
- Lesões potencialmente erradas
- Mais features ≠ melhor output

**Recomendação:** Voltar ao builder v1 com dados limpos + adicionar form_interpreter
