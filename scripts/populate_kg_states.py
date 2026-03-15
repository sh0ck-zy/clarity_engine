#!/usr/bin/env python3
"""
Populate Knowledge Graph States

Reads fotmob_matches and fotmob_player_performances,
computes team_states and player_states for each round.

Usage:
    python scripts/populate_kg_states.py
"""

import os
import sys
import re
import json
from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import execute_values

# Database connection
DB_CONFIG = {
    "dbname": "clarity_football",
    "user": "joao",
    "host": "localhost"
}


@dataclass
class MatchResult:
    """A single match result for a team."""
    round_number: int
    match_date: str
    kickoff_time: Optional[datetime] = None
    opponent_id: int = 0
    is_home: bool = True
    goals_for: int = 0
    goals_against: int = 0
    xg_for: float = 0.0
    xg_against: float = 0.0
    possession: float = 50.0
    formation: str = ""
    shots: int = 0
    shots_on_target: int = 0
    big_chances: int = 0
    shots_against: int = 0


def _parse_stats_new_format(stats_json: dict) -> dict:
    """Parse stats from Scrapling __NEXT_DATA__ format (Periods → stats array).

    Structure: {"Periods": {"All": {"stats": [
        {"key": "top_stats", "stats": [
            {"key": "BallPossesion", "stats": [61, 39]},
            {"key": "expected_goals", "stats": ["2.03", "0.22"]},
            ...
        ]},
        {"key": "shots", "stats": [
            {"key": "total_shots", "stats": [16, 6]},
            ...
        ]}
    ]}}}
    """
    result = {
        "possession_home": None, "possession_away": None,
        "xg_home": None, "xg_away": None,
        "shots_home": None, "shots_away": None,
        "shots_on_target_home": None, "shots_on_target_away": None,
        "big_chances_home": None, "big_chances_away": None,
    }

    periods = stats_json.get("Periods", {})
    all_period = periods.get("All", {})
    categories = all_period.get("stats", [])

    # Build a flat lookup: stat_key → [home, away]
    stat_lookup = {}
    for category in categories:
        for stat in category.get("stats", []):
            key = stat.get("key")
            vals = stat.get("stats", [])
            if key and isinstance(vals, list) and len(vals) >= 2:
                stat_lookup[key] = vals

    # Map keys to result fields
    key_map = {
        "BallPossesion": ("possession_home", "possession_away", float),
        "expected_goals": ("xg_home", "xg_away", float),
        "total_shots": ("shots_home", "shots_away", int),
        "ShotsOnTarget": ("shots_on_target_home", "shots_on_target_away", int),
        "big_chance": ("big_chances_home", "big_chances_away", int),
    }

    for stat_key, (home_field, away_field, cast_fn) in key_map.items():
        vals = stat_lookup.get(stat_key)
        if vals:
            try:
                result[home_field] = cast_fn(vals[0])
                result[away_field] = cast_fn(vals[1])
            except (ValueError, TypeError, IndexError):
                pass

    return result


