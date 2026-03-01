"""
Skilled Agent - LLM-driven investigation with SKILL.md loaded.

Supports both Anthropic and OpenAI models.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Optional

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
SKILLS_DIR = PROJECT_ROOT / "skills" / "match-intelligence"


def load_skill() -> str:
    """Load the SKILL.md file."""
    skill_path = SKILLS_DIR / "SKILL.md"
    if skill_path.exists():
        content = skill_path.read_text()
        # Strip YAML frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end + 3:].strip()
        return content
    return ""


def load_reference(name: str) -> str:
    """Load a reference file if needed."""
    ref_path = SKILLS_DIR / name
    if ref_path.exists():
        return ref_path.read_text()
    return ""


# Tool definitions for Anthropic function calling
ANTHROPIC_TOOLS = [
    {
        "name": "get_team_state",
        "description": "Get the full 8-layer KG snapshot for a team: identity, position, form, style, attack, defense, home/away splits, trajectory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {"type": "string", "description": "Team name"},
                "round_number": {"type": "integer", "description": "Round number for time-lock"}
            },
            "required": ["team", "round_number"]
        }
    },
    {
        "name": "get_team_form",
        "description": "Get detailed recent form: last N results, xG trends, points, trajectory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {"type": "string"},
                "matches": {"type": "integer", "description": "Number of recent matches (default 5)"},
                "round_number": {"type": "integer"}
            },
            "required": ["team", "round_number"]
        }
    },
    {
        "name": "get_h2h",
        "description": "Get head-to-head history between two teams.",
        "input_schema": {
            "type": "object",
            "properties": {
                "home_team": {"type": "string"},
                "away_team": {"type": "string"},
                "round_number": {"type": "integer"}
            },
            "required": ["home_team", "away_team", "round_number"]
        }
    },
    {
        "name": "get_key_players",
        "description": "Get key players: top scorers, assisters, best rated, in-form players.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {"type": "string"},
                "round_number": {"type": "integer"}
            },
            "required": ["team", "round_number"]
        }
    },
    {
        "name": "get_injuries_impact",
        "description": "Analyze impact of missing/injured players.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {"type": "string"},
                "round_number": {"type": "integer"}
            },
            "required": ["team", "round_number"]
        }
    },
    {
        "name": "get_manager_info",
        "description": "Get manager details: tenure, record, recent results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {"type": "string"},
                "round_number": {"type": "integer"}
            },
            "required": ["team", "round_number"]
        }
    },
    {
        "name": "get_psychological_state",
        "description": "Get team's psychological/mental state: confidence, pressure, momentum.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {"type": "string"},
                "round_number": {"type": "integer"}
            },
            "required": ["team", "round_number"]
        }
    },
    {
        "name": "read_reference",
        "description": "Read a reference file for more detail. Available: BIASES.md, FACTORS.md, INTERPRETATION.md, PATTERNS.md",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Reference file to read"}
            },
            "required": ["filename"]
        }
    },
]

# Tool definitions for OpenAI function calling
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_team_state",
            "description": "Get the full 8-layer KG snapshot for a team: identity, position, form, style, attack, defense, home/away splits, trajectory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "team": {"type": "string", "description": "Team name"},
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
                    "matches": {"type": "integer", "description": "Number of recent matches (default 5)"},
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
            "description": "Get manager details: tenure, record, recent results.",
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
    {
        "type": "function",
        "function": {
            "name": "read_reference",
            "description": "Read a reference file for more detail. Available: BIASES.md, FACTORS.md, INTERPRETATION.md, PATTERNS.md",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Reference file to read"}
                },
                "required": ["filename"]
            }
        }
    },
]


class SkilledAgent:
    """
    LLM-driven agent guided by SKILL.md.
    Supports Anthropic (claude-*) and OpenAI (gpt-*) models.
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_iterations: int = 15,
    ):
        self.model = model
        self.max_iterations = max_iterations
        self.tools_used = []
        self.skill_content = load_skill()
        
        # Determine provider from model name
        if model.startswith("claude") or model.startswith("anthropic"):
            self.provider = "anthropic"
            import anthropic
            self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        else:
            self.provider = "openai"
            import openai
            self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def analyze(
        self,
        home_team: str,
        away_team: str,
        round_number: int,
        match_date: Optional[date] = None,
        backtest_mode: bool = True,
    ) -> AnalysisReport:
        """Run analysis with skill guidance."""
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
        
        # User message
        user_message = f"""Analyze this match:

**{home_name} vs {away_name}** (Round {round_number})

TIME LOCK: Use round_number={data_round} for all tool calls.

Investigate, then give me your read."""

        if self.provider == "anthropic":
            final_response, total_tokens = self._run_anthropic(user_message, data_round)
        else:
            final_response, total_tokens = self._run_openai(user_message, data_round)
        
        elapsed = time.time() - start_time
        
        # Build report
        report = AnalysisReport(
            fixture_id=fixture_id,
            home_team=home_name,
            away_team=away_name,
            round_number=round_number,
            report_markdown=final_response or "No response",
            method="skilled",
            tools_used=self.tools_used,
            tokens_used=total_tokens,
            time_seconds=elapsed,
            model=self.model,
            raw_llm_response=final_response,
        )
        
        self._extract_predictions(report, final_response or "")
        
        return report
    
    def _run_anthropic(self, user_message: str, data_round: int) -> tuple[str, int]:
        """Run with Anthropic API."""
        messages = [{"role": "user", "content": user_message}]
        total_tokens = 0
        final_response = None
        
        for i in range(self.max_iterations):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.skill_content,
                messages=messages,
                tools=ANTHROPIC_TOOLS,
            )
            
            total_tokens += response.usage.input_tokens + response.usage.output_tokens if response.usage else 0
            
            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, 'text'):
                        final_response = block.text
                break
            
            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self._execute_tool(block.name, block.input, data_round)
                        self.tools_used.append(block.name)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        })
                
                messages.append({"role": "user", "content": tool_results})
            else:
                for block in response.content:
                    if hasattr(block, 'text'):
                        final_response = block.text
                break
        
        return final_response, total_tokens
    
    def _run_openai(self, user_message: str, data_round: int) -> tuple[str, int]:
        """Run with OpenAI API."""
        messages = [
            {"role": "system", "content": self.skill_content},
            {"role": "user", "content": user_message},
        ]
        total_tokens = 0
        final_response = None
        
        for i in range(self.max_iterations):
            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=4096,
                messages=messages,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
            )
            
            total_tokens += response.usage.total_tokens if response.usage else 0
            
            message = response.choices[0].message
            
            # Check if done
            if message.tool_calls is None or len(message.tool_calls) == 0:
                final_response = message.content
                break
            
            # Process tool calls
            messages.append(message)
            
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                result = self._execute_tool(func_name, func_args, data_round)
                self.tools_used.append(func_name)
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })
        
        return final_response, total_tokens
    
    def _execute_tool(self, func_name: str, func_args: dict, data_round: int) -> dict:
        """Execute a tool and return the result."""
        
        if func_name == "read_reference":
            filename = func_args.get("filename", "")
            content = load_reference(filename)
            if content:
                return {"success": True, "content": content}
            return {"success": False, "error": f"File not found: {filename}"}
        
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
            
            if result.success:
                return {"success": True, "data": result.data, "summary": result.summary}
            return {"success": False, "error": result.error}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _extract_predictions(self, report: AnalysisReport, text: str) -> None:
        """Extract predictions from response."""
        try:
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
                
                conf_str = pred.get("confidence", "medium")
                if isinstance(conf_str, str):
                    conf_map = {"high": 70, "medium": 55, "low": 40}
                    confidence = conf_map.get(conf_str.lower(), 55)
                else:
                    confidence = conf_str
                
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
                    
        except (json.JSONDecodeError, KeyError, TypeError):
            pass


def analyze_match(home_team: str, away_team: str, round_number: int, model: str = "gpt-4o-mini", **kwargs) -> AnalysisReport:
    """Quick way to analyze a match with Skilled agent."""
    agent = SkilledAgent(model=model)
    return agent.analyze(home_team, away_team, round_number, **kwargs)
