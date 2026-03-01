"""
Coded Agent - Fixed sequence of tool calls + single LLM analysis.

This is Method A: deterministic data gathering, then one LLM call to analyze.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Optional

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


class CodedAgent:
    """
    Fixed-sequence agent: always calls the same tools in the same order,
    then sends everything to an LLM for analysis.
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        prompt_file: str = "prompts/analysis.txt",
    ):
        self.model = model
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt_path = PROJECT_ROOT / prompt_file
        with open(prompt_path, "r") as f:
            self.system_prompt = f.read()
        
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
        Run full analysis for a match.
        
        Args:
            home_team: Home team name or ID
            away_team: Away team name or ID
            round_number: Round number for time-lock (uses round_number - 1 for data)
            match_date: Match date (for fixture_id)
            backtest_mode: If True, disables news search
        
        Returns:
            AnalysisReport with full analysis
        """
        start_time = time.time()
        self.tools_used = []
        
        # Resolve team IDs and names
        home_id = resolve_team(home_team)
        away_id = resolve_team(away_team)
        home_name = get_team_name(home_id)
        away_name = get_team_name(away_id)
        
        # Time lock: use data from BEFORE the match
        data_round = round_number - 1
        
        # Build fixture_id
        if match_date:
            fixture_id = f"{match_date}_{home_name}_{away_name}".replace(" ", "_")
        else:
            fixture_id = f"R{round_number}_{home_name}_vs_{away_name}".replace(" ", "_")
        
        # ===== PHASE 1: Gather data (fixed sequence) =====
        context = self._gather_context(
            home_id, away_id, 
            home_name, away_name,
            data_round,
            backtest_mode
        )
        
        # ===== PHASE 2: Call LLM for analysis =====
        report_text, tokens_used = self._generate_analysis(
            home_name, away_name, context
        )
        
        elapsed = time.time() - start_time
        
        # ===== PHASE 3: Build report =====
        report = AnalysisReport(
            fixture_id=fixture_id,
            home_team=home_name,
            away_team=away_name,
            round_number=round_number,
            report_markdown=report_text,
            method="coded",
            tools_used=self.tools_used,
            tokens_used=tokens_used,
            time_seconds=elapsed,
            model=self.model,
            raw_context=context,
            raw_llm_response=report_text,
        )
        
        # Try to extract predictions from report
        self._extract_predictions(report, report_text)
        
        return report
    
    def _gather_context(
        self,
        home_id: int,
        away_id: int,
        home_name: str,
        away_name: str,
        round_number: int,
        backtest_mode: bool,
    ) -> dict:
        """Gather all context using fixed tool sequence."""
        
        context = {
            "round_number": round_number,
            "home": {},
            "away": {},
            "matchup": {},
        }
        
        # 1. Team states (8-layer KG)
        home_state = get_team_state(home_id, round_number)
        self.tools_used.append("get_team_state")
        if home_state.success:
            context["home"]["state"] = home_state.data
            context["home"]["summary"] = home_state.summary
        
        away_state = get_team_state(away_id, round_number)
        self.tools_used.append("get_team_state")
        if away_state.success:
            context["away"]["state"] = away_state.data
            context["away"]["summary"] = away_state.summary
        
        # 2. Form details
        home_form = get_team_form(home_id, matches=5, round_number=round_number)
        self.tools_used.append("get_team_form")
        if home_form.success:
            context["home"]["form"] = home_form.data
        
        away_form = get_team_form(away_id, matches=5, round_number=round_number)
        self.tools_used.append("get_team_form")
        if away_form.success:
            context["away"]["form"] = away_form.data
        
        # 3. Key players
        home_players = get_key_players(home_id, round_number=round_number)
        self.tools_used.append("get_key_players")
        if home_players.success:
            context["home"]["key_players"] = home_players.data
        
        away_players = get_key_players(away_id, round_number=round_number)
        self.tools_used.append("get_key_players")
        if away_players.success:
            context["away"]["key_players"] = away_players.data
        
        # 4. Injuries
        home_injuries = get_injuries_impact(home_id, round_number=round_number)
        self.tools_used.append("get_injuries_impact")
        if home_injuries.success:
            context["home"]["injuries"] = home_injuries.data
        
        away_injuries = get_injuries_impact(away_id, round_number=round_number)
        self.tools_used.append("get_injuries_impact")
        if away_injuries.success:
            context["away"]["injuries"] = away_injuries.data
        
        # 5. Manager info
        home_manager = get_manager_info(home_id, round_number=round_number)
        self.tools_used.append("get_manager_info")
        if home_manager.success:
            context["home"]["manager"] = home_manager.data
        
        away_manager = get_manager_info(away_id, round_number=round_number)
        self.tools_used.append("get_manager_info")
        if away_manager.success:
            context["away"]["manager"] = away_manager.data
        
        # 6. Psychological state
        home_psych = get_psychological_state(home_id, round_number=round_number)
        self.tools_used.append("get_psychological_state")
        if home_psych.success:
            context["home"]["psychological"] = home_psych.data
        
        away_psych = get_psychological_state(away_id, round_number=round_number)
        self.tools_used.append("get_psychological_state")
        if away_psych.success:
            context["away"]["psychological"] = away_psych.data
        
        # 7. Head-to-head
        h2h = get_h2h(home_id, away_id, round_number=round_number)
        self.tools_used.append("get_h2h")
        if h2h.success:
            context["matchup"]["h2h"] = h2h.data
            context["matchup"]["h2h_summary"] = h2h.summary
        
        return context
    
    def _generate_analysis(
        self,
        home_name: str,
        away_name: str,
        context: dict,
    ) -> tuple[str, int]:
        """Send context to LLM and get analysis."""
        
        user_message = f"""