def _parse_stats_legacy_format(stats_json: dict) -> dict:
    """Parse stats from legacy PL backfill format (stringified dataclass repr).

    Structure: {"All": ["FotMobStatCategory(title='Top stats', ...)", ...]}
    """
    result = {
        "possession_home": None, "possession_away": None,
        "xg_home": None, "xg_away": None,
        "shots_home": None, "shots_away": None,
        "shots_on_target_home": None, "shots_on_target_away": None,
        "big_chances_home": None, "big_chances_away": None,
    }

    all_stats = stats_json.get("All", [])

    for category_str in all_stats:
        if not isinstance(category_str, str):
            continue
        # Ball possession
        m = re.search(r"title='Ball possession'.*?home='(\d+)'.*?away='(\d+)'", category_str)
        if m:
            result["possession_home"] = float(m.group(1))
            result["possession_away"] = float(m.group(2))

        # Expected goals
        m = re.search(r"key='expected_goals', home='([\d.]+)', away='([\d.]+)'", category_str)
        if m:
            result["xg_home"] = float(m.group(1))
            result["xg_away"] = float(m.group(2))

        # Total shots
        m = re.search(r"key='total_shots', home='(\d+)', away='(\d+)'", category_str)
        if m:
            result["shots_home"] = int(m.group(1))
            result["shots_away"] = int(m.group(2))

        # Shots on target
        m = re.search(r"key='ShotsOnTarget', home='(\d+)', away='(\d+)'", category_str)
        if m:
            result["shots_on_target_home"] = int(m.group(1))
            result["shots_on_target_away"] = int(m.group(2))

        # Big chances
        m = re.search(r"key='big_chance', home='(\d+)', away='(\d+)'", category_str)
        if m:
            result["big_chances_home"] = int(m.group(1))
            result["big_chances_away"] = int(m.group(2))

    return result


def parse_stats_json(stats_json: dict) -> dict:
    """Parse the FotMob stats JSON to extract key metrics.

    Handles two formats:
    - New (Scrapling __NEXT_DATA__): dict with "Periods" key → clean JSON tree
    - Legacy (PL old backfill): dict with "All" key containing string repr of dataclasses
    """
    result = {
        "possession_home": None, "possession_away": None,
        "xg_home": None, "xg_away": None,
        "shots_home": None, "shots_away": None,
        "shots_on_target_home": None, "shots_on_target_away": None,
        "big_chances_home": None, "big_chances_away": None,
    }

    if not stats_json:
        return result

    # Format 3: Playwright — list of categories directly (no Periods wrapper)
    if isinstance(stats_json, list):
        return _parse_stats_new_format({"Periods": {"All": {"stats": stats_json}}})

    if not isinstance(stats_json, dict):
        return result

    # Format 1: Scrapling — dict with "Periods" key
    if "Periods" in stats_json:
        return _parse_stats_new_format(stats_json)
    # Format 2: Legacy — dict with "All" key (stringified dataclasses)
    elif "All" in stats_json:
        return _parse_stats_legacy_format(stats_json)

    return result


def get_team_matches(conn, league_id: int = 47) -> Dict[int, List[MatchResult]]:
    """Get all matches organized by team, filtered by league."""
    cur = conn.cursor()

    cur.execute("""
        SELECT
            fotmob_match_id, round_number, match_date,
            home_team_id, home_team_name, away_team_id, away_team_name,
            home_score, away_score,
            formation_home, formation_away,
            stats,
            kickoff_time
        FROM fotmob_matches
        WHERE status = 'finished' AND round_number IS NOT NULL
            AND league_id = %s
        ORDER BY round_number, match_date
    """, (league_id,))
    
    rows = cur.fetchall()
    cur.close()
    
    # Organize by team
    team_matches: Dict[int, List[MatchResult]] = {}
    
    for row in rows:
        (match_id, round_num, match_date,
         home_id, home_name, away_id, away_name,
         home_score, away_score,
         formation_home, formation_away,
         stats_json, kickoff_time) = row

        # Parse stats
        stats = parse_stats_json(stats_json) if stats_json else {}

        # Home team result
        if home_id not in team_matches:
            team_matches[home_id] = []

        team_matches[home_id].append(MatchResult(
            round_number=round_num,
            match_date=str(match_date),
            kickoff_time=kickoff_time,
            opponent_id=away_id,
            is_home=True,
            goals_for=home_score or 0,
            goals_against=away_score or 0,
            xg_for=stats.get("xg_home") or 0,
            xg_against=stats.get("xg_away") or 0,
            possession=stats.get("possession_home") if stats.get("possession_home") is not None else 50,
            formation=formation_home or "",
            shots=stats.get("shots_home") or 0,
            shots_on_target=stats.get("shots_on_target_home") or 0,
            big_chances=stats.get("big_chances_home") or 0,
            shots_against=stats.get("shots_away") or 0,
        ))

        # Away team result
        if away_id not in team_matches:
            team_matches[away_id] = []

        team_matches[away_id].append(MatchResult(
            round_number=round_num,
            match_date=str(match_date),
            kickoff_time=kickoff_time,
            opponent_id=home_id,
            is_home=False,
            goals_for=away_score or 0,
            goals_against=home_score or 0,
            xg_for=stats.get("xg_away") or 0,
            xg_against=stats.get("xg_home") or 0,
            possession=stats.get("possession_away") if stats.get("possession_away") is not None else 50,
            formation=formation_away or "",
            shots=stats.get("shots_away") or 0,
            shots_on_target=stats.get("shots_on_target_away") or 0,
            big_chances=stats.get("big_chances_away") or 0,
            shots_against=stats.get("shots_home") or 0,
        ))
    
    return team_matches


