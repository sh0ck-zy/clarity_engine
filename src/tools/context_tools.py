"""
Context tools for the agent.

Tools:
- get_psychological_state: Pressure, confidence, desperation signals
- search_news: Recent news/narratives about team (Brave Search API)
- get_odds: Market consensus (placeholder for API-Football)
- build_game_state_tree: Scenario builder for match flow
- odds_to_probability: Convert decimal odds to implied probability
- calculate_value: Calculate expected value of a bet
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

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


# ============================================================================
# Odds helper functions
# ============================================================================

def odds_to_probability(odds: float) -> float:
    """Convert decimal odds to implied probability.
    
    Args:
        odds: Decimal odds (e.g., 2.5)
    
    Returns:
        Implied probability (0-1)
    
    Example:
        odds_to_probability(2.0)  # Returns 0.5 (50%)
        odds_to_probability(1.5)  # Returns 0.667 (66.7%)
    """
    if odds <= 0:
        return 0.0
    return 1.0 / odds


def calculate_value(our_prob: float, odds: float) -> float:
    """Calculate expected value of a bet.
    
    Args:
        our_prob: Our estimated probability (0-1)
        odds: Decimal odds offered
    
    Returns:
        Expected value (positive = value bet)
    
    Example:
        calculate_value(0.5, 2.5)  # Returns 0.25 (25% edge)
        calculate_value(0.4, 2.0)  # Returns -0.2 (negative value)
    """
    implied_prob = odds_to_probability(odds)
    return (our_prob - implied_prob) * odds


def get_psychological_state(
    team: str | int,
    round_number: Optional[int] = None,
) -> ToolResponse:
    """
    Analyze the psychological/mental state of a team.
    
    Infers mental factors from:
    - Recent results and form trends
    - Position and what's at stake
    - xG over/underperformance (luck factor)
    - Upcoming fixture difficulty
    - Historical patterns
    
    Args:
        team: Team name or ID
        round_number: Round to analyze (default: latest)
    
    Returns:
        ToolResponse with psychological analysis
    """
    try:
        team_id = resolve_team(team)
        team_name = get_team_name(team_id)
        
        if round_number is None:
            round_number = get_current_round()
        
        with db_cursor() as cur:
            # Get team state
            cur.execute(
                """
                SELECT * FROM team_states 
                WHERE team_id = %s AND round_number = %s
                """,
                (team_id, round_number)
            )
            state = cur.fetchone()
            
            if not state:
                return ToolResponse(
                    success=False,
                    error=f"No data for {team_name} at round {round_number}"
                )
            
            state = row_to_dict(state)
            
            # Get recent match results with scores
            cur.execute(
                """
                SELECT 
                    round_number,
                    CASE WHEN home_team_id = %s THEN home_score ELSE away_score END as goals_for,
                    CASE WHEN home_team_id = %s THEN away_score ELSE home_score END as goals_against
                FROM fotmob_matches
                WHERE (home_team_id = %s OR away_team_id = %s)
                    AND round_number <= %s
                ORDER BY round_number DESC
                LIMIT 5
                """,
                (team_id, team_id, team_id, team_id, round_number)
            )
            recent = [row_to_dict(r) for r in cur.fetchall()]
        
        # Analyze factors
        factors = []
        pressure_score = 50  # Baseline
        confidence_score = 50
        
        # 1. Position pressure
        position = state["position"]
        if position <= 4:
            factors.append({
                "factor": "Champions League race",
                "impact": "positive" if state["form_points"] >= 9 else "pressure",
                "description": "Fighting for top 4"
            })
            if state["form_points"] < 7:
                pressure_score += 15
        elif position >= 18:
            factors.append({
                "factor": "Relegation battle",
                "impact": "desperation",
                "description": "In the drop zone - every point matters"
            })
            pressure_score += 25
            confidence_score -= 20
        elif position >= 15:
            factors.append({
                "factor": "Relegation threat",
                "impact": "pressure",
                "description": "Looking over shoulder at relegation zone"
            })
            pressure_score += 15
        
        # 2. Form trajectory
        form_trend = state["form_trend"]
        if form_trend == "improving":
            factors.append({
                "factor": "Rising confidence",
                "impact": "positive",
                "description": "Results improving - momentum building"
            })
            confidence_score += 15
        elif form_trend == "declining":
            factors.append({
                "factor": "Crisis brewing",
                "impact": "negative",
                "description": "Results declining - pressure mounting"
            })
            confidence_score -= 15
            pressure_score += 10
        
        # 3. Recent results pattern
        form_string = state["form_string"] or ""
        if form_string.startswith("LLL"):
            factors.append({
                "factor": "Losing streak",
                "impact": "crisis",
                "description": "Three straight losses - confidence shattered"
            })
            confidence_score -= 25
            pressure_score += 20
        elif form_string.startswith("WWW"):
            factors.append({
                "factor": "Winning streak",
                "impact": "positive",
                "description": "Three straight wins - riding high"
            })
            confidence_score += 25
        elif form_string.startswith("DD") or "DDD" in form_string:
            factors.append({
                "factor": "Draw specialists",
                "impact": "neutral",
                "description": "Struggling to win - may settle for points"
            })
        
        # 4. xG luck factor
        xg_diff = (state["xg_for_last5"] or 0) - (state["goals_scored_last5"] or 0)
        if xg_diff > 2:
            factors.append({
                "factor": "Underperforming xG",
                "impact": "frustration",
                "description": f"Creating chances but not scoring ({xg_diff:.1f} xG wasted)"
            })
            pressure_score += 10
        elif xg_diff < -2:
            factors.append({
                "factor": "Overperforming xG",
                "impact": "fragile",
                "description": f"Results better than performance ({abs(xg_diff):.1f} lucky goals)"
            })
        
        # 5. Big match mentality (from H2H patterns - placeholder)
        # Would need more data to properly assess
        
        # Calculate overall state
        pressure_level = "Low"
        if pressure_score > 70:
            pressure_level = "Extreme"
        elif pressure_score > 55:
            pressure_level = "High"
        elif pressure_score > 40:
            pressure_level = "Moderate"
        
        confidence_level = "Neutral"
        if confidence_score > 65:
            confidence_level = "High"
        elif confidence_score > 55:
            confidence_level = "Good"
        elif confidence_score < 35:
            confidence_level = "Low"
        elif confidence_score < 45:
            confidence_level = "Fragile"
        
        # Determine mindset
        if pressure_score > 60 and confidence_score < 40:
            mindset = "🔴 Crisis mode - desperate for results"
        elif pressure_score > 50 and confidence_score > 55:
            mindset = "🟡 Pressure but handling it"
        elif confidence_score > 60:
            mindset = "🟢 Confident - playing freely"
        elif position >= 18:
            mindset = "🔴 Relegation fear - tight and nervous"
        else:
            mindset = "⚪ Neutral - nothing special at stake"
        
        psych_data = {
            "team": team_name,
            "round": round_number,
            "position": position,
            "position_context": describe_position(position, state["played"]),
            "form": format_form_string(form_string),
            "pressure": {
                "score": pressure_score,
                "level": pressure_level,
            },
            "confidence": {
                "score": confidence_score,
                "level": confidence_level,
            },
            "factors": factors,
            "mindset": mindset,
        }
        
        # Build summary
        summary_parts = [
            f"**{team_name} Psychological State**",
            f"Position: {describe_position(position, state['played'])}",
            f"Form: {format_form_string(form_string)}",
            f"Pressure: {pressure_level} ({pressure_score}/100)",
            f"Confidence: {confidence_level} ({confidence_score}/100)",
            f"",
            f"**Mindset:** {mindset}",
        ]
        
        if factors:
            summary_parts.append("")
            summary_parts.append("Key factors:")
            for f in factors[:3]:
                icon = "✅" if f["impact"] == "positive" else "⚠️" if f["impact"] in ["pressure", "negative"] else "🔴"
                summary_parts.append(f"  {icon} {f['description']}")
        
        return ToolResponse(
            success=True,
            data=psych_data,
            summary="\n".join(summary_parts)
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def search_news(
    team: str | int,
    query: Optional[str] = None,
    limit: int = 5,
) -> ToolResponse:
    """
    Search for recent news about a team using Brave Search API.
    
    Searches for football news, injuries, press conferences, etc.
    
    Args:
        team: Team name or ID
        query: Additional search terms (e.g., "injury", "transfer")
        limit: Maximum number of results (default: 5)
    
    Returns:
        ToolResponse with news articles
    
    Note:
        Requires BRAVE_API_KEY environment variable.
        Falls back to empty results if API not configured.
    """
    try:
        team_id = resolve_team(team)
        team_name = get_team_name(team_id)
        
        # Build search query
        search_query = f"{team_name} football news"
        if query:
            search_query += f" {query}"
        
        # Check for Brave API key
        api_key = os.getenv("BRAVE_API_KEY")
        
        if not api_key:
            return ToolResponse(
                success=True,
                data={
                    "team": team_name,
                    "query": search_query,
                    "articles": [],
                    "total": 0,
                    "message": "BRAVE_API_KEY not configured. Set it to enable news search.",
                },
                summary=f"**{team_name} News**\n⚠️ Brave API not configured - set BRAVE_API_KEY"
            )
        
        # Call Brave News Search API
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        }
        
        params = {
            "q": search_query,
            "count": limit,
            "freshness": "pw",  # Past week
        }
        
        response = requests.get(
            "https://api.search.brave.com/res/v1/news/search",
            headers=headers,
            params=params,
            timeout=10,
        )
        
        if response.status_code != 200:
            return ToolResponse(
                success=False,
                error=f"Brave API error: {response.status_code}"
            )
        
        data = response.json()
        results = data.get("results", [])
        
        # Format articles
        articles = []
        for r in results[:limit]:
            articles.append({
                "title": r.get("title", ""),
                "source": r.get("meta_url", {}).get("hostname", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
                "date": r.get("age", ""),
            })
        
        # Build summary
        summary_parts = [f"**{team_name} News** ({len(articles)} articles)"]
        for i, article in enumerate(articles[:3], 1):
            title = article["title"][:60] + "..." if len(article["title"]) > 60 else article["title"]
            summary_parts.append(f"{i}. {title}")
            summary_parts.append(f"   Source: {article['source']} | {article['date']}")
        
        if not articles:
            summary_parts.append("No recent news found.")
        
        return ToolResponse(
            success=True,
            data={
                "team": team_name,
                "query": search_query,
                "articles": articles,
                "total": len(articles),
            },
            summary="\n".join(summary_parts)
        )
        
    except requests.exceptions.RequestException as e:
        return ToolResponse(success=False, error=f"Network error: {str(e)}")
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def search_press_conference(team: str | int) -> ToolResponse:
    """
    Search for recent press conference news for a team.
    
    Convenience wrapper around search_news for manager press conferences.
    
    Args:
        team: Team name or ID
    
    Returns:
        ToolResponse with press conference news
    """
    return search_news(team, query="manager press conference", limit=3)


def get_odds(
    team1: str | int,
    team2: str | int,
    market: str = "1x2",
) -> ToolResponse:
    """
    Get betting odds/market consensus for a match.
    
    NOTE: This is a placeholder. Full implementation would integrate with:
    - API-Football odds endpoint
    - Odds comparison sites
    
    Args:
        team1: Home team
        team2: Away team
        market: Odds market (1x2, over_under, btts, etc.)
    
    Returns:
        ToolResponse with odds data (placeholder)
    """
    try:
        team1_id = resolve_team(team1)
        team2_id = resolve_team(team2)
        team1_name = get_team_name(team1_id)
        team2_name = get_team_name(team2_id)
        
        # Placeholder response
        return ToolResponse(
            success=True,
            data={
                "match": f"{team1_name} vs {team2_name}",
                "market": market,
                "odds": None,
                "message": "Odds not yet implemented. Would integrate with API-Football.",
            },
            summary=f"**{team1_name} vs {team2_name} Odds**\n⚠️ Odds integration pending - connect API-Football"
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))


def build_game_state_tree(
    team1: str | int,
    team2: str | int,
    venue_for_team1: str = "home",
    round_number: Optional[int] = None,
) -> ToolResponse:
    """
    Build a game state tree showing how the match might evolve.
    
    Creates scenarios based on:
    - First goal impact
    - Red card scenarios
    - Late game situations
    - Expected game flow
    
    This helps the agent reason about match dynamics,
    not just static pre-match states.
    
    Args:
        team1: Home team
        team2: Away team
        venue_for_team1: "home" or "away"
        round_number: Round to analyze from (default: latest)
    
    Returns:
        ToolResponse with game state scenarios
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
        
        is_home = venue_for_team1 == "home"
        
        # Expected xG for scenario building
        t1_xg = (t1["xg_per_game"] or 1.2)
        t2_xg = (t2["xg_per_game"] or 1.2)
        
        # Analyze team characteristics for scenarios
        t1_needs_win = t1["position"] >= 17 or (t1["position"] <= 5 and t1["form_points"] < 7)
        t2_needs_win = t2["position"] >= 17 or (t2["position"] <= 5 and t2["form_points"] < 7)
        
        t1_defensive = (t1["avg_possession"] or 50) < 48
        t2_defensive = (t2["avg_possession"] or 50) < 48
        
        # Build scenarios
        scenarios = {
            "kickoff": {
                "state": "0-0",
                "description": "Match begins",
                "t1_approach": "Normal" if is_home else "Cautious start",
                "t2_approach": "Cautious start" if is_home else "Normal",
            },
            "t1_scores_first": {
                "state": "1-0",
                "probability": 0.45 if is_home else 0.35,
                "description": f"{team1_name} takes the lead",
                "t1_response": "Control game, manage lead" if not t1_needs_win else "Push for second",
                "t2_response": "Must open up, risk counters" if t2_needs_win else "Patient, wait for chances",
                "likely_outcome": "More space for counters, increased tempo",
            },
            "t2_scores_first": {
                "state": "0-1",
                "probability": 0.35 if is_home else 0.45,
                "description": f"{team2_name} takes the lead",
                "t1_response": "Must attack, leave gaps" if is_home or t1_needs_win else "May struggle to respond",
                "t2_response": "Defend lead, hit on break" if t2_defensive else "Continue attacking",
                "likely_outcome": "Stretched game, end-to-end possible",
            },
            "tight_at_60": {
                "state": "0-0 or 1-1 at 60'",
                "probability": 0.40,
                "description": "Match still in balance",
                "t1_response": "Substitutions to change game" if t1_needs_win else "May accept draw",
                "t2_response": "May settle for point" if not t2_needs_win else "Push for winner",
                "likely_outcome": "Tactical changes, fresh legs vs tired legs",
            },
            "late_drama": {
                "state": "Within 1 goal at 80'",
                "description": "Desperate final push",
                "t1_response": "All-out attack if behind" if t1_needs_win else "See out result",
                "t2_response": "All-out attack if behind" if t2_needs_win else "See out result",
                "likely_outcome": "Set pieces become crucial, chaos possible",
            },
        }
        
        # Game flow prediction
        if t1_defensive and t2_defensive:
            flow_prediction = "Low tempo, few chances, set pieces key"
        elif not t1_defensive and not t2_defensive:
            flow_prediction = "Open game, goals likely, end-to-end"
        elif t1_defensive:
            flow_prediction = f"{team2_name} to dominate ball, {team1_name} on break"
        else:
            flow_prediction = f"{team1_name} to dominate ball, {team2_name} on break"
        
        # Key moments to watch
        key_moments = [
            "First 15 minutes: Who sets the tempo?",
            "First goal: How do both teams respond?",
            "Half-time: Tactical adjustments expected?",
            "60-70 minutes: Substitution impact",
            "Final 10: Who has more to play for?",
        ]
        
        tree_data = {
            "match": f"{team1_name} vs {team2_name}",
            "venue": venue_for_team1,
            "scenarios": scenarios,
            "flow_prediction": flow_prediction,
            "key_moments": key_moments,
            "stakes": {
                "team1_needs_win": t1_needs_win,
                "team2_needs_win": t2_needs_win,
            },
        }
        
        summary = f"""**{team1_name} vs {team2_name} Game State Tree**

**Expected Flow:** {flow_prediction}

**If {team1_name} scores first:**
→ {scenarios['t1_scores_first']['t2_response']}

**If {team2_name} scores first:**
→ {scenarios['t2_scores_first']['t1_response']}

**Key Moments:**
{chr(10).join(f'• {m}' for m in key_moments[:3])}

**Stakes:** {'High pressure on both' if t1_needs_win and t2_needs_win else f"{team1_name} more desperate" if t1_needs_win else f"{team2_name} more desperate" if t2_needs_win else "Nothing critical at stake"}"""
        
        return ToolResponse(
            success=True,
            data=tree_data,
            summary=summary
        )
        
    except Exception as e:
        return ToolResponse(success=False, error=str(e))
