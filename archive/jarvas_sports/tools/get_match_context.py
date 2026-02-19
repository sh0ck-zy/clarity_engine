#!/usr/bin/env python3
"""
Get match context for intelligence generation.
Usage: python get_match_context.py "West Ham United" "Manchester United" 26
"""

import sys
import psycopg2
import json
import re
from datetime import datetime

def extract_stat(stats_dict, key):
    if not stats_dict or 'All' not in stats_dict:
        return None, None
    for stat_str in stats_dict['All']:
        if key in stat_str:
            match = re.search(rf"key='{key}', home='([^']*)', away='([^']*)'", stat_str)
            if match:
                return match.group(1), match.group(2)
    return None, None

def get_team_form(cur, team_name, before_round, n=5):
    cur.execute('''
        SELECT home_team_name, away_team_name, home_score, away_score,
               round_number, stats, match_date
        FROM fotmob_matches 
        WHERE (home_team_name = %s OR away_team_name = %s)
        AND round_number < %s
        ORDER BY round_number DESC
        LIMIT %s
    ''', (team_name, team_name, before_round, n))
    
    matches = []
    for row in cur.fetchall():
        home, away, hs, as_, rnd, stats, date = row
        is_home = home == team_name
        
        xg_h, xg_a = extract_stat(stats, 'expected_goals')
        poss_h, poss_a = extract_stat(stats, 'BallPossesion')
        
        if is_home:
            result = 'W' if hs > as_ else ('D' if hs == as_ else 'L')
            xg_for = float(xg_h) if xg_h and xg_h != 'None' else None
            xg_against = float(xg_a) if xg_a and xg_a != 'None' else None
            opponent = away
        else:
            result = 'W' if as_ > hs else ('D' if hs == as_ else 'L')
            xg_for = float(xg_a) if xg_a and xg_a != 'None' else None
            xg_against = float(xg_h) if xg_h and xg_h != 'None' else None
            opponent = home
        
        matches.append({
            'round': rnd,
            'opponent': opponent,
            'venue': 'H' if is_home else 'A',
            'result': result,
            'score': f"{hs}-{as_}" if is_home else f"{as_}-{hs}",
            'xg_for': xg_for,
            'xg_against': xg_against
        })
    
    return matches

def get_h2h(cur, team1, team2):
    cur.execute('''
        SELECT home_team_name, away_team_name, home_score, away_score, round_number
        FROM fotmob_matches 
        WHERE (home_team_name = %s AND away_team_name = %s)
           OR (home_team_name = %s AND away_team_name = %s)
        ORDER BY round_number
    ''', (team1, team2, team2, team1))
    
    return [{'home': r[0], 'away': r[1], 'score': f"{r[2]}-{r[3]}", 'round': r[4]} 
            for r in cur.fetchall()]

def main():
    if len(sys.argv) < 4:
        print("Usage: python get_match_context.py <home_team> <away_team> <round>")
        sys.exit(1)
    
    home_team = sys.argv[1]
    away_team = sys.argv[2]
    round_num = int(sys.argv[3])
    
    conn = psycopg2.connect(dbname='clarity_football', user='joao')
    cur = conn.cursor()
    
    print(f"=" * 60)
    print(f"MATCH CONTEXT: {home_team} vs {away_team} (R{round_num})")
    print(f"=" * 60)
    
    # Home team form
    print(f"\n{home_team.upper()} (Home)")
    print("-" * 40)
    home_form = get_team_form(cur, home_team, round_num)
    for m in home_form:
        xg_str = f"xG: {m['xg_for']:.2f}-{m['xg_against']:.2f}" if m['xg_for'] else ""
        print(f"  R{m['round']}: vs {m['opponent'][:15]:15} [{m['venue']}] {m['result']} {m['score']} {xg_str}")
    
    # Away team form
    print(f"\n{away_team.upper()} (Away)")
    print("-" * 40)
    away_form = get_team_form(cur, away_team, round_num)
    for m in away_form:
        xg_str = f"xG: {m['xg_for']:.2f}-{m['xg_against']:.2f}" if m['xg_for'] else ""
        print(f"  R{m['round']}: vs {m['opponent'][:15]:15} [{m['venue']}] {m['result']} {m['score']} {xg_str}")
    
    # Stats summary
    print(f"\nSUMMARY")
    print("-" * 40)
    
    home_results = ''.join([m['result'] for m in home_form])
    away_results = ''.join([m['result'] for m in away_form])
    
    home_xg_for = [m['xg_for'] for m in home_form if m['xg_for']]
    home_xg_against = [m['xg_against'] for m in home_form if m['xg_against']]
    away_xg_for = [m['xg_for'] for m in away_form if m['xg_for']]
    away_xg_against = [m['xg_against'] for m in away_form if m['xg_against']]
    
    print(f"  {home_team}: Form {home_results}")
    if home_xg_for:
        print(f"    Avg xG for: {sum(home_xg_for)/len(home_xg_for):.2f}")
        print(f"    Avg xG against: {sum(home_xg_against)/len(home_xg_against):.2f}")
    
    print(f"  {away_team}: Form {away_results}")
    if away_xg_for:
        print(f"    Avg xG for: {sum(away_xg_for)/len(away_xg_for):.2f}")
        print(f"    Avg xG against: {sum(away_xg_against)/len(away_xg_against):.2f}")
    
    # H2H
    print(f"\nH2H")
    print("-" * 40)
    h2h = get_h2h(cur, home_team, away_team)
    for m in h2h:
        print(f"  R{m['round']}: {m['home']} {m['score']} {m['away']}")
    
    conn.close()

if __name__ == "__main__":
    main()