def calculate_form_string(results: List[str]) -> str:
    """Convert list of results to form string."""
    return "".join(results[-5:]) if results else ""


def calculate_form_trend(form_points_current: int, form_points_previous: int) -> str:
    """Determine form trend."""
    diff = form_points_current - form_points_previous
    if diff >= 3:
        return "improving"
    elif diff <= -3:
        return "declining"
    return "stable"


def compute_team_state(team_id: int, round_number: int,
                       matches: List[MatchResult],
                       kickoff_time: Optional[datetime] = None) -> dict:
    """Compute team state for a specific round.

    If kickoff_time is provided, uses it as the temporal cutoff (only include
    matches that kicked off BEFORE this time). Falls back to round_number
    filtering when kickoff_time is not available.
    """

    if kickoff_time is not None:
        # Temporal walk-forward: only include matches kicked off before this match
        matches_so_far = [m for m in matches
                          if m.kickoff_time is not None and m.kickoff_time < kickoff_time]
        if not matches_so_far:
            # Fallback to round-based if no kickoff_time matches
            matches_so_far = [m for m in matches if m.round_number <= round_number]
    else:
        matches_so_far = [m for m in matches if m.round_number <= round_number]
    matches_so_far.sort(key=lambda x: (x.kickoff_time or datetime.min, x.round_number))
    
    if not matches_so_far:
        return None
    
    # Last 5 matches
    last_5 = matches_so_far[-5:] if len(matches_so_far) >= 5 else matches_so_far
    
    # Calculate standings
    wins = draws = losses = 0
    goals_for = goals_against = 0
    home_wins = home_draws = home_losses = 0
    away_wins = away_draws = away_losses = 0
    results = []
    
    for m in matches_so_far:
        goals_for += m.goals_for
        goals_against += m.goals_against
        
        if m.goals_for > m.goals_against:
            wins += 1
            results.append("W")
            if m.is_home:
                home_wins += 1
            else:
                away_wins += 1
        elif m.goals_for < m.goals_against:
            losses += 1
            results.append("L")
            if m.is_home:
                home_losses += 1
            else:
                away_losses += 1
        else:
            draws += 1
            results.append("D")
            if m.is_home:
                home_draws += 1
            else:
                away_draws += 1
    
    points = wins * 3 + draws
    home_points = home_wins * 3 + home_draws
    away_points = away_wins * 3 + away_draws
    
    # Form metrics (last 5)
    form_string = calculate_form_string(results)
    form_results = results[-5:]
    form_points = sum(3 if r == "W" else 1 if r == "D" else 0 for r in form_results)
    
    goals_scored_last5 = sum(m.goals_for for m in last_5)
    goals_conceded_last5 = sum(m.goals_against for m in last_5)
    clean_sheets_last5 = sum(1 for m in last_5 if m.goals_against == 0)
    
    # xG metrics (last 5)
    xg_for_last5 = sum(m.xg_for for m in last_5)
    xg_against_last5 = sum(m.xg_against for m in last_5)
    xg_diff_last5 = xg_for_last5 - xg_against_last5
    
    # Averages
    n_matches = len(matches_so_far)
    avg_possession = sum(m.possession for m in matches_so_far) / n_matches if n_matches > 0 else 50
    shots_per_game = sum(m.shots for m in matches_so_far) / n_matches if n_matches > 0 else 0
    shots_on_target_per_game = sum(m.shots_on_target for m in matches_so_far) / n_matches if n_matches > 0 else 0
    xg_per_game = sum(m.xg_for for m in matches_so_far) / n_matches if n_matches > 0 else 0
    big_chances_per_game = sum(m.big_chances for m in matches_so_far) / n_matches if n_matches > 0 else 0
    shots_against_per_game = sum(m.shots_against for m in matches_so_far) / n_matches if n_matches > 0 else 0
    xg_against_per_game = sum(m.xg_against for m in matches_so_far) / n_matches if n_matches > 0 else 0
    
    # Most common formation
    formations = [m.formation for m in matches_so_far if m.formation]
    primary_formation = max(set(formations), key=formations.count) if formations else ""
    
    # Form trend (compare last 5 to previous 5)
    if len(matches_so_far) >= 10:
        prev_5 = matches_so_far[-10:-5]
        prev_results = []
        for m in prev_5:
            if m.goals_for > m.goals_against:
                prev_results.append("W")
            elif m.goals_for < m.goals_against:
                prev_results.append("L")
            else:
                prev_results.append("D")
        prev_form_points = sum(3 if r == "W" else 1 if r == "D" else 0 for r in prev_results)
        form_trend = calculate_form_trend(form_points, prev_form_points)
    else:
        form_trend = "stable"
    
    # Get latest match date
    as_of_date = matches_so_far[-1].match_date
    
    return {
        "team_id": team_id,
        "round_number": round_number,
        "as_of_date": as_of_date,
        "played": n_matches,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_difference": goals_for - goals_against,
        "points": points,
        "form_string": form_string,
        "form_points": form_points,
        "goals_scored_last5": goals_scored_last5,
        "goals_conceded_last5": goals_conceded_last5,
        "clean_sheets_last5": clean_sheets_last5,
        "xg_for_last5": round(xg_for_last5, 2),
        "xg_against_last5": round(xg_against_last5, 2),
        "xg_diff_last5": round(xg_diff_last5, 2),
        "avg_possession": round(avg_possession, 1),
        "primary_formation": primary_formation,
        "shots_per_game": round(shots_per_game, 1),
        "shots_on_target_per_game": round(shots_on_target_per_game, 1),
        "xg_per_game": round(xg_per_game, 2),
        "big_chances_per_game": round(big_chances_per_game, 1),
        "shots_against_per_game": round(shots_against_per_game, 1),
        "xg_against_per_game": round(xg_against_per_game, 2),
        "form_trend": form_trend,
        "home_wins": home_wins,
        "home_draws": home_draws,
        "home_losses": home_losses,
        "away_wins": away_wins,
        "away_draws": away_draws,
        "away_losses": away_losses,
        "home_points": home_points,
        "away_points": away_points,
    }


