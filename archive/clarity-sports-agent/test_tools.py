#!/usr/bin/env python3
"""
Test all tools in the Clarity Sports Agent.
"""

import sys
from pathlib import Path

# Add agent root to path
AGENT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_ROOT))

from tools.team_tools import (
    get_team_state,
    get_team_form,
    get_team_profile,
    get_psychological_state,
    get_last_match_summary,
)
from tools.player_tools import (
    get_player_state,
    get_key_players,
)
from tools.matchup_tools import (
    get_h2h,
    get_matchup_analysis,
)
from tools.reasoning_tools import (
    build_game_state_tree,
)
from resolvers.team_resolver import TeamResolver


def test_all():
    print("=" * 70)
    print("🔧 CLARITY SPORTS AGENT - Tool Tests")
    print("=" * 70)
    
    # Test resolver
    print("\n📍 Team Resolver")
    print("-" * 70)
    resolver = TeamResolver()
    for alias in ["Liverpool", "Wolves", "Spurs", "Man City"]:
        team = resolver.resolve(alias)
        status = f"✅ {team.name}" if team else "❌ Not found"
        print(f"   '{alias}' → {status}")
    
    # Test team tools
    print("\n👥 Team Tools")
    print("-" * 70)
    
    state = get_team_state("Arsenal")
    if state:
        print(f"   get_team_state('Arsenal')")
        print(f"      Position: {state.position}, Points: {state.points}")
        print(f"      Form: {state.form_string}, Trend: {state.form_trend}")
    
    form = get_team_form("Liverpool")
    if form:
        print(f"   get_team_form('Liverpool')")
        print(f"      {form.form_string} ({form.form_points}/15 pts)")
        print(f"      xG: {form.xg_for_last5:.1f} for, {form.xg_against_last5:.1f} against")
    
    psych = get_psychological_state("Burnley")
    if psych:
        print(f"   get_psychological_state('Burnley')")
        print(f"      State: {psych.state}, Confidence: {psych.confidence}")
        print(f"      Narrative: {psych.narrative[:60]}...")
    
    # Test player tools
    print("\n⚽ Player Tools")
    print("-" * 70)
    
    player = get_player_state("Haaland")
    if player:
        print(f"   get_player_state('Haaland')")
        print(f"      {player.player_name} ({player.team_name})")
        print(f"      Goals: {player.goals}, Assists: {player.assists}, xG: {player.xg_total:.1f}")
    
    key_players = get_key_players("Chelsea")
    if key_players:
        print(f"   get_key_players('Chelsea')")
        for p in key_players[:3]:
            form = "🔥" if p.is_in_form else ""
            print(f"      {p.player_name}: {p.goals}G {p.assists}A ({p.importance}) {form}")
    
    # Test matchup tools
    print("\n🆚 Matchup Tools")
    print("-" * 70)
    
    h2h = get_h2h("Arsenal", "Liverpool")
    if h2h:
        print(f"   get_h2h('Arsenal', 'Liverpool')")
        print(f"      {h2h.total_matches} matches: {h2h.team1} {h2h.team1_wins}W, {h2h.team2} {h2h.team2_wins}W, {h2h.draws}D")
        print(f"      Pattern: {h2h.pattern}")
    
    analysis = get_matchup_analysis("Manchester City", "Arsenal")
    if analysis:
        print(f"   get_matchup_analysis('Man City', 'Arsenal')")
        print(f"      {analysis.headline}")
        print(f"      Form advantage: {analysis.form_advantage}")
        print(f"      xG advantage: {analysis.xg_advantage}")
    
    # Test reasoning tools
    print("\n🧠 Reasoning Tools")
    print("-" * 70)
    
    tree = build_game_state_tree(
        home_team="Newcastle",
        away_team="Liverpool",
        home_psychological_state="neutral",
        away_psychological_state="neutral",
        home_form="DLLLW",
        away_form="DLWLW",
    )
    print(f"   build_game_state_tree('Newcastle', 'Liverpool')")
    print(f"      Most likely: {tree.most_likely_path} → {tree.most_likely_scoreline}")
    print(f"      Narrative: {tree.narrative}")
    
    print("\n" + "=" * 70)
    print("✅ All tool tests complete!")
    print("=" * 70)


if __name__ == "__main__":
    test_all()
