#!/usr/bin/env python3
"""
Test analysis script - Gera análise para um jogo
Uso: python scripts/test_analysis.py [fixture_id]
"""

import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.builders import RobustBuilder

def main():
    # Default fixture ou argumento
    fixture_id = sys.argv[1] if len(sys.argv) > 1 else "2026-02-06_Leeds_United_Nott'ham_Forest"
    
    print(f"🔍 Analyzing: {fixture_id}\n")
    
    builder = RobustBuilder()
    ctx = builder.build_context(fixture_id)
    
    if "error" in ctx:
        print(f"❌ Error: {ctx['error']}")
        return 1
    
    # Mostrar contexto
    print("=" * 60)
    print(builder.format_for_llm(ctx))
    print("=" * 60)
    
    # Mostrar qualidade dos dados
    print(f"\n📊 Data Quality:")
    print(f"   Home xG data: {'✅' if ctx['data_quality']['home_has_xg'] else '❌'}")
    print(f"   Away xG data: {'✅' if ctx['data_quality']['away_has_xg'] else '❌'}")
    
    # Guardar JSON para debugging
    output_file = f"/tmp/clarity_{fixture_id.replace('/', '_')}.json"
    with open(output_file, 'w') as f:
        json.dump(ctx, f, indent=2, default=str)
    print(f"\n💾 Full context saved to: {output_file}")
    
    builder.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
