"""
Team-focused tools for the agent.

Tools:
- get_team_state: Full 8-layer KG snapshot
- get_team_form: Recent form and trajectory
- get_team_profile: Style and identity
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import (
    db_cursor,
    row_to_dict,
    resolve_team,
    get_team_name,
    get_current_round,
    ToolResponse,
    format_form_string,
    format_trend,
    describe_position,
)


def get_team_state(
    team: str | int,
    round_number: Optional[int] = None,
) -> ToolResponse:
    """
    Get the full 8-layer KG snapshot for a team at a specific round.
    
    This is the primary tool for understanding a team's complete state:
    - Identity: Who they are
    - Position: Where they stand in the table
    - Form: Recent results and xG trends
    - Style: How they play (possession, formation)
    - Attack: How they create and finish
    - Defense: How they prevent goals
    - Home/Away: Venue performance split
    - Trajectory: Are they improving or declining?
    
    Args:
        team: Team name or ID
        round_number: Round to query (default: latest)
    
    Returns:
        ToolResponse with full team state
    """
    try:
        team_id = resolve_team(team)
        team_name = get_team_name(team_id)
        
        if round_number is None:
            round_number = get_current_round()
        
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT * FROM team_states 
                WHERE team_id = %s AND round_number = %s
                """,
                (team_id, round_number)
            )
            row = cur.fetchone()
            
            if not row:
                return ToolResponse(
                    success=False,
                    error=f"No data for {team_name} at round {round_number}"
                )
            
            state = row_to_dict(row)
        
        # Structure the 8 layers
        layers = {
            "identity": {
                "team_id": team_id,
                "team_name": team_name,
                "round": round_number,
            },
            "position": {
                "position": state["position"],
                "position_desc": describe_position(state["position"], state["played"]),
                "points": state["points"],
                "played": state["played"],
                "wins": state["wins"],
                "draws": state["draws"],
                "losses": state["losses"],
                "goal_difference": state["goal_difference"],
            },
            "form": {
                "form_string": state["form_string"],
                "form_visual": format_form_string(state["form_string"]),
                "form_points": state["form_points"],
                "goals_scored_last5": state["goals_scored_last5"],
                "goals_conceded_last5": state["goals_conceded_last5"],
                "clean_sheets_last5": state["clean_sheets_last5"],
                "xg_for_last5": state["xg_for_last5"],
                "xg_against_last5": state["xg_against_last5"],
                "xg_diff_last5": state["xg_diff_last5"],
            },
            "style": {
                "primary_formation": state["primary_formation"],
                "avg_possession": state["avg_possession"],
            },
            "attack": {
                "goals_for": state["goals_for"],
                "shots_per_game": state["shots_per_game"],
                "shots_on_target_per_game": state["shots_on_target_per_game"],
                "xg_per_game": state["xg_per_game"],
                "big_chances_per_game": state["big_chances_per_game"],
            },
            "defense": {
                "goals_against": state["goals_against"],
                "shots_against_per_game": state["shots_against_per_game"],
                "xg_against_per_game": state["xg_against_per_game"],
            },
            "home_away": {
                "home_record": f"{state['home_wins']}W-{state['home_draws']}D-{state['home_losses']}L",
                "away_record": f"{state['away_wins']}W-{state['away_draws']}D-{state['away_losses']}L",
                "home_points": state["home_points"],
                "away_points": state["away_points"],
            },
            "trajectory": {
                "form_trend": state["form_trend"],
                "trend_visual": format_trend(state["form_trend"]),
                "position_change_last5": state["position_change_last5"],
            },
        }
        
        # Build summary
        summary_parts = [
            f"**{team_name}** (Round {round_number})",
            f"Position: {layers['position']['position_desc']} ({state['points']} pts)",
            f"Form: {layers['form']['form_visual']} ({state['form_points']}/15 pts)",
            f"Trajectory: {layers['trajectory']['trend_visual']}",
        ]
        
        # Add xG insight
        xg_diff = state.get("xg_diff_last5", 0) or 0
        if xg_diff > 1:
            summary_parts.append(f"xG trend: Outperforming (+{xg_diff:.1f} xGD last 5)")
        elif xg_diff < -1:
            summary_parts.append(f"xG trend: Underperforming ({xg_diff:.1f} xGD last 5)")
        
        return ToolResponse(
            success=True,
            data=layers,
            summary="\n".join(summary_parts)
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def get_team_form(
    team: str | int,
    matches: int = 5,
    round_number: Optional[int] = None,
) -> ToolResponse:
    """
    Get detailed form analysis for a team.
    
    Focuses on recent performance trajectory with context:
    - Results and form string
    - xG performance vs actual
    - Goals scored/conceded
    - Clean sheets
    - Momentum indicators
    
    Args:
        team: Team name or ID
        matches: Number of matches to analyze (default: 5)
        round_number: Round to query from (default: latest)
    
    Returns:
        ToolResponse with form analysis
    """
    try:
        team_id = resolve_team(team)
        team_name = get_team_name(team_id)
        
        if round_number is None:
            round_number = get_current_round()
        
        with db_cursor() as cur:
            # Get current state
            cur.execute(
                """
                SELECT * FROM team_states 
                WHERE team_id = %s AND round_number = %s
                """,
                (team_id, round_number)
            )
            current = cur.fetchone()
            
            if not current:
                return ToolResponse(
                    success=False,
                    error=f"No data for {team_name} at round {round_number}"
                )
            
            # Get recent matches for detailed breakdown
            cur.execute(
                """
                SELECT 
                    fm.round_number,
                    fm.home_team_name,
                    fm.away_team_name,
                    fm.home_score,
                    fm.away_score,
                    fm.home_team_id,
                    CASE 
                        WHEN fm.home_team_id = %s THEN 'home'
                        ELSE 'away'
                    END as venue
                FROM fotmob_matches fm
                WHERE (fm.home_team_id = %s OR fm.away_team_id = %s)
                    AND fm.round_number <= %s
                    AND fm.round_number > %s
                ORDER BY fm.round_number DESC
                LIMIT %s
                """,
                (team_id, team_id, team_id, 
                 round_number, round_number - matches, matches)
            )
            recent_matches = [row_to_dict(r) for r in cur.fetchall()]
        
        state = row_to_dict(current)
        
        # Analyze form
        form_analysis = {
            "team": team_name,
            "round": round_number,
            "form_string": state["form_string"],
            "form_visual": format_form_string(state["form_string"]),
            "form_points": state["form_points"],
            "max_points": matches * 3,
            "form_pct": round(state["form_points"] / (matches * 3) * 100, 1) if matches > 0 else 0,
        }
        
        # Goals analysis
        goals_analysis = {
            "scored": state["goals_scored_last5"],
            "conceded": state["goals_conceded_last5"],
            "clean_sheets": state["clean_sheets_last5"],
            "goals_per_game": round(state["goals_scored_last5"] / min(matches, state["played"]), 2) if state["played"] > 0 else 0,
            "conceded_per_game": round(state["goals_conceded_last5"] / min(matches, state["played"]), 2) if state["played"] > 0 else 0,
        }
        
        # xG analysis (luck vs quality)
        xg_analysis = {
            "xg_for": state["xg_for_last5"],
            "xg_against": state["xg_against_last5"],
            "xg_diff": state["xg_diff_last5"],
            "actual_goals": state["goals_scored_last5"],
            "actual_conceded": state["goals_conceded_last5"],
            "finishing_luck": round(state["goals_scored_last5"] - (state["xg_for_last5"] or 0), 2),
            "defensive_luck": round((state["xg_against_last5"] or 0) - state["goals_conceded_last5"], 2),
        }
        
        # Trajectory
        trajectory = {
            "trend": state["form_trend"],
            "trend_visual": format_trend(state["form_trend"]),
            "position_change": state["position_change_last5"],
        }
        
        # Build summary
        summary_parts = [
            f"**{team_name} Form** (Last {matches} matches)",
            f"Results: {form_analysis['form_visual']} ({form_analysis['form_points']}/{form_analysis['max_points']} pts)",
            f"Goals: {goals_analysis['scored']} scored, {goals_analysis['conceded']} conceded ({goals_analysis['clean_sheets']} CS)",
        ]
        
        # xG insight
        if xg_analysis["finishing_luck"] > 1:
            summary_parts.append(f"⚠️ Overperforming xG by {xg_analysis['finishing_luck']:.1f} goals (luck factor)")
        elif xg_analysis["finishing_luck"] < -1:
            summary_parts.append(f"📈 Underperforming xG by {abs(xg_analysis['finishing_luck']):.1f} goals (regression coming?)")
        
        summary_parts.append(f"Trajectory: {trajectory['trend_visual']}")
        
        return ToolResponse(
            success=True,
            data={
                "form": form_analysis,
                "goals": goals_analysis,
                "xg": xg_analysis,
                "trajectory": trajectory,
                "recent_matches": recent_matches,
            },
            summary="\n".join(summary_parts)
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def get_team_profile(
    team: str | int,
    round_number: Optional[int] = None,
) -> ToolResponse:
    """
    Get the playing style profile of a team.
    
    Answers: "How does this team play?"
    - Formation and system
    - Possession tendency
    - Attack patterns (shots, big chances)
    - Defensive approach
    - Home vs away differences
    
    Args:
        team: Team name or ID
        round_number: Round to query (default: latest)
    
    Returns:
        ToolResponse with style profile
    """
    try:
        team_id = resolve_team(team)
        team_name = get_team_name(team_id)
        
        if round_number is None:
            round_number = get_current_round()
        
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT * FROM team_states 
                WHERE team_id = %s AND round_number = %s
                """,
                (team_id, round_number)
            )
            row = cur.fetchone()
            
            if not row:
                return ToolResponse(
                    success=False,
                    error=f"No data for {team_name} at round {round_number}"
                )
            
            state = row_to_dict(row)
        
        # Classify possession style
        possession = state["avg_possession"] or 50
        if possession >= 58:
            possession_style = "Dominant possession"
        elif possession >= 52:
            possession_style = "Possession-oriented"
        elif possession >= 48:
            possession_style = "Balanced"
        elif possession >= 42:
            possession_style = "Counter-attacking"
        else:
            possession_style = "Deep defensive"
        
        # Classify attacking output
        xg_pg = state["xg_per_game"] or 0
        if xg_pg >= 2.0:
            attack_rating = "Elite attacking"
        elif xg_pg >= 1.5:
            attack_rating = "Strong attacking"
        elif xg_pg >= 1.2:
            attack_rating = "Average attacking"
        else:
            attack_rating = "Low attacking output"
        
        # Classify defensive solidity
        xga_pg = state["xg_against_per_game"] or 0
        if xga_pg <= 0.8:
            defense_rating = "Elite defense"
        elif xga_pg <= 1.2:
            defense_rating = "Solid defense"
        elif xga_pg <= 1.5:
            defense_rating = "Average defense"
        else:
            defense_rating = "Leaky defense"
        
        # Home/Away character
        home_ppg = state["home_points"] / max(state["home_wins"] + state["home_draws"] + state["home_losses"], 1)
        away_ppg = state["away_points"] / max(state["away_wins"] + state["away_draws"] + state["away_losses"], 1)
        
        if home_ppg > away_ppg + 0.5:
            venue_profile = "Strong home advantage"
        elif away_ppg > home_ppg + 0.5:
            venue_profile = "Better on the road"
        else:
            venue_profile = "Consistent home/away"
        
        profile = {
            "team": team_name,
            "round": round_number,
            "formation": state["primary_formation"] or "Unknown",
            "style": {
                "possession": possession,
                "possession_style": possession_style,
            },
            "attack": {
                "xg_per_game": xg_pg,
                "shots_per_game": state["shots_per_game"],
                "shots_on_target_per_game": state["shots_on_target_per_game"],
                "big_chances_per_game": state["big_chances_per_game"],
                "rating": attack_rating,
            },
            "defense": {
                "xg_against_per_game": xga_pg,
                "shots_against_per_game": state["shots_against_per_game"],
                "rating": defense_rating,
            },
            "venue": {
                "home_ppg": round(home_ppg, 2),
                "away_ppg": round(away_ppg, 2),
                "profile": venue_profile,
            },
        }
        
        # Build summary
        summary = f"""**{team_name} Profile**
Formation: {profile['formation']}
Style: {possession_style} ({possession:.0f}% avg possession)
Attack: {attack_rating} ({xg_pg:.2f} xG/game)
Defense: {defense_rating} ({xga_pg:.2f} xGA/game)
Venue: {venue_profile}"""
        
        return ToolResponse(
            success=True,
            data=profile,
            summary=summary
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def get_formation_history(
    team: str | int,
    limit: int = 10,
    round_number: Optional[int] = None,
) -> ToolResponse:
    """
    Get the formation history for a team with full context.
    
    Returns list of recent formations with:
    - Opponent and their formation
    - Venue (home/away)
    - Result and score
    - Date and round
    
    Agent should analyze this to detect patterns:
    - Recent formation changes
    - Formation vs opponent type
    - Home vs away differences
    
    Args:
        team: Team name or ID
        limit: Number of matches to return (default: 10)
        round_number: Up to this round (default: latest)
    
    Returns:
        ToolResponse with formation history
    """
    try:
        team_id = resolve_team(team)
        team_name = get_team_name(team_id)
        
        if round_number is None:
            round_number = get_current_round()
        
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT 
                    fm.round_number,
                    fm.match_date,
                    fm.home_team_id,
                    fm.home_team_name,
                    fm.away_team_name,
                    fm.formation_home,
                    fm.formation_away,
                    fm.home_score,
                    fm.away_score
                FROM fotmob_matches fm
                WHERE (fm.home_team_id = %s OR fm.away_team_id = %s)
                    AND fm.round_number <= %s
                ORDER BY fm.round_number DESC
                LIMIT %s
                """,
                (team_id, team_id, round_number, limit)
            )
            matches = [row_to_dict(r) for r in cur.fetchall()]
        
        if not matches:
            return ToolResponse(
                success=False,
                error=f"No matches found for {team_name}"
            )
        
        history = []
        for m in matches:
            is_home = m["home_team_id"] == team_id
            
            if is_home:
                team_formation = m["formation_home"]
                opponent_name = m["away_team_name"]
                opponent_formation = m["formation_away"]
                goals_for = m["home_score"]
                goals_against = m["away_score"]
            else:
                team_formation = m["formation_away"]
                opponent_name = m["home_team_name"]
                opponent_formation = m["formation_home"]
                goals_for = m["away_score"]
                goals_against = m["home_score"]
            
            # Determine result
            if goals_for > goals_against:
                result = "W"
            elif goals_for < goals_against:
                result = "L"
            else:
                result = "D"
            
            history.append({
                "round": m["round_number"],
                "date": m["match_date"],
                "venue": "home" if is_home else "away",
                "formation": team_formation,
                "opponent": opponent_name,
                "opponent_formation": opponent_formation,
                "score": f"{goals_for}-{goals_against}",
                "result": result,
            })
        
        # Extract just formations for quick view
        formations_list = [h["formation"] for h in history]
        
        # Count formations
        formation_counts = {}
        for f in formations_list:
            if f:
                formation_counts[f] = formation_counts.get(f, 0) + 1
        
        # Build summary
        recent_5 = formations_list[:5]
        summary_parts = [
            f"**{team_name} Formation History** (Last {len(history)} matches)",
            f"Recent: {' → '.join(f or '?' for f in recent_5)}",
        ]
        
        if formation_counts:
            counts_str = ", ".join(f"{f}: {c}x" for f, c in sorted(formation_counts.items(), key=lambda x: -x[1]))
            summary_parts.append(f"Usage: {counts_str}")
        
        # Detect recent change
        if len(recent_5) >= 3:
            if recent_5[0] and recent_5[0] != recent_5[2]:
                summary_parts.append(f"⚠️ Recent change: was {recent_5[2]}, now {recent_5[0]}")
        
        return ToolResponse(
            success=True,
            data={
                "team": team_name,
                "matches": history,
                "formation_counts": formation_counts,
                "most_recent": formations_list[0] if formations_list else None,
            },
            summary="\n".join(summary_parts)
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))
