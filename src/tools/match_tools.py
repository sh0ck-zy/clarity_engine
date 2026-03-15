"""
Match-focused tools for the agent.

Tools:
- get_last_match_summary: Detailed breakdown of most recent match
- get_h2h: Historical head-to-head record
- get_matchup_analysis: Style clash prediction
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
    format_form_string,
)


def get_last_match_summary(
    team: str | int,
    round_number: Optional[int] = None,
) -> ToolResponse:
    """
    Get a detailed summary of a team's most recent match.
    
    Provides rich context about:
    - Result and scoreline
    - xG comparison
    - Key moments (goals, cards)
    - Player ratings
    - Tactical observations
    
    Args:
        team: Team name or ID
        round_number: Get last match before this round (default: latest)
    
    Returns:
        ToolResponse with match summary
    """
    try:
        team_id = resolve_team(team)
        team_name = get_team_name(team_id)
        
        if round_number is None:
            round_number = get_current_round()
        
        with db_cursor() as cur:
            # Get the most recent match
            cur.execute(
                """
                SELECT * FROM fotmob_matches
                WHERE (home_team_id = %s OR away_team_id = %s)
                    AND round_number <= %s
                ORDER BY round_number DESC
                LIMIT 1
                """,
                (team_id, team_id, round_number)
            )
            match = cur.fetchone()
            
            if not match:
                return ToolResponse(
                    success=False,
                    error=f"No recent match found for {team_name}"
                )
            
            match = row_to_dict(match)
            
            # Get player performances for this match
            cur.execute(
                """
                SELECT 
                    pp.*,
                    p.player_name,
                    p.position
                FROM fotmob_player_performances pp
                JOIN players p ON pp.player_id = p.player_id
                WHERE pp.fotmob_match_id = %s
                ORDER BY pp.rating DESC NULLS LAST
                """,
                (match["fotmob_match_id"],)
            )
            performances = [row_to_dict(r) for r in cur.fetchall()]
        
        # Determine if team was home or away
        is_home = match["home_team_id"] == team_id
        
        team_data = {
            "name": match["home_team_name"] if is_home else match["away_team_name"],
            "score": match["home_score"] if is_home else match["away_score"],
        }
        opponent_data = {
            "name": match["away_team_name"] if is_home else match["home_team_name"],
            "score": match["away_score"] if is_home else match["home_score"],
        }
        
        # Result
        if team_data["score"] > opponent_data["score"]:
            result = "WIN"
            result_emoji = "✅"
        elif team_data["score"] < opponent_data["score"]:
            result = "LOSS"
            result_emoji = "❌"
        else:
            result = "DRAW"
            result_emoji = "🟡"
        
        # Player performances for the team
        team_performances = [
            p for p in performances 
            if p["team_id"] == team_id
        ]
        
        # Top performers
        top_rated = sorted(
            [p for p in team_performances if p["rating"]],
            key=lambda x: x["rating"] or 0,
            reverse=True
        )[:3]
        
        # Goal scorers
        scorers = [p for p in team_performances if p["goals"] and p["goals"] > 0]
        
        summary_data = {
            "match_id": match["fotmob_match_id"],
            "round": match["round_number"],
            "date": match["match_date"],
            "venue": "Home" if is_home else "Away",
            "opponent": opponent_data["name"],
            "result": result,
            "score": f"{team_data['score']}-{opponent_data['score']}",
            "top_performers": [
                {
                    "name": p["player_name"],
                    "position": p["position"],
                    "rating": p["rating"],
                    "goals": p["goals"],
                    "assists": p["assists"],
                }
                for p in top_rated
            ],
            "scorers": [
                {"name": p["player_name"], "goals": p["goals"]}
                for p in scorers
            ],
        }
        
        # Build summary
        summary_parts = [
            f"**{team_name} Last Match** (Round {match['round_number']})",
            f"{result_emoji} {result}: {team_name} {team_data['score']}-{opponent_data['score']} {opponent_data['name']} ({'H' if is_home else 'A'})",
        ]
        
        if top_rated:
            summary_parts.append(
                f"Best rated: {top_rated[0]['player_name']} ({top_rated[0]['rating']:.1f})"
            )
        
        if scorers:
            scorer_str = ", ".join(
                f"{p['player_name']} ({p['goals']})" for p in scorers
            )
            summary_parts.append(f"Scorers: {scorer_str}")
        
        return ToolResponse(
            success=True,
            data=summary_data,
            summary="\n".join(summary_parts)
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def get_h2h(
    team1: str | int,
    team2: str | int,
    limit: int = 10,
    round_number: Optional[int] = None,
) -> ToolResponse:
    """
    Get head-to-head record between two teams.
    
    Analyzes historical matchups:
    - Win/draw/loss record
    - Goals scored/conceded
    - Home/away splits
    - Recent form in this fixture
    
    Args:
        team1: First team name or ID
        team2: Second team name or ID
        limit: Max number of matches to analyze
        round_number: Only include matches up to this round (default: latest)
    
    Returns:
        ToolResponse with H2H analysis
    """
    try:
        team1_id = resolve_team(team1)
        team2_id = resolve_team(team2)
        team1_name = get_team_name(team1_id)
        team2_name = get_team_name(team2_id)
        
        if round_number is None:
            round_number = get_current_round()
        
        with db_cursor() as cur:
            # Get matches between these teams up to the specified round
            cur.execute(
                """
                SELECT * FROM fotmob_matches
                WHERE ((home_team_id = %s AND away_team_id = %s)
                   OR (home_team_id = %s AND away_team_id = %s))
                   AND round_number <= %s
                ORDER BY match_date DESC
                LIMIT %s
                """,
                (team1_id, team2_id, team2_id, team1_id, round_number, limit)
            )
            matches = [row_to_dict(r) for r in cur.fetchall()]
        
        if not matches:
            return ToolResponse(
                success=True,
                data={
                    "team1": team1_name,
                    "team2": team2_name,
                    "matches_found": 0,
                    "message": "No head-to-head matches found in database"
                },
                summary=f"**{team1_name} vs {team2_name}**\nNo recent H2H data available"
            )
        
        # Calculate stats from team1's perspective
        team1_wins = 0
        team2_wins = 0
        draws = 0
        team1_goals = 0
        team2_goals = 0
        team1_home_wins = 0
        team1_away_wins = 0
        
        match_details = []
        
        for m in matches:
            is_team1_home = m["home_team_id"] == team1_id
            
            if is_team1_home:
                t1_score = m["home_score"]
                t2_score = m["away_score"]
            else:
                t1_score = m["away_score"]
                t2_score = m["home_score"]
            
            team1_goals += t1_score
            team2_goals += t2_score
            
            if t1_score > t2_score:
                team1_wins += 1
                if is_team1_home:
                    team1_home_wins += 1
                else:
                    team1_away_wins += 1
                result = "W"
            elif t1_score < t2_score:
                team2_wins += 1
                result = "L"
            else:
                draws += 1
                result = "D"
            
            match_details.append({
                "date": m["match_date"],
                "round": m["round_number"],
                "venue": "Home" if is_team1_home else "Away",
                "score": f"{t1_score}-{t2_score}",
                "result": result,
            })
        
        total = len(matches)
        
        h2h_data = {
            "team1": team1_name,
            "team2": team2_name,
            "matches_analyzed": total,
            "record": {
                "team1_wins": team1_wins,
                "draws": draws,
                "team2_wins": team2_wins,
            },
            "goals": {
                "team1": team1_goals,
                "team2": team2_goals,
                "team1_avg": round(team1_goals / total, 2),
                "team2_avg": round(team2_goals / total, 2),
            },
            "venue_breakdown": {
                "team1_home_wins": team1_home_wins,
                "team1_away_wins": team1_away_wins,
            },
            "recent_matches": match_details[:5],
        }
        
        # Determine who has the edge
        if team1_wins > team2_wins + 2:
            edge = f"{team1_name} dominates"
        elif team2_wins > team1_wins + 2:
            edge = f"{team2_name} dominates"
        elif team1_wins > team2_wins:
            edge = f"Slight edge to {team1_name}"
        elif team2_wins > team1_wins:
            edge = f"Slight edge to {team2_name}"
        else:
            edge = "Evenly matched"
        
        # Recent form string
        form_string = "".join(m["result"] for m in match_details[:5])
        
        summary = f"""**{team1_name} vs {team2_name} H2H** (Last {total} matches)
