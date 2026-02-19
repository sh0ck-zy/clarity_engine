"""
Extraction Schemas - Rigid JSON Schemas for Agent Outputs

These schemas enforce structural constraints on agent extractions.
If the agent returns data that doesn't match the schema, it's REJECTED.

The schemas are intentionally strict to prevent hallucination.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Literal
from datetime import date, datetime
from enum import Enum
import json


# ============================================================
# ENUMS AND CONSTANTS
# ============================================================

class Position(str, Enum):
    GK = "GK"
    DEF = "DEF"
    MID = "MID"
    FWD = "FWD"


class MatchResult(str, Enum):
    WIN = "W"
    DRAW = "D"
    LOSS = "L"


class Venue(str, Enum):
    HOME = "H"
    AWAY = "A"


# ============================================================
# EXTRACTION DATACLASSES
# ============================================================

@dataclass
class InjuryExtraction:
    """Single injury/absence extraction."""
    player_name: str
    position: str  # GK, DEF, MID, FWD
    injury_type: str  # "hamstring", "knee", "illness", etc.
    expected_return: Optional[str] = None  # "2 weeks", "unknown", date string
    is_key_player: bool = False
    source_quote: Optional[str] = None  # Direct quote from source


@dataclass
class FormMatchExtraction:
    """Single match in form extraction."""
    opponent: str
    result: str  # W, D, L
    score: str  # "2-1", "0-0"
    venue: str  # H, A
    date: Optional[str] = None  # YYYY-MM-DD if available


@dataclass
class FormExtraction:
    """Last 5 matches form extraction."""
    last_5: List[FormMatchExtraction]  # Must have exactly 5
    current_streak: str  # "3W", "2D", "1L", etc.
    goals_scored_last_5: int
    goals_conceded_last_5: int


@dataclass
class TablePositionExtraction:
    """League table position extraction."""
    position: int  # 1-20
    points: int
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    form_string: str  # "WWDLW" last 5 in table


@dataclass
class H2HMatchExtraction:
    """Single H2H match extraction."""
    date: str  # YYYY-MM-DD
    home_team: str
    away_team: str
    score: str  # "2-1"
    venue: str  # Which team was home for the current home team


@dataclass
class HeadToHeadExtraction:
    """Head-to-head history extraction."""
    last_5_meetings: List[H2HMatchExtraction]  # Up to 5
    home_team_wins: int  # Wins by current home team (in any venue)
    draws: int
    away_team_wins: int
    total_goals: int  # Across all H2H matches
    most_recent_winner: Optional[str] = None  # Team name or "draw"


@dataclass
class TeamNewsExtraction:
    """Latest news/context about a team."""
    manager_news: Optional[str] = None  # Managerial changes, pressure, etc.
    tactical_changes: Optional[str] = None  # Formation/style changes
    morale_indicator: Optional[str] = None  # "high", "low", "crisis"
    key_storylines: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)


@dataclass
class TeamEnrichment:
    """Complete enrichment for one team."""
    team_name: str
    injuries: List[InjuryExtraction]
    form: Optional[FormExtraction] = None
    table_position: Optional[TablePositionExtraction] = None
    news: Optional[TeamNewsExtraction] = None
    extraction_timestamp: str = ""
    extraction_quality: float = 0.0  # 0-1 confidence


@dataclass
class MatchEnrichment:
    """Complete enrichment for a match."""
    fixture_id: str
    home_team: TeamEnrichment
    away_team: TeamEnrichment
    head_to_head: Optional[HeadToHeadExtraction] = None
    match_context: Optional[str] = None  # Derby, relegation battle, etc.
    extraction_timestamp: str = ""
    total_quality: float = 0.0


# ============================================================
# JSON SCHEMAS FOR VALIDATION
# ============================================================

EXTRACTION_SCHEMAS = {
    "injury": {
        "type": "object",
        "required": ["player_name", "position", "injury_type"],
        "properties": {
            "player_name": {"type": "string", "minLength": 2, "maxLength": 100},
            "position": {"type": "string", "enum": ["GK", "DEF", "MID", "FWD"]},
            "injury_type": {"type": "string", "minLength": 2, "maxLength": 100},
            "expected_return": {"type": ["string", "null"], "maxLength": 100},
            "is_key_player": {"type": "boolean"},
            "source_quote": {"type": ["string", "null"], "maxLength": 500}
        }
    },

    "form_match": {
        "type": "object",
        "required": ["opponent", "result", "score", "venue"],
        "properties": {
            "opponent": {"type": "string", "minLength": 2, "maxLength": 100},
            "result": {"type": "string", "enum": ["W", "D", "L"]},
            "score": {"type": "string", "pattern": "^\\d+-\\d+$"},
            "venue": {"type": "string", "enum": ["H", "A"]},
            "date": {"type": ["string", "null"], "pattern": "^\\d{4}-\\d{2}-\\d{2}$"}
        }
    },

    "form": {
        "type": "object",
        "required": ["last_5", "goals_scored_last_5", "goals_conceded_last_5"],
        "properties": {
            "last_5": {
                "type": "array",
                "items": {"$ref": "#/definitions/form_match"},
                "minItems": 5,
                "maxItems": 5
            },
            "current_streak": {"type": "string", "pattern": "^\\d+[WDL]$"},
            "goals_scored_last_5": {"type": "integer", "minimum": 0, "maximum": 50},
            "goals_conceded_last_5": {"type": "integer", "minimum": 0, "maximum": 50}
        }
    },

    "table_position": {
        "type": "object",
        "required": ["position", "points", "played"],
        "properties": {
            "position": {"type": "integer", "minimum": 1, "maximum": 24},
            "points": {"type": "integer", "minimum": 0, "maximum": 114},
            "played": {"type": "integer", "minimum": 0, "maximum": 38},
            "won": {"type": "integer", "minimum": 0, "maximum": 38},
            "drawn": {"type": "integer", "minimum": 0, "maximum": 38},
            "lost": {"type": "integer", "minimum": 0, "maximum": 38},
            "goals_for": {"type": "integer", "minimum": 0, "maximum": 200},
            "goals_against": {"type": "integer", "minimum": 0, "maximum": 200},
            "goal_difference": {"type": "integer", "minimum": -200, "maximum": 200},
            "form_string": {"type": "string", "pattern": "^[WDL]{0,5}$"}
        }
    },

    "h2h_match": {
        "type": "object",
        "required": ["date", "home_team", "away_team", "score"],
        "properties": {
            "date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
            "home_team": {"type": "string", "minLength": 2},
            "away_team": {"type": "string", "minLength": 2},
            "score": {"type": "string", "pattern": "^\\d+-\\d+$"},
            "venue": {"type": "string"}
        }
    },

    "head_to_head": {
        "type": "object",
        "required": ["home_team_wins", "draws", "away_team_wins"],
        "properties": {
            "last_5_meetings": {
                "type": "array",
                "items": {"$ref": "#/definitions/h2h_match"},
                "maxItems": 5
            },
            "home_team_wins": {"type": "integer", "minimum": 0, "maximum": 5},
            "draws": {"type": "integer", "minimum": 0, "maximum": 5},
            "away_team_wins": {"type": "integer", "minimum": 0, "maximum": 5},
            "total_goals": {"type": "integer", "minimum": 0, "maximum": 50},
            "most_recent_winner": {"type": ["string", "null"]}
        }
    },

    "team_enrichment": {
        "type": "object",
        "required": ["team_name", "injuries"],
        "properties": {
            "team_name": {"type": "string", "minLength": 2},
            "injuries": {
                "type": "array",
                "items": {"$ref": "#/definitions/injury"}
            },
            "form": {"$ref": "#/definitions/form"},
            "table_position": {"$ref": "#/definitions/table_position"},
            "extraction_quality": {"type": "number", "minimum": 0, "maximum": 1}
        }
    }
}


# ============================================================
# PROMPT TEMPLATES FOR EXTRACTION
# ============================================================

INJURY_EXTRACTION_PROMPT = """You are a football data extraction agent. Extract ONLY factual injury information.

