#!/usr/bin/env python3
"""
Compare Context Builders across Round 24 fixtures.

Compares:
1. V1 - MatchContextBuilder (legacy, dict-based, used by predictor)
2. V2 - ContextBuilderV2 (structured, dataclass-based)
3. V3 - EnrichedContextBuilder (V2 + optional agent enrichment)
"""

import sys
import warnings
from pathlib import Path
from datetime import datetime
import json

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.config import get_connection
import pandas as pd

# Import builders
from src.analysis.builder import MatchContextBuilder  # V1 Legacy
from src.analysis.context_builder_v2 import ContextBuilderV2  # V2 Structured
from src.agents.enriched_context import EnrichedContextBuilder  # V3 Enriched


def get_round_fixtures(round_num: int):
    """Get fixtures for a specific round."""
    conn = get_connection()
    df = pd.read_sql(f'''
        SELECT id, date, home_team, away_team, status, round
        FROM fixtures
        WHERE round = {round_num}
        ORDER BY date, home_team
    ''', conn)
    conn.close()
    return df


def analyze_v1_legacy(fixture_id: str):
    """Analyze using V1 MatchContextBuilder (legacy dict)."""
    builder = MatchContextBuilder()
    try:
        context = builder.build_context(fixture_id)
        if not context:
            return None

        home = context.get('home', {})
        away = context.get('away', {})

        return {
            'version': 'V1 Legacy (dict)',
            'builder': 'MatchContextBuilder',
            'file': 'src/analysis/builder.py',
            'format': 'dict',
            'home_name': home.get('name', 'N/A'),
            'away_name': away.get('name', 'N/A'),
            'home_elo': home.get('identity', {}).get('elo', 'N/A'),
            'away_elo': away.get('identity', {}).get('elo', 'N/A'),
            'home_form': home.get('form', {}).get('last_5_results', 'N/A'),
            'away_form': away.get('form', {}).get('last_5_results', 'N/A'),
            'home_injuries': len(home.get('context', {}).get('key_injuries', [])),
            'away_injuries': len(away.get('context', {}).get('key_injuries', [])),
            'has_h2h': False,  # V1 doesn't have H2H
            'has_schedule': False,  # V1 doesn't have schedule
            'has_league_pos': False,  # V1 doesn't have league position
            'has_odds': 'market_odds' in context,
            'coverage_score': 'N/A',  # V1 doesn't calculate coverage
        }
    except Exception as e:
        return {'version': 'V1 Legacy', 'error': str(e)}
    finally:
        builder.close()


def analyze_v2_structured(fixture_id: str):
    """Analyze using V2 ContextBuilderV2 (structured dataclass)."""
    builder = ContextBuilderV2()
    try:
        context = builder.build_context(fixture_id)
        if not context:
            return None

        return {
            'version': 'V2 Structured (dataclass)',
            'builder': 'ContextBuilderV2',
            'file': 'src/analysis/context_builder_v2.py',
            'format': 'MatchContext (dataclass)',
            'home_name': context.home.identity.name,
            'away_name': context.away.identity.name,
            'home_elo': context.home.identity.elo,
            'away_elo': context.away.identity.elo,
            'home_form': context.home.form.results,
            'away_form': context.away.form.results,
            'home_injuries': context.home.absences.total_missing,
            'away_injuries': context.away.absences.total_missing,
            'has_h2h': context.head_to_head.matches_played > 0,
            'h2h_matches': context.head_to_head.matches_played,
            'has_schedule': True,
            'home_rest': context.schedule.home_rest_days,
            'away_rest': context.schedule.away_rest_days,
            'has_league_pos': True,
            'home_position': context.league_position.home_position,
            'away_position': context.league_position.away_position,
            'has_odds': context.odds.home_win is not None,
            'coverage_score': f"{context.coverage_score:.0f}%",
            'missing_fields': len(context.missing_fields),
            'warnings': len(context.data_warnings),
        }
    except Exception as e:
        return {'version': 'V2 Structured', 'error': str(e)}
    finally:
        builder.close()