def calculate_positions(team_states: List[dict], round_number: int) -> None:
    """Calculate league positions for a round based on points."""
    round_states = [s for s in team_states if s and s["round_number"] == round_number]
    
    # Sort by points, then goal difference, then goals for
    round_states.sort(
        key=lambda x: (-x["points"], -x["goal_difference"], -x["goals_for"])
    )
    
    for i, state in enumerate(round_states, 1):
        state["position"] = i


def populate_players(conn, league_id: int) -> int:
    """Populate players table from fotmob_player_performances."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO players (player_id, player_name, current_team_id)
        SELECT DISTINCT ON (fpp.player_id)
            fpp.player_id, fpp.player_name, fpp.team_id
        FROM fotmob_player_performances fpp
        JOIN fotmob_matches fm ON fm.fotmob_match_id = fpp.fotmob_match_id
        WHERE fm.league_id = %s
          AND fpp.player_id IS NOT NULL
        ORDER BY fpp.player_id, fm.match_date DESC
        ON CONFLICT (player_id) DO UPDATE SET
            player_name = EXCLUDED.player_name,
            current_team_id = EXCLUDED.current_team_id
    """, (league_id,))
    conn.commit()
    count = cur.rowcount
    cur.close()
    return count


def get_player_match_data(conn, league_id: int) -> Dict[int, List[dict]]:
    """Get per-match player data for computing states."""
    cur = conn.cursor()
    cur.execute("""
        SELECT
            fpp.player_id, fpp.team_id, fm.round_number, fm.match_date,
            fpp.is_starter, fpp.minutes_played,
            fpp.goals, fpp.assists, fpp.xg, fpp.xa, fpp.rating
        FROM fotmob_player_performances fpp
        JOIN fotmob_matches fm ON fm.fotmob_match_id = fpp.fotmob_match_id
        WHERE fm.league_id = %s
          AND fm.status = 'finished'
          AND fm.round_number IS NOT NULL
          AND fpp.player_id IS NOT NULL
        ORDER BY fpp.player_id, fm.round_number, fm.match_date
    """, (league_id,))

    rows = cur.fetchall()
    cur.close()

    player_matches: Dict[int, List[dict]] = {}
    for row in rows:
        pid = row[0]
        entry = {
            "player_id": row[0],
            "team_id": row[1],
            "round_number": row[2],
            "match_date": str(row[3]),
            "is_starter": row[4],
            "minutes_played": row[5] or 0,
            "goals": row[6] or 0,
            "assists": row[7] or 0,
            "xg": float(row[8]) if row[8] is not None else 0.0,
            "xa": float(row[9]) if row[9] is not None else 0.0,
            "rating": float(row[10]) if row[10] is not None else None,
        }
        player_matches.setdefault(pid, []).append(entry)

    return player_matches


