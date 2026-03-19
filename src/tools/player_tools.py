"""
Player-focused tools for the agent.

Tools:
- get_key_players: Top performers and their current form
- get_injuries_impact: Who's missing and what it means
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import (
    db_cursor,
    row_to_dict,
    resolve_team,
    get_team_name,
    get_current_round,
    ToolResponse,
)


def get_key_players(
    team: str | int,
    round_number: Optional[int] = None,
    top_n: int = 5,
) -> ToolResponse:
    """
    Get the key players for a team based on performance metrics.
    
    Identifies the most influential players by:
    - Goal contributions (goals + assists)
    - Minutes played (regular starters)
    - Rating (data provider rating)
    - xG/xA output
    
    Args:
        team: Team name or ID
        round_number: Round to query (default: latest)
        top_n: Number of top players to return
    
    Returns:
        ToolResponse with key players analysis
    """
    try:
        team_id = resolve_team(team)
        team_name = get_team_name(team_id)
        
        if round_number is None:
            round_number = get_current_round()
        
        with db_cursor() as cur:
            # Get player states for this team at this round
            # Fall back to latest available round if requested round has no data
            cur.execute(
                """
                SELECT
                    ps.*,
                    p.player_name,
                    p.position
                FROM player_states ps
                JOIN players p ON ps.player_id = p.player_id
                WHERE ps.team_id = %s AND ps.round_number = (
                    SELECT MAX(round_number) FROM player_states
                    WHERE team_id = %s AND round_number <= %s
                )
                ORDER BY ps.minutes DESC
                """,
                (team_id, team_id, round_number)
            )
            all_players = [row_to_dict(r) for r in cur.fetchall()]

            if not all_players:
                return ToolResponse(
                    success=False,
                    error=f"No player data for {team_name} at round {round_number}"
                )
        
        # Categorize players
        regulars = [p for p in all_players if p["minutes"] >= 500]  # Regular starters
        
        # Sort by different metrics
        by_goals = sorted(all_players, key=lambda x: x["goals"], reverse=True)[:top_n]
        by_assists = sorted(all_players, key=lambda x: x["assists"], reverse=True)[:top_n]
        by_rating = sorted(
            [p for p in all_players if p["avg_rating_season"]],
            key=lambda x: x["avg_rating_season"] or 0,
            reverse=True
        )[:top_n]
        by_xg = sorted(all_players, key=lambda x: x["xg_total"] or 0, reverse=True)[:top_n]
        
        # Identify key players (appear in multiple top lists or exceptional in one)
        player_scores = {}
        for p in all_players:
            pid = p["player_id"]
            player_scores[pid] = {
                "player": p,
                "score": 0,
            }
            
            # Score based on contribution
            if p["goals"] > 0:
                player_scores[pid]["score"] += p["goals"] * 3
            if p["assists"] > 0:
                player_scores[pid]["score"] += p["assists"] * 2
            if p["avg_rating_season"] and p["avg_rating_season"] >= 7.0:
                player_scores[pid]["score"] += (p["avg_rating_season"] - 6.0) * 2
            if p["minutes"] >= 500:
                player_scores[pid]["score"] += 2  # Regular bonus
        
        # Get top scorers
        key_players = sorted(
            player_scores.values(),
            key=lambda x: x["score"],
            reverse=True
        )[:top_n]
        
        # Format key players
        formatted_players = []
        for item in key_players:
            p = item["player"]
            formatted_players.append({
                "player_id": p["player_id"],
                "name": p["player_name"],
                "position": p["position"],
                "minutes": p["minutes"],
                "appearances": p["appearances"],
                "goals": p["goals"],
                "assists": p["assists"],
                "g_a": p["goals"] + p["assists"],
                "xg": p["xg_total"],
                "xa": p["xa_total"],
                "avg_rating": p["avg_rating_season"],
                "form_rating": p["avg_rating_last5"],
                "goals_last5": p["goals_last5"],
                "assists_last5": p["assists_last5"],
            })
        
        # Build summary
        top_scorer = by_goals[0] if by_goals else None
        top_assist = by_assists[0] if by_assists else None
        
        summary_parts = [f"**{team_name} Key Players** (Round {round_number})"]
        
        if top_scorer and top_scorer["goals"] > 0:
            summary_parts.append(
                f"Top scorer: {top_scorer['player_name']} ({top_scorer['goals']}G)"
            )
        
        if top_assist and top_assist["assists"] > 0:
            summary_parts.append(
                f"Top assists: {top_assist['player_name']} ({top_assist['assists']}A)"
            )
        
        if by_rating:
            summary_parts.append(
                f"Best rated: {by_rating[0]['player_name']} ({by_rating[0]['avg_rating_season']:.1f})"
            )
        
        # Form players
        form_stars = [
            p for p in all_players 
            if p["avg_rating_last5"] and p["avg_rating_last5"] >= 7.0
        ]
        if form_stars:
            names = [p["player_name"] for p in sorted(
                form_stars, 
                key=lambda x: x["avg_rating_last5"] or 0, 
                reverse=True
            )[:3]]
            summary_parts.append(f"In form: {', '.join(names)}")
        
        return ToolResponse(
            success=True,
            data={
                "team": team_name,
                "round": round_number,
                "key_players": formatted_players,
                "top_scorers": [
                    {"name": p["player_name"], "goals": p["goals"]} 
                    for p in by_goals if p["goals"] > 0
                ],
                "top_assists": [
                    {"name": p["player_name"], "assists": p["assists"]} 
                    for p in by_assists if p["assists"] > 0
                ],
                "total_players": len(all_players),
                "regulars": len(regulars),
            },
            summary="\n".join(summary_parts)
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def get_injuries_impact(
    team: str | int,
    round_number: Optional[int] = None,
) -> ToolResponse:
    """
    Analyze the impact of missing players on a team.
    
    Compares current availability to full strength by looking at:
    - Players with reduced minutes recently
    - Key players missing from recent matches
    - Goal contribution from unavailable players
    
    Note: This is a heuristic based on playing time patterns,
    not actual injury reports (which would need a separate data source).
    
    Args:
        team: Team name or ID
        round_number: Round to query (default: latest)
    
    Returns:
        ToolResponse with injury/availability analysis
    """
    try:
        team_id = resolve_team(team)
        team_name = get_team_name(team_id)
        
        if round_number is None:
            round_number = get_current_round()
        
        with db_cursor() as cur:
            # Get current player states (fall back to latest available round)
            cur.execute(
                """
                SELECT
                    ps.*,
                    p.player_name,
                    p.position
                FROM player_states ps
                JOIN players p ON ps.player_id = p.player_id
                WHERE ps.team_id = %s AND ps.round_number = (
                    SELECT MAX(round_number) FROM player_states
                    WHERE team_id = %s AND round_number <= %s
                )
                """,
                (team_id, team_id, round_number)
            )
            current_players = {r["player_id"]: row_to_dict(r) for r in cur.fetchall()}

            # Get previous round to compare
            if round_number > 1:
                cur.execute(
                    """
                    SELECT
                        ps.*,
                        p.player_name,
                        p.position
                    FROM player_states ps
                    JOIN players p ON ps.player_id = p.player_id
                    WHERE ps.team_id = %s AND ps.round_number = (
                        SELECT MAX(round_number) FROM player_states
                        WHERE team_id = %s AND round_number <= %s
                    )
                    """,
                    (team_id, team_id, round_number - 1)
                )
                prev_players = {r["player_id"]: row_to_dict(r) for r in cur.fetchall()}
            else:
                prev_players = {}
        
        # Identify potential absentees (significant players with 0 or few minutes recently)
        potential_missing = []
        returning = []
        
        for pid, player in current_players.items():
            # Was a regular (500+ mins) but hasn't played last 5
            if player["minutes"] >= 500 and player["minutes_last5"] == 0:
                potential_missing.append({
                    "name": player["player_name"],
                    "position": player["position"],
                    "total_minutes": player["minutes"],
                    "goals": player["goals"],
                    "assists": player["assists"],
                    "last_5_minutes": player["minutes_last5"],
                    "impact": "High" if player["goals"] + player["assists"] >= 5 else "Medium",
                })
            
            # Reduced minutes (was playing, now not)
            elif pid in prev_players:
                prev = prev_players[pid]
                if prev["minutes_last5"] >= 300 and player["minutes_last5"] < 90:
                    potential_missing.append({
                        "name": player["player_name"],
                        "position": player["position"],
                        "total_minutes": player["minutes"],
                        "goals": player["goals"],
                        "assists": player["assists"],
                        "last_5_minutes": player["minutes_last5"],
                        "impact": "Medium",
                    })
            
            # Returning (wasn't playing, now is)
            if pid in prev_players:
                prev = prev_players[pid]
                if prev["minutes_last5"] < 90 and player["minutes_last5"] >= 200:
                    returning.append({
                        "name": player["player_name"],
                        "position": player["position"],
                        "minutes_last5": player["minutes_last5"],
                    })
        
        # Calculate missing contribution
        total_goals = sum(p["goals"] for p in current_players.values())
        total_assists = sum(p["assists"] for p in current_players.values())
        missing_goals = sum(p["goals"] for p in potential_missing)
        missing_assists = sum(p["assists"] for p in potential_missing)
        
        missing_pct = 0
        if total_goals + total_assists > 0:
            missing_pct = (missing_goals + missing_assists) / (total_goals + total_assists) * 100
        
        # Build summary
        summary_parts = [f"**{team_name} Availability Analysis** (Round {round_number})"]
        
        if potential_missing:
            summary_parts.append(f"⚠️ {len(potential_missing)} key players potentially unavailable:")
            for p in potential_missing[:3]:
                summary_parts.append(f"  - {p['name']} ({p['position']}) - {p['goals']}G {p['assists']}A this season")
            
            if missing_pct > 20:
                summary_parts.append(f"📊 Missing {missing_pct:.0f}% of team's goal contributions")
        else:
            summary_parts.append("✅ No significant absences detected")
        
        if returning:
            summary_parts.append(f"🔄 Returning: {', '.join(p['name'] for p in returning[:3])}")
        
        return ToolResponse(
            success=True,
            data={
                "team": team_name,
                "round": round_number,
                "potential_missing": potential_missing,
                "returning_players": returning,
                "missing_contribution": {
                    "goals": missing_goals,
                    "assists": missing_assists,
                    "pct_of_total": round(missing_pct, 1),
                },
                "squad_size": len(current_players),
            },
            summary="\n".join(summary_parts)
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))
