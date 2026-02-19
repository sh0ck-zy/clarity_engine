#!/usr/bin/env python3
"""
Compara outputs dos builders para validação
Gera matriz de comparação sem chamar API
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.builders import RobustBuilder
from src.database.config import get_connection

# Builder v1 (old)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'archive', 'old_src'))
from builder import MatchContextBuilder as OldBuilder


def get_fixtures(round_num):
    """Busca fixtures de uma ronda"""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, home_team, away_team, home_score, away_score
            FROM fixtures WHERE round = %s
            ORDER BY date
        """, (round_num,))
        rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "home": r[1], "away": r[2], "home_score": r[3], "away_score": r[4]} for r in rows]


def compare_fixture(fixture_id, home_team, away_team, home_score, away_score):
    """Compara outputs de ambos os builders para um jogo"""
    
    # Builder Robusto (novo)
    robust = RobustBuilder()
    robust_ctx = robust.build_context(fixture_id)
    robust.close()
    
    # Builder v1 (antigo)
    old = OldBuilder()
    old_ctx = old.build_context(fixture_id)
    old.close()
    
    # Extrair dados relevantes
    result = {
        "fixture": f"{home_team} vs {away_team}",
        "actual_result": f"{home_score}-{away_score}",
        "actual_winner": "H" if home_score > away_score else "A" if away_score > home_score else "D",
        "robust": extract_key_data(robust_ctx, "robust"),
        "old_v1": extract_key_data(old_ctx, "old")
    }
    
    return result


def extract_key_data(ctx, builder_type):
    """Extrai dados chave do contexto"""
    if "error" in ctx:
        return {"error": ctx["error"]}
    
    if builder_type == "robust":
        home = ctx.get("home", {})
        away = ctx.get("away", {})
        return {
            "home_form": home.get("form", {}).get("last_5_results", "?"),
            "home_gd": home.get("form", {}).get("last_5_goal_diff", 0),
            "home_label": home.get("interpretation", {}).get("form_label", "?"),
            "home_psych": home.get("interpretation", {}).get("psychological_state", "?"),
            "away_form": away.get("form", {}).get("last_5_results", "?"),
            "away_gd": away.get("form", {}).get("last_5_goal_diff", 0),
            "away_label": away.get("interpretation", {}).get("form_label", "?"),
            "away_psych": away.get("interpretation", {}).get("psychological_state", "?"),
        }
    else:  # old v1
        home = ctx.get("home", {})
        away = ctx.get("away", {})
        return {
            "home_form": home.get("form", {}).get("last_5_results", "?"),
            "home_gd": home.get("form", {}).get("last_5_goal_diff", 0),
            "home_xg_diff": home.get("form", {}).get("last_5_xg_diff", 0),
            "away_form": away.get("form", {}).get("last_5_results", "?"),
            "away_gd": away.get("form", {}).get("last_5_goal_diff", 0),
            "away_xg_diff": away.get("form", {}).get("last_5_xg_diff", 0),
        }


def print_comparison(results):
    """Imprime comparação formatada"""
    print("\n" + "=" * 100)
    print("COMPARAÇÃO DE BUILDERS - R24")
    print("=" * 100)
    
    for r in results:
        print(f"\n{'─' * 100}")
        print(f"📌 {r['fixture']} | Resultado: {r['actual_result']} ({r['actual_winner']})")
        print(f"{'─' * 100}")
        
        robust = r['robust']
        old = r['old_v1']
        
        if "error" in robust:
            print(f"   ROBUST: ERROR - {robust['error']}")
        else:
            print(f"   ROBUST Builder:")
            print(f"     Home: {robust['home_form']} (GD:{robust['home_gd']:+d}) → {robust['home_label']} | {robust['home_psych']}")
            print(f"     Away: {robust['away_form']} (GD:{robust['away_gd']:+d}) → {robust['away_label']} | {robust['away_psych']}")
        
        if "error" in old:
            print(f"   OLD v1: ERROR - {old['error']}")
        else:
            print(f"   OLD v1 Builder:")
            print(f"     Home: {old['home_form']} (GD:{old['home_gd']:+d}, xG:{old['home_xg_diff']:+.1f})")
            print(f"     Away: {old['away_form']} (GD:{old['away_gd']:+d}, xG:{old['away_xg_diff']:+.1f})")
        
        # Comparar forms
        if "error" not in robust and "error" not in old:
            home_match = robust['home_form'] == old['home_form']
            away_match = robust['away_form'] == old['away_form']
            print(f"\n   ⚖️  Forms match: Home {'✅' if home_match else '❌'} | Away {'✅' if away_match else '❌'}")


def main():
    print("🔍 Gerando comparação de builders...")
    
    # R24 fixtures
    fixtures = get_fixtures(24)
    print(f"   Encontrados {len(fixtures)} jogos em R24")
    
    results = []
    for f in fixtures:
        print(f"   Processing: {f['home']} vs {f['away']}...")
        try:
            result = compare_fixture(f['id'], f['home'], f['away'], f['home_score'], f['away_score'])
            results.append(result)
        except Exception as e:
            print(f"   ⚠️ Error: {e}")
            results.append({
                "fixture": f"{f['home']} vs {f['away']}",
                "actual_result": f"{f['home_score']}-{f['away_score']}",
                "error": str(e)
            })
    
    print_comparison(results)
    
    # Guardar JSON
    output_file = "/tmp/builder_comparison_r24.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n💾 JSON saved to: {output_file}")


if __name__ == "__main__":
    main()