def compute_player_state(player_id: int, round_number: int,
                         matches: List[dict]) -> Optional[dict]:
    """Compute player state for a specific round (walk-forward)."""
    so_far = [m for m in matches if m["round_number"] <= round_number]
    if not so_far:
        return None

    last_5 = so_far[-5:]

    # Season totals
    appearances = len(so_far)
    starts = sum(1 for m in so_far if m["is_starter"])
    total_minutes = sum(m["minutes_played"] for m in so_far)
    goals = sum(m["goals"] for m in so_far)
    assists = sum(m["assists"] for m in so_far)
    xg_total = sum(m["xg"] for m in so_far)
    xa_total = sum(m["xa"] for m in so_far)

    # Last-5 form
    goals_last5 = sum(m["goals"] for m in last_5)
    assists_last5 = sum(m["assists"] for m in last_5)
    xg_last5 = sum(m["xg"] for m in last_5)
    xa_last5 = sum(m["xa"] for m in last_5)
    minutes_last5 = sum(m["minutes_played"] for m in last_5)
    ratings_last5 = [m["rating"] for m in last_5 if m["rating"] is not None]
    avg_rating_last5 = round(sum(ratings_last5) / len(ratings_last5), 1) if ratings_last5 else None

    # Season average rating
    all_ratings = [m["rating"] for m in so_far if m["rating"] is not None]
    avg_rating_season = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else None

    # Per-90 averages (guard: need at least 90 total minutes)
    if total_minutes >= 90:
        goals_per_90 = round(goals / (total_minutes / 90), 2)
        assists_per_90 = round(assists / (total_minutes / 90), 2)
        xg_per_90 = round(xg_total / (total_minutes / 90), 2)
    else:
        goals_per_90 = None
        assists_per_90 = None
        xg_per_90 = None

    # Use most recent match for team_id and as_of_date
    latest = so_far[-1]

    return {
        "player_id": player_id,
        "team_id": latest["team_id"],
        "round_number": round_number,
        "as_of_date": latest["match_date"],
        "appearances": appearances,
        "starts": starts,
        "minutes": total_minutes,
        "goals": goals,
        "assists": assists,
        "xg_total": round(xg_total, 2),
        "xa_total": round(xa_total, 2),
        "goals_last5": goals_last5,
        "assists_last5": assists_last5,
        "xg_last5": round(xg_last5, 2),
        "xa_last5": round(xa_last5, 2),
        "minutes_last5": minutes_last5,
        "avg_rating_last5": avg_rating_last5,
        "avg_rating_season": avg_rating_season,
        "goals_per_90": goals_per_90,
        "assists_per_90": assists_per_90,
        "xg_per_90": xg_per_90,
    }