Record: {team1_wins}W-{draws}D-{team2_wins}L (from {team1_name}'s perspective)
Goals: {team1_goals}-{team2_goals} ({team1_goals/total:.1f} vs {team2_goals/total:.1f} per game)
Recent: {format_form_string(form_string)}
Verdict: {edge}"""
        
        return ToolResponse(
            success=True,
            data=h2h_data,
            summary=summary
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def get_matchup_analysis(
    team1: str | int,
    team2: str | int,
    venue_for_team1: str = "home",
    round_number: Optional[int] = None,
    league_id: Optional[int] = None,
) -> ToolResponse:
    """
    Analyze how two teams' styles match up.
    
    Compares:
    - Possession tendencies
    - Attack vs defense metrics
    - xG output vs opponent's defensive quality
    - Home/away factors
    - Key advantages and disadvantages
    
    Args:
        team1: First team (usually home)
        team2: Second team (usually away)
        venue_for_team1: "home" or "away" for team1
        round_number: Round to analyze from (default: latest)
    
    Returns:
        ToolResponse with matchup analysis
    """
    try:
        team1_id = resolve_team(team1)
        team2_id = resolve_team(team2)
        team1_name = get_team_name(team1_id)
        team2_name = get_team_name(team2_id)
        
        if round_number is None:
            round_number = get_current_round()
        
        with db_cursor() as cur:
            # Get both teams' states
            if league_id:
                cur.execute(
                    """
                    SELECT * FROM team_states
                    WHERE team_id IN (%s, %s) AND round_number = %s AND league_id = %s
                    """,
                    (team1_id, team2_id, round_number, league_id)
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM team_states
                    WHERE team_id IN (%s, %s) AND round_number = %s
                    """,
                    (team1_id, team2_id, round_number)
                )
            states = {r["team_id"]: row_to_dict(r) for r in cur.fetchall()}
        
        if team1_id not in states or team2_id not in states:
            return ToolResponse(
                success=False,
                error=f"Missing team state data for round {round_number}"
            )
        
        t1 = states[team1_id]
        t2 = states[team2_id]
        
        # Possession battle prediction
        t1_poss = t1["avg_possession"] or 50
        t2_poss = t2["avg_possession"] or 50
        expected_t1_poss = (t1_poss + (100 - t2_poss)) / 2
        
        if expected_t1_poss > 55:
            possession_edge = team1_name
            possession_desc = f"{team1_name} likely to dominate ball ({expected_t1_poss:.0f}%)"
        elif expected_t1_poss < 45:
            possession_edge = team2_name
            possession_desc = f"{team2_name} likely to dominate ball ({100-expected_t1_poss:.0f}%)"
        else:
            possession_edge = "Even"
            possession_desc = "Contested midfield battle expected"
        
        # Attack vs Defense matchup
        t1_attack = t1["xg_per_game"] or 1.0
        t2_defense = t2["xg_against_per_game"] or 1.2
        t2_attack = t2["xg_per_game"] or 1.0
        t1_defense = t1["xg_against_per_game"] or 1.2
        
        # Expected xG (rough approximation)
        t1_expected_xg = (t1_attack + t2_defense) / 2
        t2_expected_xg = (t2_attack + t1_defense) / 2
        
        # Venue adjustment
        is_home = venue_for_team1 == "home"
        if is_home:
            t1_expected_xg *= 1.1  # Home boost
            t2_expected_xg *= 0.9
        else:
            t1_expected_xg *= 0.9
            t2_expected_xg *= 1.1
        
        # Form comparison
        t1_form = t1["form_points"] or 0
        t2_form = t2["form_points"] or 0
        
        if t1_form > t2_form + 3:
            form_edge = f"{team1_name} in better form"
        elif t2_form > t1_form + 3:
            form_edge = f"{team2_name} in better form"
        else:
            form_edge = "Similar form"
        
        # Key advantages
        t1_advantages = []
        t2_advantages = []
        
        if t1_attack > t2_attack + 0.3:
            t1_advantages.append("Superior attacking output")
        elif t2_attack > t1_attack + 0.3:
            t2_advantages.append("Superior attacking output")
        
        if t1_defense < t2_defense - 0.3:
            t1_advantages.append("Better defensive organization")
        elif t2_defense < t1_defense - 0.3:
            t2_advantages.append("Better defensive organization")
        
        if is_home:
            t1_advantages.append("Home advantage")
        else:
            t2_advantages.append("Home advantage")
        
        if t1["position"] < t2["position"]:
            t1_advantages.append(f"Higher league position (#{t1['position']} vs #{t2['position']})")
        elif t2["position"] < t1["position"]:
            t2_advantages.append(f"Higher league position (#{t2['position']} vs #{t1['position']})")
        
        # Overall assessment
        t1_score = len(t1_advantages) + (t1_expected_xg - t2_expected_xg)
        
        if t1_score > 1.5:
            verdict = f"{team1_name} favored"
        elif t1_score < -1.5:
            verdict = f"{team2_name} favored"
        else:
            verdict = "Competitive match expected"
        
        matchup = {
            "team1": {
                "name": team1_name,
                "venue": venue_for_team1,
                "position": t1["position"],
                "form_points": t1_form,
                "xg_per_game": t1["xg_per_game"],
                "xga_per_game": t1["xg_against_per_game"],
                "expected_xg": round(t1_expected_xg, 2),
            },
            "team2": {
                "name": team2_name,
                "venue": "away" if is_home else "home",
                "position": t2["position"],
                "form_points": t2_form,
                "xg_per_game": t2["xg_per_game"],
                "xga_per_game": t2["xg_against_per_game"],
                "expected_xg": round(t2_expected_xg, 2),
            },
            "predictions": {
                "possession_edge": possession_edge,
                "expected_total_xg": round(t1_expected_xg + t2_expected_xg, 2),
                "form_comparison": form_edge,
            },
            "advantages": {
                "team1": t1_advantages,
                "team2": t2_advantages,
            },
            "verdict": verdict,
        }
        
        summary = f"""**{team1_name} vs {team2_name} Matchup**
{possession_desc}
Expected xG: {t1_expected_xg:.2f} - {t2_expected_xg:.2f}
Form: {form_edge}

{team1_name} advantages: {', '.join(t1_advantages) if t1_advantages else 'None significant'}
{team2_name} advantages: {', '.join(t2_advantages) if t2_advantages else 'None significant'}

**Verdict: {verdict}**"""
        
        return ToolResponse(
            success=True,
            data=matchup,
            summary=summary
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))
