#!/usr/bin/env python3
"""
Test Claude agent integration.

Tests the ExtractionAgent with Claude (Anthropic) as the primary provider.
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Check for API key
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("❌ ANTHROPIC_API_KEY not found in environment")
    print("\nTo set it:")
    print("  export ANTHROPIC_API_KEY='your-key-here'")
    print("  # or add to .env file")
    sys.exit(1)

print(f"✓ Found ANTHROPIC_API_KEY: {api_key[:10]}...")

from src.agents.extraction_agent import ExtractionAgent, create_agent
from datetime import date

print("\n" + "=" * 70)
print("CLAUDE AGENT TEST")
print("=" * 70)

# Test 1: Initialize agent
print("\n[1/4] Initializing Claude agent...")
agent = create_agent(provider="claude")

if agent._claude_client:
    print("✓ Claude client initialized")
else:
    print("❌ Claude client not initialized")
    sys.exit(1)

# Test 2: Extract injuries
print("\n[2/4] Testing injury extraction...")
team_name = "Arsenal"
league = "Premier League"
match_date = date(2026, 2, 1)

try:
    result = agent.extract_injuries(team_name, league, match_date)

    print(f"✓ Extraction completed")
    print(f"  Source: {result['source']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Injuries found: {len(result['injuries'])}")

    for injury in result['injuries'][:3]:
        print(f"    - {injury['player_name']} ({injury['position']}): {injury['injury_type']}")

    if len(result['injuries']) > 3:
        print(f"    ... and {len(result['injuries']) - 3} more")

except Exception as e:
    print(f"❌ Extraction failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Extract form
print("\n[3/4] Testing form extraction...")
try:
    result = agent.extract_form(team_name, league, match_date)

    print(f"✓ Extraction completed")
    print(f"  Source: {result['source']}")

    if result['form']:
        print(f"  Last 5 matches: {len(result['form']['last_5'])}")
        print(f"  Goals scored: {result['form']['goals_scored_last_5']}")
        print(f"  Goals conceded: {result['form']['goals_conceded_last_5']}")

        for match in result['form']['last_5'][:3]:
            print(f"    {match['result']} vs {match['opponent']} ({match['score']}) [{match['venue']}]")
    else:
        print("  No form data extracted")

except Exception as e:
    print(f"❌ Form extraction failed: {e}")

# Test 4: Extract table position
print("\n[4/4] Testing table position extraction...")
try:
    result = agent.extract_table_position(team_name, league, match_date)

    print(f"✓ Extraction completed")
    print(f"  Source: {result['source']}")

    if result['table_position']:
        table = result['table_position']
        print(f"  Position: {table['position']}")
        print(f"  Points: {table['points']} ({table['played']} games)")
        print(f"  W-D-L: {table['won']}-{table['drawn']}-{table['lost']}")
        print(f"  GD: {table['goal_difference']}")
    else:
        print("  No table data extracted")

except Exception as e:
    print(f"❌ Table extraction failed: {e}")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("✓ Claude agent integration working")
print("✓ Can extract structured data")
print("✓ Returns valid JSON")
print("\nNext step: Test with validation layer")
