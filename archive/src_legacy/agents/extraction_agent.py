"""
Extraction Agent - AI-Powered Data Enrichment with Web Search

This agent uses LLM + Web Search to extract structured football data.
It follows the principle: EXTRACT, DON'T INVENT.

The agent:
1. Searches the web for current information
2. Extracts ONLY factual data in structured format
3. Returns data that can be validated against schemas

Key design decisions:
- Prioritizes Claude (Anthropic) for best structured extraction
- Falls back to Gemini with Google Search grounding
- Falls back to OpenAI if others unavailable
- Always returns structured JSON matching schemas
- Never generates opinions or predictions
"""

import os
import json
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date
from dataclasses import asdict

logger = logging.getLogger(__name__)


class ExtractionAgent:
    """
    Agent that extracts structured football data using LLM + Web Search.

    Architecture:
    1. Research phase: Search web for information
    2. Extract phase: Parse into structured JSON
    3. Validate phase: Check against schemas (done externally)

    Priority order: Claude > Gemini > OpenAI
    """

    def __init__(
        self,
        provider: str = "claude",  # "claude", "gemini", or "openai"
        claude_model: str = "claude-3-5-sonnet-20241022",
        gemini_model: str = "gemini-2.5-flash",
        openai_model: str = "gpt-4o-mini"
    ):
        """
        Initialize the extraction agent.

        Args:
            provider: Primary provider ("claude", "gemini", "openai")
            claude_model: Claude model to use
            gemini_model: Gemini model to use
            openai_model: OpenAI model to use
        """
        self.provider = provider
        self.claude_model = claude_model
        self.gemini_model = gemini_model
        self.openai_model = openai_model

        # Initialize clients
        self._claude_client = None
        self._gemini_client = None
        self._openai_client = None
        self._init_clients()

    def _init_clients(self):
        """Initialize LLM clients in priority order."""
        # Try Claude (Anthropic) - BEST for structured extraction
        try:
            from anthropic import Anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                self._claude_client = Anthropic(api_key=api_key)
                logger.info("Claude client initialized")
        except ImportError:
            logger.warning("anthropic not installed")
        except Exception as e:
            logger.warning(f"Failed to init Claude: {e}")

        # Try Gemini - GOOD for web search grounding
        try:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                self._gemini_client = genai.Client(api_key=api_key)
                logger.info("Gemini client initialized")
        except ImportError:
            logger.warning("google-genai not installed")
        except Exception as e:
            logger.warning(f"Failed to init Gemini: {e}")

        # Try OpenAI - FALLBACK
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self._openai_client = OpenAI(api_key=api_key)
                logger.info("OpenAI client initialized")
        except ImportError:
            logger.warning("openai not installed")
        except Exception as e:
            logger.warning(f"Failed to init OpenAI: {e}")

    # ============================================================
    # CORE EXTRACTION METHODS
    # ============================================================

    def _extract_with_claude(self, prompt: str) -> Tuple[Optional[Dict], str]:
        """
        Extract data using Claude (Anthropic).

        Claude excels at structured extraction with strong instruction following.
        Uses extended thinking for web research simulation.

        Returns:
            (extracted_data, raw_response)
        """
        if not self._claude_client:
            return None, "Claude client not available"

        try:
            # Add instruction to search web mentally and extract facts
            enhanced_prompt = f"""You are a football data extraction agent with access to your knowledge base.

{prompt}

CRITICAL INSTRUCTIONS:
1. Think through what you know about recent football matches, injuries, and team news
2. Extract ONLY factual information from your knowledge
3. If you don't have recent information, return empty arrays/null values
4. Output ONLY valid JSON matching the requested schema
5. Do NOT make up data - better to return empty than incorrect

Remember: The output will be validated with cross-checks. Any inconsistencies will cause rejection."""

            response = self._claude_client.messages.create(
                model=self.claude_model,
                max_tokens=4096,
                temperature=0.1,  # Low temperature for factual extraction
                messages=[
                    {"role": "user", "content": enhanced_prompt}
                ]
            )

            raw_text = response.content[0].text

            # Extract JSON from response
            extracted = self._parse_json_from_response(raw_text)
            return extracted, raw_text

        except Exception as e:
            logger.error(f"Claude extraction failed: {e}")
            return None, str(e)

    def _extract_with_gemini(
        self,
        prompt: str,
        use_search: bool = True
    ) -> Tuple[Optional[Dict], str]:
        """
        Extract data using Gemini with Google Search grounding.

        Returns:
            (extracted_data, raw_response)
        """
        if not self._gemini_client:
            return None, "Gemini client not available"

        try:
            from google.genai import types

            # Configure grounding with Google Search
            config = types.GenerateContentConfig(
                temperature=0.1,  # Low temperature for factual extraction
                tools=[types.Tool(google_search=types.GoogleSearch())] if use_search else None
            )

            response = self._gemini_client.models.generate_content(
                model=self.gemini_model,
                contents=prompt,
                config=config
            )

            raw_text = response.text

            # Extract JSON from response
            extracted = self._parse_json_from_response(raw_text)
            return extracted, raw_text

        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            return None, str(e)

    def _extract_with_openai(self, prompt: str) -> Tuple[Optional[Dict], str]:
        """
        Extract data using OpenAI (no web search, uses training data).

        Returns:
            (extracted_data, raw_response)
        """
        if not self._openai_client:
            return None, "OpenAI client not available"

        try:
            response = self._openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a football data extraction agent. Extract ONLY factual information. Output ONLY valid JSON, no explanations."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )

            raw_text = response.choices[0].message.content
            extracted = self._parse_json_from_response(raw_text)
            return extracted, raw_text

        except Exception as e:
            logger.error(f"OpenAI extraction failed: {e}")
            return None, str(e)

    def _parse_json_from_response(self, text: str) -> Optional[Dict]:
        """Extract JSON from LLM response text."""
        if not text:
            return None

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in markdown
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\{[\s\S]*\}'
        ]

        for pattern in json_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    json_str = match.group(1) if '```' in pattern else match.group(0)
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue

        return None

    def _extract(self, prompt: str, use_search: bool = True) -> Tuple[Optional[Dict], str]:
        """
        Extract data using best available method.

        Priority: Claude > Gemini > OpenAI

        Returns:
            (extracted_data, raw_response)
        """
        # Try Claude first (best for structured extraction)
        if self._claude_client and self.provider == "claude":
            data, raw = self._extract_with_claude(prompt)
            if data is not None:
                logger.info("Claude extraction successful")
                return data, raw

        # Try Gemini second (has web search grounding)
        if self._gemini_client and self.provider in ["gemini", "claude"]:
            data, raw = self._extract_with_gemini(prompt, use_search)
            if data is not None:
                logger.info("Gemini extraction successful")
                return data, raw

        # Fallback to OpenAI
        if self._openai_client:
            data, raw = self._extract_with_openai(prompt)
            if data is not None:
                logger.info("OpenAI extraction successful")
                return data, raw

        # Last resort: try any available client
        if self._claude_client:
            logger.warning("Falling back to Claude as last resort")
            return self._extract_with_claude(prompt)
        if self._gemini_client:
            logger.warning("Falling back to Gemini as last resort")
            return self._extract_with_gemini(prompt, use_search)
        if self._openai_client:
            logger.warning("Falling back to OpenAI as last resort")
            return self._extract_with_openai(prompt)

        return None, "No LLM client available"

    # ============================================================
    # SPECIFIC EXTRACTION METHODS
    # ============================================================

    def extract_injuries(
        self,
        team_name: str,
        league: str = "Premier League",
        match_date: Optional[date] = None
    ) -> Dict:
        """
        Extract current injuries for a team.

        Returns:
            {
                "injuries": [...],
                "confidence": 0.0-1.0,
                "source": "gemini|openai",
                "raw_response": "..."
            }
        """
        match_date = match_date or date.today()

        prompt = f"""You are a football data extraction agent. Extract ONLY factual injury information.

TEAM: {team_name}
LEAGUE: {league}
DATE: {match_date.isoformat()}

Search the web and extract current injuries for {team_name}.

OUTPUT FORMAT (JSON only, no explanation):
{{
    "injuries": [
        {{
            "player_name": "exact player name",
            "position": "GK|DEF|MID|FWD",
            "injury_type": "hamstring|knee|illness|suspended|etc",
            "expected_return": "date or timeframe or null",
            "is_key_player": true/false,
            "source_quote": "direct quote from source if available"
        }}
    ],
    "confidence": 0.0-1.0
}}

RULES:
- Only include injuries confirmed by reliable sources
- If unsure about a player, DO NOT include them
- Position must be one of: GK, DEF, MID, FWD
- Return empty array if no confirmed injuries found
- is_key_player = true only for regular starters or star players
"""

        data, raw = self._extract(prompt, use_search=True)

        return {
            "injuries": data.get("injuries", []) if data else [],
            "confidence": data.get("confidence", 0.0) if data else 0.0,
            "source": "gemini" if self._gemini_client else "openai",
            "raw_response": raw
        }

    def extract_form(
        self,
        team_name: str,
        league: str = "Premier League",
        match_date: Optional[date] = None
    ) -> Dict:
        """
        Extract last 5 matches form for a team.

        Returns:
            {
                "form": {...},
                "confidence": 0.0-1.0,
                "source": "...",
                "raw_response": "..."
            }
        """
        match_date = match_date or date.today()

        prompt = f"""You are a football data extraction agent. Extract ONLY factual match results.

TEAM: {team_name}
LEAGUE: {league}
DATE: {match_date.isoformat()}

Extract the last 5 completed matches for {team_name} BEFORE {match_date.isoformat()}.

OUTPUT FORMAT (JSON only, no explanation):
{{
    "last_5": [
        {{
            "opponent": "opponent team name",
            "result": "W|D|L",
            "score": "goals_for-goals_against",
            "venue": "H|A",
            "date": "YYYY-MM-DD"
        }}
    ],
    "current_streak": "nW|nD|nL",
    "goals_scored_last_5": total,
    "goals_conceded_last_5": total,
    "confidence": 0.0-1.0
}}

RULES:
- Must have EXACTLY 5 matches
- Most recent match first
- Score format: team's goals first, then opponent's (e.g., "2-1" if team won 2-1)
- result must match the score (W if scored more, L if scored less, D if equal)
- Dates must be BEFORE {match_date.isoformat()}
"""

        data, raw = self._extract(prompt, use_search=True)

        form_data = None
        if data:
            form_data = {
                "last_5": data.get("last_5", []),
                "current_streak": data.get("current_streak", ""),
                "goals_scored_last_5": data.get("goals_scored_last_5", 0),
                "goals_conceded_last_5": data.get("goals_conceded_last_5", 0)
            }

        return {
            "form": form_data,
            "confidence": data.get("confidence", 0.0) if data else 0.0,
            "source": "gemini" if self._gemini_client else "openai",
            "raw_response": raw
        }

    def extract_table_position(
        self,
        team_name: str,
        league: str = "Premier League",
        match_date: Optional[date] = None
    ) -> Dict:
        """
        Extract current league table position for a team.

        Returns:
            {
                "table_position": {...},
                "confidence": 0.0-1.0,
                "source": "...",
                "raw_response": "..."
            }
        """
        match_date = match_date or date.today()

        prompt = f"""You are a football data extraction agent. Extract ONLY factual league table data.

TEAM: {team_name}
LEAGUE: {league}
DATE: {match_date.isoformat()}

Extract the league table position for {team_name} as of {match_date.isoformat()}.

OUTPUT FORMAT (JSON only, no explanation):
{{
    "position": 1-20,
    "points": total_points,
    "played": matches_played,
    "won": wins,
    "drawn": draws,
    "lost": losses,
    "goals_for": total_scored,
    "goals_against": total_conceded,
    "goal_difference": GF-GA,
    "form_string": "WWDLW",
    "confidence": 0.0-1.0
}}

RULES:
- Position must be 1-20 for Premier League
- Points = won*3 + drawn*1 (verify this matches)
- goal_difference = goals_for - goals_against (verify this matches)
- played = won + drawn + lost (verify this matches)
- form_string = last 5 results, most recent last
"""

        data, raw = self._extract(prompt, use_search=True)

        table_data = None
        if data and "position" in data:
            table_data = {
                "position": data.get("position"),
                "points": data.get("points", 0),
                "played": data.get("played", 0),
                "won": data.get("won", 0),
                "drawn": data.get("drawn", 0),
                "lost": data.get("lost", 0),
                "goals_for": data.get("goals_for", 0),
                "goals_against": data.get("goals_against", 0),
                "goal_difference": data.get("goal_difference", 0),
                "form_string": data.get("form_string", "")
            }

        return {
            "table_position": table_data,
            "confidence": data.get("confidence", 0.0) if data else 0.0,
            "source": "gemini" if self._gemini_client else "openai",
            "raw_response": raw
        }

    def extract_head_to_head(
        self,
        home_team: str,
        away_team: str,
        league: str = "Premier League",
        match_date: Optional[date] = None
    ) -> Dict:
        """
        Extract head-to-head history between two teams.

        Returns:
            {
                "head_to_head": {...},
                "confidence": 0.0-1.0,
                "source": "...",
                "raw_response": "..."
            }
        """
        match_date = match_date or date.today()

        prompt = f"""You are a football data extraction agent. Extract ONLY factual head-to-head data.

HOME TEAM: {home_team}
AWAY TEAM: {away_team}
MATCH DATE: {match_date.isoformat()}

Extract the last 5 meetings between {home_team} and {away_team} BEFORE {match_date.isoformat()}.

OUTPUT FORMAT (JSON only, no explanation):
{{
    "last_5_meetings": [
        {{
            "date": "YYYY-MM-DD",
            "home_team": "team that played at home",
            "away_team": "team that played away",
            "score": "home_goals-away_goals"
        }}
    ],
    "home_team_wins": count_of_{home_team}_wins,
    "draws": count_of_draws,
    "away_team_wins": count_of_{away_team}_wins,
    "total_goals": sum_of_all_goals,
    "most_recent_winner": "team_name or draw",
    "confidence": 0.0-1.0
}}

RULES:
- Only include matches BEFORE {match_date.isoformat()}
- home_team_wins + draws + away_team_wins must equal number of matches
- Score format: home team goals first (e.g., "2-1")
- most_recent_winner = winner of most recent match, or "draw"
"""

        data, raw = self._extract(prompt, use_search=True)

        h2h_data = None
        if data:
            h2h_data = {
                "last_5_meetings": data.get("last_5_meetings", []),
                "home_team_wins": data.get("home_team_wins", 0),
                "draws": data.get("draws", 0),
                "away_team_wins": data.get("away_team_wins", 0),
                "total_goals": data.get("total_goals", 0),
                "most_recent_winner": data.get("most_recent_winner")
            }

        return {
            "head_to_head": h2h_data,
            "confidence": data.get("confidence", 0.0) if data else 0.0,
            "source": "gemini" if self._gemini_client else "openai",
            "raw_response": raw
        }

    def extract_team_news(
        self,
        team_name: str,
        league: str = "Premier League",
        match_date: Optional[date] = None
    ) -> Dict:
        """
        Extract latest news and context about a team.

        Returns:
            {
                "news": {...},
                "confidence": 0.0-1.0,
                "source": "...",
                "raw_response": "..."
            }
        """
        match_date = match_date or date.today()

        prompt = f"""You are a football data extraction agent. Extract ONLY factual news and context.

TEAM: {team_name}
LEAGUE: {league}
DATE: {match_date.isoformat()}

Search for the latest news about {team_name} in the past 7 days.

OUTPUT FORMAT (JSON only, no explanation):
{{
    "manager_news": "Any managerial changes, pressure, or statements (or null)",
    "tactical_changes": "Any reported formation/style changes (or null)",
    "morale_indicator": "high|normal|low|crisis (based on reports)",
    "key_storylines": ["storyline 1", "storyline 2"],
    "sources": ["source1.com", "source2.com"],
    "confidence": 0.0-1.0
}}

RULES:
- Only include FACTUAL news from reliable sources
- Do NOT include speculation or rumors
- morale_indicator should be based on actual reports, not assumption
- key_storylines should be specific, not generic
"""

        data, raw = self._extract(prompt, use_search=True)

        news_data = None
        if data:
            news_data = {
                "manager_news": data.get("manager_news"),
                "tactical_changes": data.get("tactical_changes"),
                "morale_indicator": data.get("morale_indicator"),
                "key_storylines": data.get("key_storylines", []),
                "sources": data.get("sources", [])
            }

        return {
            "news": news_data,
            "confidence": data.get("confidence", 0.0) if data else 0.0,
            "source": "gemini" if self._gemini_client else "openai",
            "raw_response": raw
        }

    # ============================================================
    # COMPOSITE EXTRACTION
    # ============================================================

    def extract_team_enrichment(
        self,
        team_name: str,
        league: str = "Premier League",
        match_date: Optional[date] = None,
        include_form: bool = True,
        include_table: bool = True,
        include_news: bool = False
    ) -> Dict:
        """
        Extract complete enrichment for one team.

        Returns combined data from all extraction types.
        """
        match_date = match_date or date.today()
        result = {
            "team_name": team_name,
            "extraction_timestamp": datetime.now().isoformat(),
            "injuries": [],
            "form": None,
            "table_position": None,
            "news": None,
            "extraction_quality": 0.0,
            "errors": []
        }

        # Extract injuries (always)
        try:
            injuries_result = self.extract_injuries(team_name, league, match_date)
            result["injuries"] = injuries_result.get("injuries", [])
        except Exception as e:
            result["errors"].append(f"Injuries extraction failed: {e}")
            logger.error(f"Injuries extraction failed for {team_name}: {e}")

        # Extract form
        if include_form:
            try:
                form_result = self.extract_form(team_name, league, match_date)
                result["form"] = form_result.get("form")
            except Exception as e:
                result["errors"].append(f"Form extraction failed: {e}")
                logger.error(f"Form extraction failed for {team_name}: {e}")

        # Extract table position
        if include_table:
            try:
                table_result = self.extract_table_position(team_name, league, match_date)
                result["table_position"] = table_result.get("table_position")
            except Exception as e:
                result["errors"].append(f"Table extraction failed: {e}")
                logger.error(f"Table extraction failed for {team_name}: {e}")

        # Extract news
        if include_news:
            try:
                news_result = self.extract_team_news(team_name, league, match_date)
                result["news"] = news_result.get("news")
            except Exception as e:
                result["errors"].append(f"News extraction failed: {e}")
                logger.error(f"News extraction failed for {team_name}: {e}")

        # Calculate overall quality
        quality_factors = []
        if result["injuries"] is not None:
            quality_factors.append(1.0)
        if result["form"] is not None:
            quality_factors.append(1.0)
        if result["table_position"] is not None:
            quality_factors.append(1.0)

        result["extraction_quality"] = sum(quality_factors) / 3 if quality_factors else 0.0

        return result

    def extract_match_enrichment(
        self,
        fixture_id: str,
        home_team: str,
        away_team: str,
        league: str = "Premier League",
        match_date: Optional[date] = None,
        include_form: bool = True,
        include_table: bool = True,
        include_h2h: bool = True,
        include_news: bool = False
    ) -> Dict:
        """
        Extract complete enrichment for a match (both teams + H2H).

        Returns combined data for the entire match context.
        """
        match_date = match_date or date.today()

        result = {
            "fixture_id": fixture_id,
            "extraction_timestamp": datetime.now().isoformat(),
            "home_team": None,
            "away_team": None,
            "head_to_head": None,
            "total_quality": 0.0,
            "errors": []
        }

        # Extract home team
        try:
            result["home_team"] = self.extract_team_enrichment(
                home_team, league, match_date, include_form, include_table, include_news
            )
        except Exception as e:
            result["errors"].append(f"Home team extraction failed: {e}")
            logger.error(f"Home team extraction failed: {e}")

        # Extract away team
        try:
            result["away_team"] = self.extract_team_enrichment(
                away_team, league, match_date, include_form, include_table, include_news
            )
        except Exception as e:
            result["errors"].append(f"Away team extraction failed: {e}")
            logger.error(f"Away team extraction failed: {e}")

        # Extract H2H
        if include_h2h:
            try:
                h2h_result = self.extract_head_to_head(home_team, away_team, league, match_date)
                result["head_to_head"] = h2h_result.get("head_to_head")
            except Exception as e:
                result["errors"].append(f"H2H extraction failed: {e}")
                logger.error(f"H2H extraction failed: {e}")

        # Calculate total quality
        quality = 0.0
        if result["home_team"]:
            quality += result["home_team"].get("extraction_quality", 0) * 0.4
        if result["away_team"]:
            quality += result["away_team"].get("extraction_quality", 0) * 0.4
        if result["head_to_head"]:
            quality += 0.2

        result["total_quality"] = quality

        return result


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def create_agent(provider: str = "claude") -> ExtractionAgent:
    """
    Create an extraction agent with default settings.

    Args:
        provider: "claude" (recommended), "gemini", or "openai"

    Returns:
        ExtractionAgent configured with specified provider
    """
    return ExtractionAgent(provider=provider)
