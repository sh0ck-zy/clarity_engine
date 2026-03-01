"""
Base classes and schemas for agents.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class AnalysisReport:
    """Output from any agent analysis."""
    
    # Match identification
    fixture_id: str
    home_team: str
    away_team: str
    round_number: int
    
    # The analysis
    report_markdown: str
    
    # Extracted predictions (parsed from report)
    home_win_prob: Optional[float] = None
    draw_prob: Optional[float] = None
    away_win_prob: Optional[float] = None
    predicted_result: Optional[str] = None  # "H", "D", "A"
    predicted_scoreline: Optional[str] = None
    over25_prob: Optional[float] = None
    btts_prob: Optional[float] = None
    recommended_bet: Optional[str] = None
    
    # Metadata
    method: str = "coded"  # "coded" or "openclaw"
    tools_used: List[str] = field(default_factory=list)
    tokens_used: int = 0
    time_seconds: float = 0.0
    model: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Raw data for debugging
    raw_context: Optional[dict] = None
    raw_llm_response: Optional[str] = None


@dataclass
class MatchReality:
    """Actual match result for comparison."""
    
    fixture_id: str
    home_team: str
    away_team: str
    
    # Result
    home_score: int
    away_score: int
    result: str  # "H", "D", "A"
    
    # Stats
    home_xg: Optional[float] = None
    away_xg: Optional[float] = None
    
    # Match events summary
    summary: Optional[str] = None
