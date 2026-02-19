#!/usr/bin/env python3
"""
Populate Player States

Reads fotmob_player_performances,
computes player_states for each round.

Usage:
    python scripts/populate_player_states.py
"""

import os
import sys
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

import psycopg2
from psycopg2.extras import execute_values

# Database connection
DB_CONFIG = {
    "dbname": "clarity_football",
    "user": "joao",
    "host": "localhost"
}


@dataclass
class PlayerPerformance:
    """A single match performance for a player."""
    round_number: int
    match_date: str
    team_id: int
    is_starter: bool
    minutes_played: int
    rating: Optional[float]
    goals: int
    assists: int
    xg: float
    xa: float
    shots: int


def get_player_performances(conn) -> Tuple[Dict[int, str], Dict[int, List[PlayerPerformance]]]:
    """Get all player performances organized by player."""
    cur = conn.cursor()
    
    # Get performances with round numbers
    cur.execute("""
        SELECT 
            pp.player_id, pp.player_name, pp.team_id, pp.team_name,
            pp.is_starter, pp.minutes_played, pp.rating,
            pp.goals, pp.assists, COALESCE(pp.xg, 0), COALESCE(pp.xa, 0),
            COALESCE(pp.shots, 0),
            m.round_number, m.match_date
        FROM fotmob_player_performances pp
        JOIN fotmob_matches m ON pp.fotmob_match_id = m.fotmob_match_id
        WHERE m.round_number IS NOT NULL
        ORDER BY m.round_number, m.match_date
    """)
    
    rows = cur.fetchall()
    cur.close()
    
    # Organize by player
    player_names: Dict[int, str] = {}
    player_teams: Dict[int, int] = {}  # Most recent team
    player_performances: Dict[int, List[PlayerPerformance]] = defaultdict(list)
    
    for row in rows:
        (player_id, player_name, team_id, team_name,
         is_starter, minutes, rating,
         goals, assists, xg, xa, shots,
         round_num, match_date) = row
        
        player_names[player_id] = player_name
        player_teams[player_id] = team_id
        
        player_performances[player_id].append(PlayerPerformance(
            round_number=round_num,
            match_date=str(match_date),
            team_id=team_id,
            is_starter=is_starter or False,
            minutes_played=minutes or 0,
            rating=float(rating) if rating else None,
            goals=goals or 0,
            assists=assists or 0,
            xg=float(xg) if xg else 0,
            xa=float(xa) if xa else 0,
            shots=shots or 0,
        ))
    
    return player_names, player_teams, player_performances


