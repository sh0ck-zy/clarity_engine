"""
OpenClaw Agent - LLM-driven investigation with tool access.

This is Method B: the agent decides which tools to call and in what order.
Uses native function calling to let the LLM investigate autonomously.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Optional, Any

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from .base import AnalysisReport
from ..tools import (
    get_team_state,
    get_team_form,
    get_h2h,
    get_key_players,
    get_injuries_impact,
    get_manager_info,
    get_psychological_state,
    resolve_team,
    get_team_name,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Tool definitions for function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_team_state",
            "description": "Get the full 8-layer KG snapshot for a team: identity, position, form, style, attack, defense, home/away splits, trajectory. This is the most comprehensive view of a team.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string", "description": "Team name (e.g., 'Arsenal', 'Chelsea')"},
                    "round_number": {"type": "integer", "description": "Round number for time-lock"}
                },
                "required": ["team", "round_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_team_form",
            "description": "Get detailed recent form: last N results, xG trends, points, trajectory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "matches": {"type": "integer", "default": 5},
                    "round_number": {"type": "integer"}
                },
                "required": ["team", "round_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_h2h",
            "description": "Get head-to-head history between two teams.",
            "parameters": {
                "type": "object",
                "properties": {
                    "home_team": {"type": "string"},
                    "away_team": {"type": "string"},
                    "round_number": {"type": "integer"}
                },
                "required": ["home_team", "away_team", "round_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_key_players",
            "description": "Get key players: top scorers, assisters, best rated, in-form players.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "round_number": {"type": "integer"}
                },
                "required": ["team", "round_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_injuries_impact",
            "description": "Analyze impact of missing/injured players.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "round_number": {"type": "integer"}
                },
                "required": ["team", "round_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_manager_info",
            "description": "Get manager details: tenure, record, recent results, tactical style.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "round_number": {"type": "integer"}
                },
                "required": ["team", "round_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_psychological_state",
            "description": "Get team's psychological/mental state: confidence, pressure, momentum.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "round_number": {"type": "integer"}
                },
                "required": ["team", "round_number"]
            }
        }
    },
]

SYSTEM_PROMPT = """You are a seasoned football analyst investigating a match. You have access to tools to gather data about teams.

INVESTIGATION APPROACH:
1. Start with what you think is most important for THIS specific match
2. Follow interesting leads - if something looks unusual, investigate further
3. Stop when you have enough information - you don't need to use every tool
4. Think like an analyst, not a data collector

You decide what to investigate based on:
- The specific teams involved
- What you already know about them
- What anomalies or interesting patterns you find

When you're ready to make your prediction, output a JSON report.

OUTPUT FORMAT (when done investigating):
```json
{
    "match_story": "2-3 sentences narrative",
    "psychological_edge": {"advantage": "home/away/none", "reason": "...", "impact": "high/medium/low"},
    "game_state_tree": {
        "home_scores_first": "...",
        "goalless_at_60": "...",
        "away_scores_first": "...",
        "most_likely_path": "..."
    },
    "prediction": {
        "result": "H/D/A",
        "scoreline": "X-Y",
        "confidence": 50-70,
        "total_goals": "Over/Under 2.5",
        "btts": "Yes/No",
        "btts_reasoning": "..."
    },
    "reasoning": {
        "for_prediction": ["reason1", "reason2", "reason3"],
        "against_prediction": ["risk1", "risk2"],
        "confidence_check": "..."
    },
    "bold_call": "One pundit sentence",
    "market_angle": {"best_bet": "...", "reasoning": "...", "avoid": "..."}
}
```

Be opinionated. Read the game. Don't hedge."""


class OpenClawAgent:
    """
    LLM-driven agent that investigates matches autonomously.
    Uses function calling to let the model decide which tools to use.
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_iterations: int = 15,
    ):
        self.model = model
        self.max_iterations = max_iterations
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.tools_used = []
    
    def analyze(
        self,
        home_team: str,
        away_team: str,
        round_number: int,
        match_date: Optional[date] = None,
        backtest_mode: bool = True,
    ) -> AnalysisReport:
        """
        Run autonomous analysis for a match.
        The agent decides which tools to use and investigates as needed.
        """
        start_time = time.time()
        self.tools_used = []
        total_tokens = 0
        
        # Resolve team names
        try:
            home_id = resolve_team(home_team)
            away_id = resolve_team(away_team)
            home_name = get_team_name(home_id)
            away_name = get_team_name(away_id)
        except:
            home_name = str(home_team)
            away_name = str(away_team)
        
        # Build fixture_id
        if match_date:
            fixture_id = f"{match_date}_{home_name}_{away_name}".replace(" ", "_")
        else:
            fixture_id = f"R{round_number}_{home_name}_vs_{away_name}".replace(" ", "_")
        
        # Time lock
        data_round = round_number - 1
        
        # Initial message
        user_message = f"""Analyze this match:

