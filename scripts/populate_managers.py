#!/usr/bin/env python3
"""
Extract manager history from fotmob_matches.

For each team, extracts:
- Manager changes over the season
- Record under each manager
- Current manager
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict
from datetime import date

def get_connection():
    return psycopg2.connect(
        dbname="clarity_football",
        user="joao",
        host="localhost",
        port="5432"
    )


def extract_managers():
    """Extract manager data from all matches."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get all matches with coach info
    cur.execute("""
        SELECT 
            fotmob_match_id,
            round_number,
            match_date,
            home_team_id,
            away_team_id,
            home_score,
            away_score,
            raw_json->'content'->'lineup'->'homeTeam'->'coach'->>'id' as home_coach_id,
            raw_json->'content'->'lineup'->'homeTeam'->'coach'->>'name' as home_coach_name,
            raw_json->'content'->'lineup'->'awayTeam'->'coach'->>'id' as away_coach_id,
            raw_json->'content'->'lineup'->'awayTeam'->'coach'->>'name' as away_coach_name
        FROM fotmob_matches
        WHERE raw_json->'content'->'lineup'->'homeTeam'->'coach' IS NOT NULL
        ORDER BY round_number ASC
    """)
    
    matches = cur.fetchall()
    print(f"Processing {len(matches)} matches...")
    
    # Track manager stints per team
    # Key: (team_id, manager_id) -> {manager_name, matches: [...]}
    manager_stints = defaultdict(lambda: {
        "manager_name": None,
        "matches": []
    })
    
    for match in matches:
        round_num = match["round_number"]
        match_date = match["match_date"]
        
        # Process home team
        if match["home_coach_id"]:
            team_id = match["home_team_id"]
            manager_id = int(match["home_coach_id"])
            manager_name = match["home_coach_name"]
            
            key = (team_id, manager_id)
            manager_stints[key]["manager_name"] = manager_name
            
            # Determine result
            if match["home_score"] > match["away_score"]:
                result = "W"
            elif match["home_score"] < match["away_score"]:
                result = "L"
            else:
                result = "D"
            
            manager_stints[key]["matches"].append({
                "round": round_num,
                "date": match_date,
                "result": result
            })
        
        # Process away team
        if match["away_coach_id"]:
            team_id = match["away_team_id"]
            manager_id = int(match["away_coach_id"])
            manager_name = match["away_coach_name"]
            
            key = (team_id, manager_id)
            manager_stints[key]["manager_name"] = manager_name
            
            # Determine result
            if match["away_score"] > match["home_score"]:
                result = "W"
            elif match["away_score"] < match["home_score"]:
                result = "L"
            else:
                result = "D"
            
            manager_stints[key]["matches"].append({
                "round": round_num,
                "date": match_date,
                "result": result
            })
    
    # Find current manager per team (latest round)
    team_latest_manager = {}
    for (team_id, manager_id), data in manager_stints.items():
        if data["matches"]:
            latest_round = max(m["round"] for m in data["matches"])
            if team_id not in team_latest_manager or latest_round > team_latest_manager[team_id][1]:
                team_latest_manager[team_id] = (manager_id, latest_round)
    
    # Clear existing data
    cur.execute("TRUNCATE manager_history RESTART IDENTITY")
    
    # Insert manager stints
    inserted = 0
    for (team_id, manager_id), data in manager_stints.items():
        if not data["matches"]:
            continue
        
        matches_list = data["matches"]
        manager_name = data["manager_name"]
        
        first_round = min(m["round"] for m in matches_list)
        last_round = max(m["round"] for m in matches_list)
        first_date = min(m["date"] for m in matches_list)
        last_date = max(m["date"] for m in matches_list)
        
        wins = sum(1 for m in matches_list if m["result"] == "W")
        draws = sum(1 for m in matches_list if m["result"] == "D")
        losses = sum(1 for m in matches_list if m["result"] == "L")
        
        is_current = (team_id in team_latest_manager and 
                      team_latest_manager[team_id][0] == manager_id)
        
        cur.execute("""
            INSERT INTO manager_history 
            (team_id, manager_id, manager_name, first_match_round, last_match_round,
             first_match_date, last_match_date, matches, wins, draws, losses, is_current)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (team_id, manager_id) DO UPDATE SET
                manager_name = EXCLUDED.manager_name,
                first_match_round = EXCLUDED.first_match_round,
                last_match_round = EXCLUDED.last_match_round,
                first_match_date = EXCLUDED.first_match_date,
                last_match_date = EXCLUDED.last_match_date,
                matches = EXCLUDED.matches,
                wins = EXCLUDED.wins,
                draws = EXCLUDED.draws,
                losses = EXCLUDED.losses,
                is_current = EXCLUDED.is_current
        """, (
            team_id, manager_id, manager_name,
            first_round, last_round,
            first_date, last_date,
            len(matches_list), wins, draws, losses,
            is_current
        ))
        inserted += 1
    
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"Inserted {inserted} manager stints")
    return inserted


def show_summary():
    """Show manager summary."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT 
            t.team_name,
            mh.manager_name,
            mh.first_match_round,
            mh.last_match_round,
            mh.matches,
            mh.wins,
            mh.draws,
            mh.losses,
            mh.is_current
        FROM manager_history mh
        JOIN teams t ON t.team_id = mh.team_id
        ORDER BY t.team_name, mh.first_match_round
    """)
    
    rows = cur.fetchall()
    
    print("\n" + "="*80)
    print("MANAGER HISTORY")
    print("="*80)
    
    current_team = None
    for row in rows:
        if row["team_name"] != current_team:
            current_team = row["team_name"]
            print(f"\n{current_team}:")
        
        current = "← CURRENT" if row["is_current"] else ""
        record = f"{row['wins']}W-{row['draws']}D-{row['losses']}L"
        rounds = f"R{row['first_match_round']}-R{row['last_match_round']}"
        
        print(f"  {row['manager_name']:25s} {rounds:12s} ({row['matches']:2d} games, {record}) {current}")
    
    cur.close()
    conn.close()


if __name__ == "__main__":
    extract_managers()
    show_summary()