def compute_player_state(player_id: int, team_id: int, round_number: int,
                         performances: List[PlayerPerformance]) -> Optional[dict]:
    """Compute player state for a specific round."""
    
    # Filter performances up to this round
    perfs_so_far = [p for p in performances if p.round_number <= round_number]
    perfs_so_far.sort(key=lambda x: (x.round_number, x.match_date))
    
    if not perfs_so_far:
        return None
    
    # Last 5 performances
    last_5 = perfs_so_far[-5:] if len(perfs_so_far) >= 5 else perfs_so_far
    
    # Season totals
    appearances = len(perfs_so_far)
    starts = sum(1 for p in perfs_so_far if p.is_starter)
    total_minutes = sum(p.minutes_played for p in perfs_so_far)
    total_goals = sum(p.goals for p in perfs_so_far)
    total_assists = sum(p.assists for p in perfs_so_far)
    total_xg = sum(p.xg for p in perfs_so_far)
    total_xa = sum(p.xa for p in perfs_so_far)
    
    # Last 5 metrics
    goals_last5 = sum(p.goals for p in last_5)
    assists_last5 = sum(p.assists for p in last_5)
    xg_last5 = sum(p.xg for p in last_5)
    xa_last5 = sum(p.xa for p in last_5)
    minutes_last5 = sum(p.minutes_played for p in last_5)
    
    # Ratings
    ratings_last5 = [p.rating for p in last_5 if p.rating is not None]
    avg_rating_last5 = sum(ratings_last5) / len(ratings_last5) if ratings_last5 else None
    
    all_ratings = [p.rating for p in perfs_so_far if p.rating is not None]
    avg_rating_season = sum(all_ratings) / len(all_ratings) if all_ratings else None
    
    # Per 90 stats
    if total_minutes >= 90:
        goals_per_90 = (total_goals / total_minutes) * 90
        assists_per_90 = (total_assists / total_minutes) * 90
        xg_per_90 = (total_xg / total_minutes) * 90
    else:
        goals_per_90 = assists_per_90 = xg_per_90 = 0
    
    # Get latest match date and team
    as_of_date = perfs_so_far[-1].match_date
    current_team = perfs_so_far[-1].team_id
    
    return {
        "player_id": player_id,
        "team_id": current_team,
        "round_number": round_number,
        "as_of_date": as_of_date,
        "appearances": appearances,
        "starts": starts,
        "minutes": total_minutes,
        "goals": total_goals,
        "assists": total_assists,
        "xg_total": round(total_xg, 2),
        "xa_total": round(total_xa, 2),
        "goals_last5": goals_last5,
        "assists_last5": assists_last5,
        "xg_last5": round(xg_last5, 2),
        "xa_last5": round(xa_last5, 2),
        "minutes_last5": minutes_last5,
        "avg_rating_last5": round(avg_rating_last5, 1) if avg_rating_last5 else None,
        "avg_rating_season": round(avg_rating_season, 1) if avg_rating_season else None,
        "goals_per_90": round(goals_per_90, 2),
        "assists_per_90": round(assists_per_90, 2),
        "xg_per_90": round(xg_per_90, 2),
    }