def populate_player_states(conn, league_id: int) -> int:
    """Compute and insert player states for all players × rounds."""
    player_matches = get_player_match_data(conn, league_id)
    if not player_matches:
        return 0

    # Detect max round
    max_round = 0
    for matches in player_matches.values():
        for m in matches:
            if m["round_number"] > max_round:
                max_round = m["round_number"]

    all_states = []
    for player_id, matches in player_matches.items():
        for round_num in range(1, max_round + 1):
            state = compute_player_state(player_id, round_num, matches)
            if state:
                state["league_id"] = league_id
                all_states.append(state)

    if not all_states:
        return 0

    cur = conn.cursor()
    insert_sql = """
        INSERT INTO player_states (
            player_id, team_id, round_number, as_of_date,
            appearances, starts, minutes, goals, assists,
            xg_total, xa_total,
            goals_last5, assists_last5, xg_last5, xa_last5,
            minutes_last5, avg_rating_last5,
            avg_rating_season, goals_per_90, assists_per_90, xg_per_90,
            league_id
        ) VALUES %s
        ON CONFLICT (player_id, round_number, league_id) DO UPDATE SET
            team_id = EXCLUDED.team_id,
            as_of_date = EXCLUDED.as_of_date,
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
            s["appearances"], s["starts"], s["minutes"], s["goals"], s["assists"],
            s["xg_total"], s["xa_total"],
            s["goals_last5"], s["assists_last5"], s["xg_last5"], s["xa_last5"],
            s["minutes_last5"], s["avg_rating_last5"],
            s["avg_rating_season"], s["goals_per_90"], s["assists_per_90"], s["xg_per_90"],
            s["league_id"],
        )
        for s in all_states
    ]

    execute_values(cur, insert_sql, values)
    conn.commit()
    count = len(values)
    cur.close()
    return count


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Populate team states from FotMob matches")
    parser.add_argument("--league-id", type=int, default=47, help="FotMob league ID (default: 47 = PL)")
    args = parser.parse_args()

    league_id = args.league_id
    print("=" * 60)
    print(f"CLARITY KG - Populating Team States (league_id={league_id})")
    print("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)

    try:
        # 1. Ensure tables exist (without dropping existing data)
        print("\n[1/7] Ensuring KG tables exist...")
        cur = conn.cursor()
        # Create tables only if they don't exist yet
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'team_states'
            )
        """)
        tables_exist = cur.fetchone()[0]
        if not tables_exist:
            with open("scripts/001_create_kg_tables.sql", "r") as f:
                sql = f.read()
            cur.execute(sql)
            conn.commit()
            print("      ✓ Tables created")
        else:
            print("      ✓ Tables already exist (preserving data)")
            conn.commit()

        # 2. Populate teams table
        print("\n[2/7] Populating teams table...")
        cur.execute("""
            INSERT INTO teams (team_id, team_name, league_id)
            SELECT DISTINCT home_team_id, home_team_name, league_id
            FROM fotmob_matches
            WHERE league_id = %s
            ON CONFLICT (team_id) DO UPDATE SET
                league_id = EXCLUDED.league_id
        """, (league_id,))
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM teams WHERE league_id = %s", (league_id,))
        team_count = cur.fetchone()[0]
        print(f"      ✓ {team_count} teams inserted for league {league_id}")

        # 2b. Populate players table
        print("\n[2b/7] Populating players table...")
        player_count = populate_players(conn, league_id)
        cur.execute("SELECT COUNT(*) FROM players WHERE current_team_id IN (SELECT team_id FROM teams WHERE league_id = %s)", (league_id,))
        total_players = cur.fetchone()[0]
        print(f"      ✓ {total_players} players inserted for league {league_id}")

        # 3. Get all match data
        print("\n[3/7] Loading match data...")
        team_matches = get_team_matches(conn, league_id=league_id)
        print(f"      ✓ Loaded matches for {len(team_matches)} teams")

        # Detect max round from data (not hardcoded)
        all_rounds = set()
        for matches in team_matches.values():
            for m in matches:
                all_rounds.add(m.round_number)
        max_round = max(all_rounds) if all_rounds else 0
        print(f"      ✓ Rounds 1-{max_round} detected")

        # 4. Compute team states for each round
        print("\n[4/7] Computing team states...")
        all_states = []

        # Build a lookup: (team_id, round_number) -> kickoff_time
        # so we can use temporal walk-forward
        team_round_kickoff = {}
        for team_id, matches in team_matches.items():
            for m in matches:
                if m.kickoff_time is not None:
                    team_round_kickoff[(team_id, m.round_number)] = m.kickoff_time

        for round_num in range(1, max_round + 1):
            for team_id, matches in team_matches.items():
                # Use the kickoff_time of the match this team plays in the NEXT round
                # (team_state at round N is used for predicting round N+1)
                # But for computing state AS OF round N, we use this round's kickoff
                kickoff = team_round_kickoff.get((team_id, round_num))
                state = compute_team_state(team_id, round_num, matches, kickoff_time=kickoff)
                if state:
                    state["league_id"] = league_id
                    all_states.append(state)

            # Calculate positions for this round
            calculate_positions(all_states, round_num)

            if round_num % 5 == 0:
                print(f"      ... Round {round_num} computed")
        
        print(f"      ✓ {len(all_states)} team states computed")
        
        # 5. Insert team states
        print("\n[5/7] Inserting team states...")
        
        insert_sql = """
            INSERT INTO team_states (
                team_id, round_number, as_of_date, position,
                points, played, wins, draws, losses,
                goals_for, goals_against, goal_difference,
                form_string, form_points,
                goals_scored_last5, goals_conceded_last5, clean_sheets_last5,
                xg_for_last5, xg_against_last5, xg_diff_last5,
                avg_possession, primary_formation,
                shots_per_game, shots_on_target_per_game,
                xg_per_game, big_chances_per_game,
                shots_against_per_game, xg_against_per_game,
                form_trend,
                home_wins, home_draws, home_losses,
                away_wins, away_draws, away_losses,
                home_points, away_points,
                league_id
            ) VALUES %s
            ON CONFLICT (team_id, round_number, league_id) DO UPDATE SET
                position = EXCLUDED.position,
                points = EXCLUDED.points,
                played = EXCLUDED.played,
                wins = EXCLUDED.wins,
                draws = EXCLUDED.draws,
                losses = EXCLUDED.losses,
                goals_for = EXCLUDED.goals_for,
                goals_against = EXCLUDED.goals_against,
                goal_difference = EXCLUDED.goal_difference,
                form_string = EXCLUDED.form_string,
                form_points = EXCLUDED.form_points,
                goals_scored_last5 = EXCLUDED.goals_scored_last5,
                goals_conceded_last5 = EXCLUDED.goals_conceded_last5,
                clean_sheets_last5 = EXCLUDED.clean_sheets_last5,
                xg_for_last5 = EXCLUDED.xg_for_last5,
                xg_against_last5 = EXCLUDED.xg_against_last5,
                xg_diff_last5 = EXCLUDED.xg_diff_last5,
                avg_possession = EXCLUDED.avg_possession,
                primary_formation = EXCLUDED.primary_formation,
                shots_per_game = EXCLUDED.shots_per_game,
                shots_on_target_per_game = EXCLUDED.shots_on_target_per_game,
                xg_per_game = EXCLUDED.xg_per_game,
                big_chances_per_game = EXCLUDED.big_chances_per_game,
                shots_against_per_game = EXCLUDED.shots_against_per_game,
                xg_against_per_game = EXCLUDED.xg_against_per_game,
                form_trend = EXCLUDED.form_trend,
                home_wins = EXCLUDED.home_wins,
                home_draws = EXCLUDED.home_draws,
                home_losses = EXCLUDED.home_losses,
                away_wins = EXCLUDED.away_wins,
                away_draws = EXCLUDED.away_draws,
                away_losses = EXCLUDED.away_losses,
                home_points = EXCLUDED.home_points,
                away_points = EXCLUDED.away_points,
                computed_at = now()
        """
        
        values = [
            (
                s["team_id"], s["round_number"], s["as_of_date"], s["position"],
                s["points"], s["played"], s["wins"], s["draws"], s["losses"],
                s["goals_for"], s["goals_against"], s["goal_difference"],
                s["form_string"], s["form_points"],
                s["goals_scored_last5"], s["goals_conceded_last5"], s["clean_sheets_last5"],
                s["xg_for_last5"], s["xg_against_last5"], s["xg_diff_last5"],
                s["avg_possession"], s["primary_formation"],
                s["shots_per_game"], s["shots_on_target_per_game"],
                s["xg_per_game"], s["big_chances_per_game"],
                s["shots_against_per_game"], s["xg_against_per_game"],
                s["form_trend"],
                s["home_wins"], s["home_draws"], s["home_losses"],
                s["away_wins"], s["away_draws"], s["away_losses"],
                s["home_points"], s["away_points"],
                s["league_id"],
            )
            for s in all_states
        ]
        
        execute_values(cur, insert_sql, values)
        conn.commit()
        
        # Verification
        cur.execute("SELECT COUNT(*) FROM team_states WHERE league_id = %s", (league_id,))
        state_count = cur.fetchone()[0]
        print(f"      ✓ {state_count} team states inserted")

        # 6. Compute player states
        print("\n[6/7] Computing player states...")
        ps_count = populate_player_states(conn, league_id)
        print(f"      ✓ {ps_count} player states inserted")
        
        # Show sample (first team found)
        cur.execute("""
            SELECT DISTINCT t.team_id, t.team_name
            FROM teams t
            JOIN team_states ts ON ts.team_id = t.team_id AND ts.league_id = %s
            LIMIT 1
        """, (league_id,))
        sample_row = cur.fetchone()
        sample_team_id = sample_row[0] if sample_row else None
        sample_team_name = sample_row[1] if sample_row else "Unknown"

        print("\n" + "=" * 60)
        print(f"SAMPLE: {sample_team_name} progression")
        print("=" * 60)
        cur.execute("""
            SELECT round_number, position, points, form_string,
                   xg_for_last5, xg_against_last5, form_trend
            FROM team_states
            WHERE team_id = %s AND league_id = %s
            ORDER BY round_number
            LIMIT 10
        """, (sample_team_id, league_id))
        for row in cur.fetchall():
            print(f"  R{row[0]:2d}: Pos {row[1]:2d} | {row[2]:2d} pts | Form: {row[3]:5s} | xG: {row[4]:.1f} for / {row[5]:.1f} ag | {row[6]}")
        
        cur.close()
        
        print("\n" + "=" * 60)
        print("✅ DONE! Team states + player states populated.")
        print("=" * 60)
        
    finally:
        conn.close()


if __name__ == "__main__":
    main()
