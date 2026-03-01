"""
Manager-focused tools for the agent.

Tools:
- get_manager_info: Current manager and recent history
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import (
    db_cursor,
    row_to_dict,
    resolve_team,
    get_team_name,
    ToolResponse,
)


def get_manager_info(
    team: str | int,
    round_number: Optional[int] = None,
) -> ToolResponse:
    """
    Get manager information for a team at a specific point in time.
    
    Returns:
    - Manager at that round and their record up to that point
    - Previous manager (if changed before that round)
    - Record comparison
    
    Essential for understanding team context and recent changes.
    
    Args:
        team: Team name or ID
        round_number: Get manager info as of this round (default: latest)
    
    Returns:
        ToolResponse with manager info
    """
    try:
        team_id = resolve_team(team)
        team_name = get_team_name(team_id)
        
        if round_number is None:
            # Get latest round from team_states
            with db_cursor() as cur:
                cur.execute("SELECT MAX(round_number) as max_round FROM team_states")
                row = cur.fetchone()
                round_number = row["max_round"] if row else 26
        
        with db_cursor() as cur:
            # Get managers who had matches up to this round
            cur.execute(
                """
                SELECT 
                    manager_id,
                    manager_name,
                    first_match_round,
                    LEAST(last_match_round, %s) as last_match_round,
                    first_match_date,
                    last_match_date,
                    -- Recalculate matches/wins/draws/losses up to round_number
                    -- For now use stored values but filter by round
                    matches,
                    wins,
                    draws,
                    losses,
                    CASE WHEN last_match_round >= %s AND first_match_round <= %s 
                         THEN TRUE ELSE FALSE END as is_current
                FROM manager_history
                WHERE team_id = %s
                  AND first_match_round <= %s
                ORDER BY first_match_round DESC
                """,
                (round_number, round_number, round_number, team_id, round_number)
            )
            managers = [row_to_dict(r) for r in cur.fetchall()]
        
        if not managers:
            return ToolResponse(
                success=False,
                error=f"No manager data for {team_name}"
            )
        
        # Find current manager
        current = next((m for m in managers if m["is_current"]), managers[0])
        
        # Find previous manager (if exists)
        previous = None
        for m in managers:
            if m["manager_id"] != current["manager_id"]:
                previous = m
                break
        
        # Calculate stats
        current_record = f"{current['wins']}W-{current['draws']}D-{current['losses']}L"
        current_matches = current["matches"]
        
        if current_matches > 0:
            current_ppg = round((current["wins"] * 3 + current["draws"]) / current_matches, 2)
            current_win_rate = round(current["wins"] / current_matches * 100, 1)
        else:
            current_ppg = 0
            current_win_rate = 0
        
        data = {
            "team": team_name,
            "current_manager": {
                "name": current["manager_name"],
                "since_round": current["first_match_round"],
                "since_date": current["first_match_date"],
                "matches": current_matches,
                "record": current_record,
                "wins": current["wins"],
                "draws": current["draws"],
                "losses": current["losses"],
                "ppg": current_ppg,
                "win_rate": current_win_rate,
            },
            "manager_changed_this_season": previous is not None,
        }
        
        # Add previous manager info if exists
        if previous:
            prev_matches = previous["matches"]
            prev_record = f"{previous['wins']}W-{previous['draws']}D-{previous['losses']}L"
            
            if prev_matches > 0:
                prev_ppg = round((previous["wins"] * 3 + previous["draws"]) / prev_matches, 2)
            else:
                prev_ppg = 0
            
            data["previous_manager"] = {
                "name": previous["manager_name"],
                "rounds": f"R{previous['first_match_round']}-R{previous['last_match_round']}",
                "matches": prev_matches,
                "record": prev_record,
                "ppg": prev_ppg,
            }
            
            # Comparison
            ppg_diff = current_ppg - prev_ppg
            data["comparison"] = {
                "ppg_change": ppg_diff,
                "improved": ppg_diff > 0,
            }
        
        # Build summary
        summary_parts = [
            f"**{team_name} Manager**",
            f"Current: {current['manager_name']} (since R{current['first_match_round']})",
            f"Record: {current_record} ({current_matches} games, {current_ppg} PPG)",
        ]
        
        if previous:
            direction = "📈" if data["comparison"]["improved"] else "📉"
            summary_parts.append(
                f"Previous: {previous['manager_name']} ({prev_record}, {prev_ppg} PPG)"
            )
            summary_parts.append(
                f"{direction} Change: {ppg_diff:+.2f} PPG"
            )
        
        return ToolResponse(
            success=True,
            data=data,
            summary="\n".join(summary_parts)
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))