def main():
    print("=" * 60)
    print("CLARITY KG - Populating Player States")
    print("=" * 60)
    
    conn = psycopg2.connect(**DB_CONFIG)
    
    try:
        cur = conn.cursor()
        
        # 1. Populate players table
        print("\n[1/4] Populating players table...")
        cur.execute("""
            INSERT INTO players (player_id, player_name, current_team_id)
            SELECT DISTINCT ON (player_id) 
                player_id, player_name, team_id
            FROM fotmob_player_performances
            ORDER BY player_id, fotmob_match_id DESC
            ON CONFLICT (player_id) DO UPDATE SET
                player_name = EXCLUDED.player_name,
                current_team_id = EXCLUDED.current_team_id
        """)
        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM players")
        player_count = cur.fetchone()[0]
        print(f"      ✓ {player_count} players inserted")
        
        # 2. Get all performance data
        print("\n[2/4] Loading player performances...")
        player_names, player_teams, player_performances = get_player_performances(conn)
        print(f"      ✓ Loaded performances for {len(player_performances)} players")
        
        # 3. Compute player states for each round
        print("\n[3/4] Computing player states...")
        all_states = []
        
        for round_num in range(1, 27):
            round_count = 0
            for player_id, performances in player_performances.items():
                # Only compute if player has played by this round
                if any(p.round_number <= round_num for p in performances):
                    state = compute_player_state(
                        player_id, 
                        player_teams.get(player_id),
                        round_num, 
                        performances
                    )
                    if state:
                        all_states.append(state)
                        round_count += 1
            
            if round_num % 5 == 0:
                print(f"      ... Round {round_num}: {round_count} player states")
        
        print(f"      ✓ {len(all_states)} player states computed")
        
        # 4. Insert player states
        print("\n[4/4] Inserting player states...")
        
        insert_sql = """
            INSERT INTO player_states (
                player_id, team_id, round_number, as_of_date,
                appearances, starts, minutes,
                goals, assists, xg_total, xa_total,
                goals_last5, assists_last5, xg_last5, xa_last5, minutes_last5,
                avg_rating_last5, avg_rating_season,
                goals_per_90, assists_per_90, xg_per_90
            ) VALUES %s
            ON CONFLICT (player_id, round_number) DO UPDATE SET
                team_id = EXCLUDED.team_id,
                appearances = EXCLUDED.appearances,
                starts = EXCLUDED.starts,
                minutes = EXCLUDED.minutes,
                goals = EXCLUDED.goals,
                assists = EXCLUDED.assists,
                xg_total = EXCLUDED.xg_total,
                xa_total = EXCLUDED.xa_total,
                goals_last5 = EXCLUDED.goals_last5,
                assists_last5 = EXCLUDED.assists_last5,
                xg_last5 = EXCLUDED.xg_last5,
                xa_last5 = EXCLUDED.xa_last5,
                minutes_last5 = EXCLUDED.minutes_last5,
                avg_rating_last5 = EXCLUDED.avg_rating_last5,
                avg_rating_season = EXCLUDED.avg_rating_season,
                goals_per_90 = EXCLUDED.goals_per_90,
                assists_per_90 = EXCLUDED.assists_per_90,
                xg_per_90 = EXCLUDED.xg_per_90,
                computed_at = now()
        """
        
        values = [
            (
                s["player_id"], s["team_id"], s["round_number"], s["as_of_date"],
                s["appearances"], s["starts"], s["minutes"],
                s["goals"], s["assists"], s["xg_total"], s["xa_total"],
                s["goals_last5"], s["assists_last5"], s["xg_last5"], s["xa_last5"], s["minutes_last5"],
                s["avg_rating_last5"], s["avg_rating_season"],
                s["goals_per_90"], s["assists_per_90"], s["xg_per_90"],
            )
            for s in all_states
        ]
        
        execute_values(cur, insert_sql, values)
        conn.commit()
        
        # Verification
        cur.execute("SELECT COUNT(*) FROM player_states")
        state_count = cur.fetchone()[0]
        print(f"      ✓ {state_count} player states inserted")
        
        # Show sample - Top scorers at round 26
        print("\n" + "=" * 60)
        print("SAMPLE: Top 10 scorers at Round 26")
        print("=" * 60)
        cur.execute("""
            SELECT 
                p.player_name, t.team_name, 
                ps.goals, ps.assists, ps.xg_total,
                ps.avg_rating_season, ps.goals_per_90
            FROM player_states ps
            JOIN players p ON ps.player_id = p.player_id
            JOIN teams t ON ps.team_id = t.team_id
            WHERE ps.round_number = 26
            ORDER BY ps.goals DESC, ps.xg_total DESC
            LIMIT 10
        """)
        print(f"{'Player':<22} {'Team':<15} {'G':>3} {'A':>3} {'xG':>5} {'Rtg':>4} {'G/90':>5}")
        print("-" * 60)
        for row in cur.fetchall():
            name, team, goals, assists, xg, rating, g90 = row
            rating_str = f"{rating:.1f}" if rating else "N/A"
            print(f"{name:<22} {team:<15} {goals:>3} {assists:>3} {xg:>5.1f} {rating_str:>4} {g90:>5.2f}")
        
        # Show Salah's progression
        print("\n" + "=" * 60)
        print("SAMPLE: Mohamed Salah progression")
        print("=" * 60)
        cur.execute("""
            SELECT round_number, goals, assists, xg_total, 
                   goals_last5, avg_rating_last5
            FROM player_states 
            WHERE player_id = 292462  -- Salah
            AND round_number IN (5, 10, 15, 20, 26)
            ORDER BY round_number
        """)
        print(f"{'Rnd':>3} {'G':>3} {'A':>3} {'xG':>5} {'G(L5)':>5} {'Rtg(L5)':>7}")
        print("-" * 30)
        for row in cur.fetchall():
            rnd, goals, assists, xg, g5, rtg = row
            rtg_str = f"{rtg:.1f}" if rtg else "N/A"
            print(f"{rnd:>3} {goals:>3} {assists:>3} {xg:>5.1f} {g5:>5} {rtg_str:>7}")
        
        cur.close()
        
        print("\n" + "=" * 60)
        print("✅ DONE! Player states populated.")
        print("=" * 60)
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()
