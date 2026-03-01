#!/usr/bin/env python
"""Generate complete match analysis with absence context."""

import json
import os
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

from openai import OpenAI
from src.analysis.context_builder_v2 import ContextBuilderV2
from src.builders.absence_analyzer import AbsenceAnalyzer


SYSTEM_PROMPT = """You are a football analyst who UNDERSTANDS THE GAME, not just stats.

Analyze this match considering:
1. TACTICAL CONTEXT - How do these teams play? What's the matchup?
2. FORM & MOMENTUM - Not just results, but trajectory and confidence
3. ABSENCES - Note the "team_adapted" flag. If True, the team has played 3+ games without this player, so they've adjusted. Real impact is already discounted.
4. STAKES - What does this game mean for each team?
5. KEY BATTLES - What individual matchups will decide this?

OUTPUT in Portuguese (pt-PT), structured as:

## 🎯 VEREDICTO
[One sentence prediction with confidence]

## 📊 PROBABILIDADES
Home Win: X%
Draw: X%  
Away Win: X%
Over 2.5: X%
BTTS: X%

## ⚽ ANÁLISE TÁCTICA
[How will these teams set up? What's the tactical matchup?]

## 🔑 FACTORES DECISIVOS
[3-4 bullet points on what will decide this match]

## 💰 APOSTA RECOMENDADA
[One specific bet with reasoning]

Be opinionated. Take a stance. No hedging."""


def generate_analysis(fixture_id: str, match_date: date):
    """Generate complete analysis for a fixture."""
    
    # Build base context
    print(f"Building context for {fixture_id}...")
    builder = ContextBuilderV2()
    context = builder.build_context(fixture_id)
    
    if not context:
        print("Failed to build context")
        return None
    
    from dataclasses import asdict
    ctx = asdict(context)
    print(f"✅ Context built (coverage: {ctx['coverage_score']}%)")
    
    # Add absence analysis with adaptation
    print("Analyzing absences with adaptation logic...")
    analyzer = AbsenceAnalyzer()
    
    # Normalize team names for injury lookup
    home_team = ctx['home']['identity']['name'].replace("Nott'ham", "Nottingham")
    away_team = ctx['away']['identity']['name'].replace("Nott'ham", "Nottingham")
    
    # Leeds absences
    home_absences = analyzer.get_team_absences(home_team, match_date)
    home_summary = analyzer.summarize_absences(home_absences)
    
    # Forest absences  
    away_absences = analyzer.get_team_absences(away_team, match_date)
    away_summary = analyzer.summarize_absences(away_absences)
    
    analyzer.close()
    
    # Add to context
    ctx['home']['absences_v2'] = {
        'summary': home_summary,
        'players': [
            {
                'name': a.player_name,
                'position': a.position,
                'days_out': a.days_out,
                'games_missed': a.games_missed,
                'team_adapted': a.team_adapted,
                'base_impact': a.base_impact,
                'real_impact': round(a.real_impact, 1)
            } for a in home_absences
        ]
    }
    
    ctx['away']['absences_v2'] = {
        'summary': away_summary,
        'players': [
            {
                'name': a.player_name,
                'position': a.position,
                'days_out': a.days_out,
                'games_missed': a.games_missed,
                'team_adapted': a.team_adapted,
                'base_impact': a.base_impact,
                'real_impact': round(a.real_impact, 1)
            } for a in away_absences
        ]
    }
    
    print(f"  {home_team}: {home_summary['total_missing']} missing, real impact: {home_summary['total_real_impact']}")
    print(f"  {away_team}: {away_summary['total_missing']} missing, real impact: {away_summary['total_real_impact']}")
    
    # Call OpenAI
    print("\nCalling OpenAI for analysis...")
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': json.dumps(ctx, default=str)}
        ],
        max_tokens=1500
    )
    
    return response.choices[0].message.content


if __name__ == "__main__":
    fixture_id = sys.argv[1] if len(sys.argv) > 1 else "2026-02-06_Leeds_United_Nott'ham_Forest"
    match_date = date(2026, 2, 6)
    
    analysis = generate_analysis(fixture_id, match_date)
    
    if analysis:
        print("\n" + "="*60)
        print("ANÁLISE COMPLETA")
        print("="*60 + "\n")
        print(analysis)