MATCH: {home_name} vs {away_name} (Round {round_number})

TIME LOCK: Use round_number={data_round} for all tool calls (data before the match).

Investigate as you see fit. When ready, output your JSON prediction."""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        
        # Agent loop
        final_response = None
        
        for i in range(self.max_iterations):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.7,
            )
            
            total_tokens += response.usage.total_tokens if response.usage else 0
            
            message = response.choices[0].message
            messages.append(message)
            
            # Check if done (no tool calls)
            if not message.tool_calls:
                final_response = message.content
                break
            
            # Execute tool calls
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                # Execute the tool
                result = self._execute_tool(func_name, func_args, data_round)
                self.tools_used.append(func_name)
                
                # Add result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })
        
        elapsed = time.time() - start_time
        
        # Build report
        report = AnalysisReport(
            fixture_id=fixture_id,
            home_team=home_name,
            away_team=away_name,
            round_number=round_number,
            report_markdown=final_response or "No response",
            method="openclaw",
            tools_used=self.tools_used,
            tokens_used=total_tokens,
            time_seconds=elapsed,
            model=self.model,
            raw_llm_response=final_response,
        )
        
        # Extract predictions
        self._extract_predictions(report, final_response or "")
        
        return report
    
    def _execute_tool(
        self,
        func_name: str,
        func_args: dict,
        data_round: int,
    ) -> dict:
        """Execute a tool and return the result."""
        
        # Ensure round_number is set correctly (time lock)
        func_args["round_number"] = data_round
        
        try:
            if func_name == "get_team_state":
                result = get_team_state(func_args["team"], func_args["round_number"])
            elif func_name == "get_team_form":
                matches = func_args.get("matches", 5)
                result = get_team_form(func_args["team"], matches, func_args["round_number"])
            elif func_name == "get_h2h":
                result = get_h2h(func_args["home_team"], func_args["away_team"], func_args["round_number"])
            elif func_name == "get_key_players":
                result = get_key_players(func_args["team"], func_args["round_number"])
            elif func_name == "get_injuries_impact":
                result = get_injuries_impact(func_args["team"], func_args["round_number"])
            elif func_name == "get_manager_info":
                result = get_manager_info(func_args["team"], func_args["round_number"])
            elif func_name == "get_psychological_state":
                result = get_psychological_state(func_args["team"], func_args["round_number"])
            else:
                return {"error": f"Unknown function: {func_name}"}
            
            # Return data and summary
            if result.success:
                return {
                    "success": True,
                    "data": result.data,
                    "summary": result.summary,
                }
            else:
                return {"success": False, "error": result.error}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _extract_predictions(self, report: AnalysisReport, text: str) -> None:
        """Extract predictions from report text."""
        try:
            # Find JSON block
            if "```json" in text:
                json_start = text.find("```json") + 7
                json_end = text.find("```", json_start)
                json_str = text[json_start:json_end].strip()
            elif "{" in text and "}" in text:
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                json_str = text[json_start:json_end]
            else:
                return
            
            data = json.loads(json_str)
            
            if "prediction" in data:
                pred = data["prediction"]
                report.predicted_result = pred.get("result")
                report.predicted_scoreline = pred.get("scoreline")
                
                confidence = pred.get("confidence", 50)
                
                if report.predicted_result == "H":
                    report.home_win_prob = confidence / 100
                    report.draw_prob = (100 - confidence) * 0.4 / 100
                    report.away_win_prob = (100 - confidence) * 0.6 / 100
                elif report.predicted_result == "D":
                    report.draw_prob = confidence / 100
                    report.home_win_prob = (100 - confidence) * 0.55 / 100
                    report.away_win_prob = (100 - confidence) * 0.45 / 100
                elif report.predicted_result == "A":
                    report.away_win_prob = confidence / 100
                    report.draw_prob = (100 - confidence) * 0.4 / 100
                    report.home_win_prob = (100 - confidence) * 0.6 / 100
            
            if "market_angle" in data:
                report.recommended_bet = data["market_angle"].get("best_bet")
                
        except (json.JSONDecodeError, KeyError, TypeError):
            pass


# Quick test function
def analyze_match(
    home_team: str,
    away_team: str,
    round_number: int,
    **kwargs
) -> AnalysisReport:
    """Quick way to analyze a match with OpenClaw agent."""
    agent = OpenClawAgent()
    return agent.analyze(home_team, away_team, round_number, **kwargs)