TEAM: {team_name}
LEAGUE: {league}
DATE: {match_date}

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

FORM_EXTRACTION_PROMPT = """You are a football data extraction agent. Extract ONLY factual match results.

TEAM: {team_name}
LEAGUE: {league}
DATE: {match_date}

Extract the last 5 completed matches for {team_name} BEFORE {match_date}.

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
    "goals_conceded_last_5": total
}}

RULES:
- Must have EXACTLY 5 matches
- Most recent match first
- Score format: team's goals first, then opponent's (e.g., "2-1" if team won 2-1)
- result must match the score (W if scored more, L if scored less, D if equal)
- Dates must be BEFORE {match_date}
"""

TABLE_EXTRACTION_PROMPT = """You are a football data extraction agent. Extract ONLY factual league table data.

TEAM: {team_name}
LEAGUE: {league}
DATE: {match_date}

Extract the league table position for {team_name} as of {match_date}.

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
    "form_string": "WWDLW"
}}

RULES:
- Position must be 1-20 for Premier League
- Points = won*3 + drawn*1 (verify this matches)
- goal_difference = goals_for - goals_against (verify this matches)
- played = won + drawn + lost (verify this matches)
- form_string = last 5 results, most recent last
"""

H2H_EXTRACTION_PROMPT = """You are a football data extraction agent. Extract ONLY factual head-to-head data.

HOME TEAM: {home_team}
AWAY TEAM: {away_team}
MATCH DATE: {match_date}

Extract the last 5 meetings between {home_team} and {away_team} BEFORE {match_date}.

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
    "most_recent_winner": "team_name or draw"
}}

RULES:
- Only include matches BEFORE {match_date}
- home_team_wins + draws + away_team_wins must equal number of matches
- Score format: home team goals first (e.g., "2-1")
- most_recent_winner = winner of most recent match, or "draw"
"""