def analyze_v3_enriched(fixture_id: str, use_agent: bool = False):
    """Analyze using V3 EnrichedContextBuilder (V2 + optional agent)."""
    builder = EnrichedContextBuilder(use_agent=use_agent)
    try:
        result = builder.build_enriched_context(
            fixture_id,
            enrich_injuries=use_agent,
            enrich_h2h=use_agent,
            enrich_news=False
        )

        if not result.context:
            return None

        context = result.context

        return {
            'version': f'V3 Enriched (agent={use_agent})',
            'builder': 'EnrichedContextBuilder',
            'file': 'src/agents/enriched_context.py',
            'format': 'EnrichmentResult + MatchContext',
            'home_name': context.home.identity.name,
            'away_name': context.away.identity.name,
            'home_elo': context.home.identity.elo,
            'away_elo': context.away.identity.elo,
            'home_form': context.home.form.results,
            'away_form': context.away.form.results,
            'home_injuries': context.home.absences.total_missing,
            'away_injuries': context.away.absences.total_missing,
            'has_h2h': context.head_to_head.matches_played > 0,
            'h2h_matches': context.head_to_head.matches_played,
            'has_schedule': True,
            'home_rest': context.schedule.home_rest_days,
            'away_rest': context.schedule.away_rest_days,
            'has_league_pos': True,
            'home_position': context.league_position.home_position,
            'away_position': context.league_position.away_position,
            'has_odds': context.odds.home_win is not None,
            'coverage_score': f"{context.coverage_score:.0f}%",
            'enrichment_applied': result.enrichment_applied,
            'enrichment_quality': f"{result.enrichment_quality:.0%}",
            'enrichment_sources': result.enrichment_sources,
            'agent_data_used': result.agent_data_used if use_agent else 'N/A',
            'validation_errors': len(result.validation_errors),
            'validation_warnings': len(result.validation_warnings),
        }
    except Exception as e:
        return {'version': f'V3 Enriched (agent={use_agent})', 'error': str(e)}
    finally:
        builder.close()


def compare_fixture(fixture_id: str, home_team: str, away_team: str):
    """Compare all builders for one fixture."""
    print(f"\n{'=' * 80}")
    print(f"FIXTURE: {home_team} vs {away_team}")
    print(f"ID: {fixture_id}")
    print('=' * 80)

    # V1 Legacy
    print("\n[1/3] V1 Legacy MatchContextBuilder (dict-based, used by predictor)")
    print("-" * 80)
    v1 = analyze_v1_legacy(fixture_id)
    if v1 and 'error' not in v1:
        print(f"  Format: {v1['format']}")
        print(f"  Elo: {v1['home_elo']} vs {v1['away_elo']}")
        print(f"  Form: {v1['home_form']} vs {v1['away_form']}")
        print(f"  Injuries: {v1['home_injuries']} vs {v1['away_injuries']}")
        print(f"  H2H: {'No' if not v1['has_h2h'] else 'Yes'}")
        print(f"  Schedule: {'No' if not v1['has_schedule'] else 'Yes'}")
        print(f"  League Pos: {'No' if not v1['has_league_pos'] else 'Yes'}")
        print(f"  Odds: {'Yes' if v1['has_odds'] else 'No'}")
    else:
        print(f"  ERROR: {v1.get('error', 'Unknown')}")

    # V2 Structured
    print("\n[2/3] V2 ContextBuilderV2 (dataclass-based, strict schema)")
    print("-" * 80)
    v2 = analyze_v2_structured(fixture_id)
    if v2 and 'error' not in v2:
        print(f"  Format: {v2['format']}")
        print(f"  Elo: {v2['home_elo']} vs {v2['away_elo']}")
        print(f"  Form: {v2['home_form']} vs {v2['away_form']}")
        print(f"  Injuries: {v2['home_injuries']} vs {v2['away_injuries']}")
        print(f"  H2H: {'Yes' if v2['has_h2h'] else 'No'} ({v2.get('h2h_matches', 0)} matches)")
        print(f"  Schedule: Yes (rest: {v2.get('home_rest')} vs {v2.get('away_rest')} days)")
        print(f"  League Pos: Yes ({v2.get('home_position')} vs {v2.get('away_position')})")
        print(f"  Odds: {'Yes' if v2['has_odds'] else 'No'}")
        print(f"  Coverage: {v2['coverage_score']} (missing: {v2['missing_fields']}, warnings: {v2['warnings']})")
    else:
        print(f"  ERROR: {v2.get('error', 'Unknown')}")

    # V3 Enriched (no agent due to quota)
    print("\n[3/3] V3 EnrichedContextBuilder (V2 + agent support, agent=OFF)")
    print("-" * 80)
    v3 = analyze_v3_enriched(fixture_id, use_agent=False)
    if v3 and 'error' not in v3:
        print(f"  Format: {v3['format']}")
        print(f"  Elo: {v3['home_elo']} vs {v3['away_elo']}")
        print(f"  Form: {v3['home_form']} vs {v3['away_form']}")
        print(f"  Injuries: {v3['home_injuries']} vs {v3['away_injuries']}")
        print(f"  H2H: {'Yes' if v3['has_h2h'] else 'No'} ({v3.get('h2h_matches', 0)} matches)")
        print(f"  Schedule: Yes (rest: {v3.get('home_rest')} vs {v3.get('away_rest')} days)")
        print(f"  League Pos: Yes ({v3.get('home_position')} vs {v3.get('away_position')})")
        print(f"  Odds: {'Yes' if v3['has_odds'] else 'No'}")
        print(f"  Coverage: {v3['coverage_score']}")
        print(f"  Enrichment: Applied={v3['enrichment_applied']}, Sources={v3['enrichment_sources']}")
    else:
        print(f"  ERROR: {v3.get('error', 'Unknown')}")

    return v1, v2, v3


