"""
OpenClaw Agent - LLM-driven investigation with tool access.

This is Method B: the agent decides which tools to call and in what order.
Uses OpenClaw's sessions_spawn to run an isolated agent session.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Optional

from .base import AnalysisReport

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class OpenClawAgent:
    """
    LLM-driven agent that investigates matches autonomously.
    
    Uses OpenClaw sessions_spawn to run analysis in an isolated session
    with access to the Clarity tools.
    """
    
    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4",
        timeout_seconds: int = 120,
    ):
        self.model = model
        self.timeout_seconds = timeout_seconds
    
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
        
        The agent will decide which tools to use and investigate as needed.
        """
        start_time = time.time()
        
        # Build fixture_id
        if match_date:
            fixture_id = f"{match_date}_{home_team}_{away_team}".replace(" ", "_")
        else:
            fixture_id = f"R{round_number}_{home_team}_vs_{away_team}".replace(" ", "_")
        
        # Build the task prompt
        task = self._build_task(home_team, away_team, round_number, backtest_mode)
        
        # Run via OpenClaw subprocess
        report_text, tools_used, tokens_used = self._run_openclaw(task)
        
        elapsed = time.time() - start_time
        
        # Build report
        report = AnalysisReport(
            fixture_id=fixture_id,
            home_team=home_team,
            away_team=away_team,
            round_number=round_number,
            report_markdown=report_text,
            method="openclaw",
            tools_used=tools_used,
            tokens_used=tokens_used,
            time_seconds=elapsed,
            model=self.model,
            raw_llm_response=report_text,
        )
        
        # Extract predictions
        self._extract_predictions(report, report_text)
        
        return report
    
    def _build_task(
        self,
        home_team: str,
        away_team: str,
        round_number: int,
        backtest_mode: bool,
    ) -> str:
        """Build the task prompt for OpenClaw."""
        
        backtest_note = ""
        if backtest_mode:
            backtest_note = f"""
IMPORTANT - BACKTEST MODE:
- Use round_number={round_number - 1} for ALL tool calls (time lock)
- Do NOT use search_news() - it's disabled in backtest
- Only use data available BEFORE the match
"""
        
        return f"""Analyze this football match and produce a Match Intelligence Report.

MATCH: {home_team} vs {away_team} (Round {round_number})
{backtest_note}

You have access to these tools (in src/tools/):
- get_team_state(team, round_number) - Full 8-layer KG snapshot
- get_team_form(team, matches=5, round_number) - Recent form
- get_h2h(home, away, round_number) - Head to head history
- get_key_players(team, round_number) - Important players
- get_injuries_impact(team, round_number) - Missing players
- get_manager_info(team, round_number) - Manager details
- get_psychological_state(team, round_number) - Mental state

INVESTIGATE as you see fit. You don't need to call every tool - use your judgment.

OUTPUT FORMAT (JSON):
{{
    "match_story": "2-3 sentences narrative",
    "psychological_edge": {{"advantage": "home/away/none", "reason": "...", "impact": "high/medium/low"}},
    "game_state_tree": {{
        "home_scores_first": "...",
        "goalless_at_60": "...",
        "away_scores_first": "...",
        "most_likely_path": "..."
    }},
    "prediction": {{
        "result": "H/D/A",
        "scoreline": "X-Y",
        "confidence": 50-70,
        "total_goals": "Over/Under 2.5",
        "btts": "Yes/No",
        "btts_reasoning": "..."
    }},
    "reasoning": {{
        "for_prediction": ["reason1", "reason2", "reason3"],
        "against_prediction": ["risk1", "risk2"],
        "confidence_check": "..."
    }},
    "bold_call": "One pundit sentence",
    "market_angle": {{"best_bet": "...", "reasoning": "...", "avoid": "..."}}
}}

Think like a football analyst, not a statistician. Read the game."""
    
    def _run_openclaw(self, task: str) -> tuple[str, list[str], int]:
        """
        Run analysis via OpenClaw CLI.
        
        Returns: (report_text, tools_used, tokens_used)
        """
        import subprocess
        
        # Use openclaw CLI to spawn an isolated session
        cmd = [
            "openclaw", "run",
            "--model", self.model,
            "--timeout", str(self.timeout_seconds),
            "--cwd", str(PROJECT_ROOT),
            task
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds + 10,
                cwd=str(PROJECT_ROOT),
            )
            
            output = result.stdout + result.stderr
            
            # Parse tools used from output (look for tool calls)
            tools_used = self._parse_tools_from_output(output)
            
            # Extract the final report (JSON block)
            report_text = self._extract_report(output)
            
            # Estimate tokens (rough: 4 chars per token)
            tokens_used = len(output) // 4
            
            return report_text, tools_used, tokens_used
            
        except subprocess.TimeoutExpired:
            return "Error: Analysis timed out", [], 0
        except Exception as e:
            return f"Error: {str(e)}", [], 0
    
    def _parse_tools_from_output(self, output: str) -> list[str]:
        """Extract tool names from OpenClaw output."""
        tools = []
        tool_patterns = [
            r"get_team_state",
            r"get_team_form",
            r"get_h2h",
            r"get_key_players",
            r"get_injuries_impact",
            r"get_manager_info",
            r"get_psychological_state",
            r"search_news",
        ]
        
        for pattern in tool_patterns:
            matches = re.findall(pattern, output)
            tools.extend(matches)
        
        return tools
    
    def _extract_report(self, output: str) -> str:
        """Extract the final JSON report from output."""
        
        # Look for JSON block
        json_match = re.search(r'\{[^{}]*"match_story"[^{}]*\}', output, re.DOTALL)
        if json_match:
            return json_match.group(0)
        
        # Look for markdown JSON block
        md_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
        if md_match:
            return md_match.group(1)
        
        # Return full output if no JSON found
        return output
    
    def _extract_predictions(self, report: AnalysisReport, text: str) -> None:
        """Extract predictions from report text."""
        try:
            # Find JSON
            if "{" in text and "}" in text:
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                data = json.loads(text[json_start:json_end])
                
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