MATCH: {home_name} vs {away_name} (Round {context['round_number'] + 1})

=== HOME TEAM: {home_name} ===
{context['home'].get('summary', 'No data')}

Psychological State: {json.dumps(context['home'].get('psychological', {}), indent=2)}

Key Players: {json.dumps(context['home'].get('key_players', {}), indent=2)}

Injuries: {json.dumps(context['home'].get('injuries', {}), indent=2)}

Manager: {json.dumps(context['home'].get('manager', {}), indent=2)}

=== AWAY TEAM: {away_name} ===
{context['away'].get('summary', 'No data')}

Psychological State: {json.dumps(context['away'].get('psychological', {}), indent=2)}

Key Players: {json.dumps(context['away'].get('key_players', {}), indent=2)}

Injuries: {json.dumps(context['away'].get('injuries', {}), indent=2)}

Manager: {json.dumps(context['away'].get('manager', {}), indent=2)}

=== HEAD TO HEAD ===
{context['matchup'].get('h2h_summary', 'No H2H data')}

---

Now analyze this match and provide your prediction.
"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
        )
        
        report_text = response.choices[0].message.content
        tokens_used = response.usage.total_tokens if response.usage else 0
        
        return report_text, tokens_used
    
    def _extract_predictions(self, report: AnalysisReport, text: str) -> None:
        """Try to extract structured predictions from report text."""
        
        # Try to parse as JSON first (if LLM followed the prompt format)
        try:
            # Find JSON block
            if "```json" in text:
                json_start = text.find("```json") + 7
                json_end = text.find("```", json_start)
                json_str = text[json_start:json_end].strip()
            elif "{" in text and "}" in text:
                # Try to find JSON object
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                json_str = text[json_start:json_end]
            else:
                return
            
            data = json.loads(json_str)
            
            # Extract prediction
            if "prediction" in data:
                pred = data["prediction"]
                report.predicted_result = pred.get("result")
                report.predicted_scoreline = pred.get("scoreline")
                
                confidence = pred.get("confidence", 50)
                
                # Convert result + confidence to probabilities
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
            
            # Extract recommended bet
            if "market_angle" in data:
                report.recommended_bet = data["market_angle"].get("best_bet")
        
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # Could not parse, leave fields as None


# Convenience function
def analyze_match(
    home_team: str,
    away_team: str,
    round_number: int,
    **kwargs
) -> AnalysisReport:
    """Quick way to analyze a match."""
    agent = CodedAgent()
    return agent.analyze(home_team, away_team, round_number, **kwargs)