def main():
    """Compare all builders for Round 24."""
    print("\n" + "=" * 80)
    print("CONTEXT BUILDER COMPARISON - ROUND 24")
    print("=" * 80)
    print("\nComparing 3 versions:")
    print("  V1: MatchContextBuilder (legacy dict, used by predictor)")
    print("  V2: ContextBuilderV2 (structured dataclass)")
    print("  V3: EnrichedContextBuilder (V2 + optional agent)")
    print("\nNote: Agent enrichment disabled due to API quota limits")

    fixtures = get_round_fixtures(24)
    print(f"\nFound {len(fixtures)} fixtures in Round 24")

    results = []
    for idx, row in fixtures.iterrows():
        v1, v2, v3 = compare_fixture(
            row['id'],
            row['home_team'],
            row['away_team']
        )
        results.append({
            'fixture_id': row['id'],
            'home': row['home_team'],
            'away': row['away_team'],
            'v1': v1,
            'v2': v2,
            'v3': v3
        })

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    v1_success = sum(1 for r in results if r['v1'] and 'error' not in r['v1'])
    v2_success = sum(1 for r in results if r['v2'] and 'error' not in r['v2'])
    v3_success = sum(1 for r in results if r['v3'] and 'error' not in r['v3'])

    print(f"\nSuccess Rate:")
    print(f"  V1 Legacy: {v1_success}/{len(results)} ({v1_success/len(results)*100:.0f}%)")
    print(f"  V2 Structured: {v2_success}/{len(results)} ({v2_success/len(results)*100:.0f}%)")
    print(f"  V3 Enriched: {v3_success}/{len(results)} ({v3_success/len(results)*100:.0f}%)")

    # Feature comparison
    print("\n" + "=" * 80)
    print("FEATURE COMPARISON")
    print("=" * 80)

    features = [
        ('Basic Stats (Elo, Form)', True, True, True),
        ('Injuries', True, True, True),
        ('Head-to-Head', False, True, True),
        ('Schedule/Rest', False, True, True),
        ('League Position', False, True, True),
        ('Odds', True, True, True),
        ('Coverage Score', False, True, True),
        ('Validation', False, True, True),
        ('Strict Schema', False, True, True),
        ('Agent Enrichment', False, False, True),
    ]

    print(f"\n{'Feature':<25} {'V1':<8} {'V2':<8} {'V3':<8}")
    print("-" * 50)
    for feature, v1, v2, v3 in features:
        v1_s = '✓' if v1 else '✗'
        v2_s = '✓' if v2 else '✗'
        v3_s = '✓' if v3 else '✗'
        print(f"{feature:<25} {v1_s:<8} {v2_s:<8} {v3_s:<8}")

    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    print("""
V1 (MatchContextBuilder) - LEGACY
  ✓ Simple dict format
  ✓ Currently used by predictor
  ✗ Missing H2H, schedule, league position
  ✗ No validation or coverage tracking
  → Keep for backwards compatibility only

V2 (ContextBuilderV2) - CURRENT BEST
  ✓ Structured dataclass (MatchContext)
  ✓ Complete data: H2H, schedule, league position
  ✓ Validation and coverage tracking
  ✓ Time-travel safe
  → Use for new development

V3 (EnrichedContextBuilder) - FUTURE
  ✓ All V2 features
  ✓ Optional AI agent enrichment (injuries, H2H, news)
  ✓ Validation prevents hallucination
  ✓ Graceful fallback to DB-only
  → Use when agent enrichment is needed
  → Currently limited by API quotas
    """)


if __name__ == "__main__":
    main()
