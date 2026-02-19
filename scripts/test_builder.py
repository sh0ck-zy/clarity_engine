#!/usr/bin/env python3
"""
Quick test script for the ContextBuilder.

Usage:
    python scripts/test_builder.py
    python scripts/test_builder.py <fixture_id>
    python scripts/test_builder.py --round 25
"""

import sys
import json
from dataclasses import asdict
from datetime import date, datetime

sys.path.insert(0, '/Users/joao/Projects/clarity_engine')

from src.pipeline.builder import ContextBuilder


def json_serial(obj):
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, 'value'):  # Enum
        return obj.value
    raise TypeError(f"Type {type(obj)} not serializable")


def print_context(ctx):
    """Pretty print a PreMatchContext."""
    print(f"\n{'='*60}")
    print(f"🏟️  {ctx.fixture.home_team_name} vs {ctx.fixture.away_team_name}")
    print(f"📅 {ctx.fixture.match_date} | Round {ctx.fixture.round}")
    print(f"{'='*60}")
    
    print(f"\n🏠 HOME: {ctx.home_snapshot.name}")
    print(f"   📊 #{ctx.home_snapshot.league_position} | {ctx.home_snapshot.points}pts | ELO {ctx.home_snapshot.elo}")
    print(f"   📈 Form: {ctx.home_snapshot.form_last_5} ({ctx.home_snapshot.form_trend.value})")
    print(f"   ⚽ GD: {ctx.home_snapshot.goal_difference}")
    
    print(f"\n✈️  AWAY: {ctx.away_snapshot.name}")
    print(f"   📊 #{ctx.away_snapshot.league_position} | {ctx.away_snapshot.points}pts | ELO {ctx.away_snapshot.elo}")
    print(f"   📈 Form: {ctx.away_snapshot.form_last_5} ({ctx.away_snapshot.form_trend.value})")
    print(f"   ⚽ GD: {ctx.away_snapshot.goal_difference}")
    
    print(f"\n📉 STATS")
    print(f"   Home xG: {ctx.home_stats.xg_for:.1f} for / {ctx.home_stats.xg_against:.1f} against")
    print(f"   Away xG: {ctx.away_stats.xg_for:.1f} for / {ctx.away_stats.xg_against:.1f} against")
    
    print(f"\n🤕 INJURIES")
    print(f"   Home: {ctx.home_availability.total_missing} out ({ctx.home_availability.missing_key_players} key)")
    for a in ctx.home_availability.absences[:3]:
        adapted = "✓" if a.team_adapted else ""
        print(f"      • {a.player_name}: {a.injury_type} ({a.games_missed}g) {adapted}")
    if ctx.home_availability.total_missing > 3:
        print(f"      ... and {ctx.home_availability.total_missing - 3} more")
    
    print(f"   Away: {ctx.away_availability.total_missing} out ({ctx.away_availability.missing_key_players} key)")
    for a in ctx.away_availability.absences[:3]:
        adapted = "✓" if a.team_adapted else ""
        print(f"      • {a.player_name}: {a.injury_type} ({a.games_missed}g) {adapted}")
    if ctx.away_availability.total_missing > 3:
        print(f"      ... and {ctx.away_availability.total_missing - 3} more")
    
    print(f"\n⚔️  H2H ({ctx.head_to_head.matches_analyzed} matches)")
    print(f"   {ctx.head_to_head.home_wins}W-{ctx.head_to_head.draws}D-{ctx.head_to_head.away_wins}L")
    print(f"   Pattern: {ctx.head_to_head.pattern}")
    
    print(f"\n📖 NARRATIVES")
    if ctx.narratives.is_derby:
        print(f"   🔥 DERBY!")
    if ctx.narratives.is_rivalry:
        print(f"   ⚡ RIVALRY!")
    if ctx.narratives.is_six_pointer:
        print(f"   💥 SIX POINTER!")
    print(f"   Home: {ctx.narratives.home_stakes}")
    print(f"   Away: {ctx.narratives.away_stakes}")
    if ctx.narratives.home_under_pressure:
        print(f"   ⚠️  Home under pressure!")
    if ctx.narratives.away_under_pressure:
        print(f"   ⚠️  Away under pressure!")
    
    print(f"\n💰 ODDS")
    if ctx.odds:
        print(f"   H: {ctx.odds.home_win} | D: {ctx.odds.draw} | A: {ctx.odds.away_win}")
    else:
        print(f"   No odds available")
    
    print(f"\n📊 Coverage: {ctx.coverage_score}%")
    print(f"🔗 Sources: {', '.join(set(ctx.sources))}")


def main():
    builder = ContextBuilder()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--round':
            round_num = int(sys.argv[2]) if len(sys.argv) > 2 else 25
            print(f"\n📋 Fixtures for Round {round_num}:")
            fixtures = builder.list_fixtures(round_num=round_num)
            for f in fixtures:
                status = "✅" if f['status'] == 'FINISHED' else "⏳"
                score = f"{f['home_score']}-{f['away_score']}" if f['home_score'] is not None else "vs"
                print(f"  {status} {f['home_team']} {score} {f['away_team']}")
                print(f"     ID: {f['id']}")
        elif sys.argv[1] == '--json':
            fixture_id = sys.argv[2] if len(sys.argv) > 2 else None
            if fixture_id:
                ctx = builder.build_pre_match(fixture_id)
                print(json.dumps(asdict(ctx), default=json_serial, indent=2))
        else:
            fixture_id = sys.argv[1]
            ctx = builder.build_pre_match(fixture_id)
            print_context(ctx)
    else:
        # Default: show recent fixtures and test one
        print("📋 Recent fixtures:")
        fixtures = builder.list_fixtures(limit=10)
        for f in fixtures[:5]:
            print(f"  • {f['id']}")
        
        if fixtures:
            print(f"\n🔍 Testing first fixture...")
            ctx = builder.build_pre_match(fixtures[0]['id'])
            print_context(ctx)


if __name__ == "__main__":
    main()
