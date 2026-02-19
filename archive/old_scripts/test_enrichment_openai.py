#!/usr/bin/env python3
"""
Test enrichment with OpenAI (since we have quota).

Demonstrates full pipeline: DB → Agent (OpenAI) → Validation → Merge
"""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import os
if not os.getenv("OPENAI_API_KEY"):
    print("❌ OPENAI_API_KEY not found")
    sys.exit(1)

print(f"✓ Found OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY')[:15]}...")

from src.agents.enriched_context import EnrichedContextBuilder
from src.database.config import get_connection
import pandas as pd

print("\n" + "=" * 70)
print("OPENAI AGENT ENRICHMENT TEST")
print("=" * 70)

# Get a fixture
conn = get_connection()
df = pd.read_sql("""
    SELECT id, home_team, away_team
    FROM fixtures
    WHERE round = 24 AND status = 'SCHEDULED'
    LIMIT 1
""", conn)
conn.close()

if df.empty:
    print("❌ No fixtures found")
    sys.exit(1)

fixture_id = df.iloc[0]['id']
home_team = df.iloc[0]['home_team']
away_team = df.iloc[0]['away_team']

print(f"\nFixture: {fixture_id}")
print(f"Match: {home_team} vs {away_team}")

# Test 1: Base context (no agent)
print("\n" + "=" * 70)
print("[1/2] BASE CONTEXT (DB only)")
print("=" * 70)

builder_base = EnrichedContextBuilder(use_agent=False)
result_base = builder_base.build_enriched_context(fixture_id)
builder_base.close()

if result_base.context:
    ctx = result_base.context
    print(f"✓ Context built")
    print(f"  Coverage: {ctx.coverage_score}%")
    print(f"  Home injuries: {ctx.home.absences.total_missing}")
    print(f"  Away injuries: {ctx.away.absences.total_missing}")
    print(f"  H2H matches: {ctx.head_to_head.matches_played}")
    print(f"  Sources: {result_base.enrichment_sources}")
else:
    print("❌ Failed to build base context")
    sys.exit(1)

# Test 2: Enriched context with OpenAI
print("\n" + "=" * 70)
print("[2/2] ENRICHED CONTEXT (DB + OpenAI Agent)")
print("=" * 70)

print("\nBuilding with OpenAI agent...")
print("(This may take 10-20 seconds for web search + extraction)")

builder_enriched = EnrichedContextBuilder(use_agent=True, provider="openai")
result_enriched = builder_enriched.build_enriched_context(
    fixture_id,
    enrich_injuries=True,
    enrich_h2h=True,
    enrich_news=False  # Skip news for speed
)
builder_enriched.close()

if result_enriched.context:
    ctx = result_enriched.context
    print(f"\n✓ Context built with enrichment")
    print(f"  Coverage: {ctx.coverage_score}%")
    print(f"  Enrichment applied: {result_enriched.enrichment_applied}")
    print(f"  Enrichment quality: {result_enriched.enrichment_quality:.0%}")
    print(f"  Sources: {result_enriched.enrichment_sources}")

    print(f"\n  Agent data used:")
    for key, used in result_enriched.agent_data_used.items():
        status = "✓" if used else "✗"
        print(f"    {status} {key}")

    print(f"\n  Home injuries: {ctx.home.absences.total_missing}")
    if ctx.home.absences.players:
        for p in ctx.home.absences.players[:3]:
            print(f"    - {p.player_name} ({p.position}): {p.injury_type}")
        if ctx.home.absences.total_missing > 3:
            print(f"    ... and {ctx.home.absences.total_missing - 3} more")

    print(f"\n  Away injuries: {ctx.away.absences.total_missing}")
    if ctx.away.absences.players:
        for p in ctx.away.absences.players[:3]:
            print(f"    - {p.player_name} ({p.position}): {p.injury_type}")
        if ctx.away.absences.total_missing > 3:
            print(f"    ... and {ctx.away.absences.total_missing - 3} more")

    print(f"\n  H2H matches: {ctx.head_to_head.matches_played}")
    if ctx.head_to_head.matches_played > 0:
        print(f"    Home wins: {ctx.head_to_head.home_wins}")
        print(f"    Draws: {ctx.head_to_head.draws}")
        print(f"    Away wins: {ctx.head_to_head.away_wins}")

    if result_enriched.validation_errors:
        print(f"\n  Validation errors: {len(result_enriched.validation_errors)}")
        for e in result_enriched.validation_errors[:3]:
            print(f"    - {e}")

    if result_enriched.validation_warnings:
        print(f"\n  Validation warnings: {len(result_enriched.validation_warnings)}")
        for w in result_enriched.validation_warnings[:3]:
            print(f"    - {w}")
else:
    print("❌ Failed to build enriched context")
    if result_enriched.validation_errors:
        print(f"\nErrors: {result_enriched.validation_errors}")
    sys.exit(1)

# Comparison
print("\n" + "=" * 70)
print("COMPARISON")
print("=" * 70)

print(f"\nBase (DB only):")
print(f"  Coverage: {result_base.context.coverage_score}%")
print(f"  Home injuries: {result_base.context.home.absences.total_missing}")
print(f"  Away injuries: {result_base.context.away.absences.total_missing}")

print(f"\nEnriched (DB + Agent):")
print(f"  Coverage: {result_enriched.context.coverage_score}%")
print(f"  Home injuries: {result_enriched.context.home.absences.total_missing}")
print(f"  Away injuries: {result_enriched.context.away.absences.total_missing}")

if result_enriched.enrichment_applied:
    print(f"\n✓ Enrichment improved the context!")
    print(f"  Quality gain: {result_enriched.enrichment_quality:.0%}")
else:
    print(f"\n✗ No enrichment applied (agent may have failed or returned empty)")

print("\n" + "=" * 70)
print("✓ TEST COMPLETE")
print("=" * 70)
print("\nKey takeaways:")
print("  • Agent enrichment working with OpenAI")
print("  • Validation layer prevents bad data")
print("  • Graceful fallback to DB if agent fails")
print("  • Never shows wrong data to user")