# ============================================================
# SERIALIZATION HELPERS
# ============================================================

def extraction_to_dict(obj) -> Dict:
    """Convert any extraction dataclass to dict."""
    if hasattr(obj, '__dataclass_fields__'):
        return asdict(obj)
    return obj


def extraction_to_json(obj, indent: int = 2) -> str:
    """Convert extraction to JSON string."""
    def serializer(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if isinstance(o, Enum):
            return o.value
        if hasattr(o, '__dataclass_fields__'):
            return asdict(o)
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.dumps(extraction_to_dict(obj), default=serializer, indent=indent)


def dict_to_injury_extraction(d: Dict) -> InjuryExtraction:
    """Parse dict to InjuryExtraction."""
    return InjuryExtraction(
        player_name=d['player_name'],
        position=d['position'],
        injury_type=d['injury_type'],
        expected_return=d.get('expected_return'),
        is_key_player=d.get('is_key_player', False),
        source_quote=d.get('source_quote')
    )


def dict_to_form_extraction(d: Dict) -> FormExtraction:
    """Parse dict to FormExtraction."""
    last_5 = [
        FormMatchExtraction(
            opponent=m['opponent'],
            result=m['result'],
            score=m['score'],
            venue=m['venue'],
            date=m.get('date')
        )
        for m in d.get('last_5', [])
    ]
    return FormExtraction(
        last_5=last_5,
        current_streak=d.get('current_streak', ''),
        goals_scored_last_5=d.get('goals_scored_last_5', 0),
        goals_conceded_last_5=d.get('goals_conceded_last_5', 0)
    )


def dict_to_table_extraction(d: Dict) -> TablePositionExtraction:
    """Parse dict to TablePositionExtraction."""
    return TablePositionExtraction(
        position=d['position'],
        points=d['points'],
        played=d['played'],
        won=d.get('won', 0),
        drawn=d.get('drawn', 0),
        lost=d.get('lost', 0),
        goals_for=d.get('goals_for', 0),
        goals_against=d.get('goals_against', 0),
        goal_difference=d.get('goal_difference', 0),
        form_string=d.get('form_string', '')
    )


def dict_to_h2h_extraction(d: Dict) -> HeadToHeadExtraction:
    """Parse dict to HeadToHeadExtraction."""
    last_5 = [
        H2HMatchExtraction(
            date=m['date'],
            home_team=m['home_team'],
            away_team=m['away_team'],
            score=m['score'],
            venue=m.get('venue', '')
        )
        for m in d.get('last_5_meetings', [])
    ]
    return HeadToHeadExtraction(
        last_5_meetings=last_5,
        home_team_wins=d.get('home_team_wins', 0),
        draws=d.get('draws', 0),
        away_team_wins=d.get('away_team_wins', 0),
        total_goals=d.get('total_goals', 0),
        most_recent_winner=d.get('most_recent_winner')
    )
