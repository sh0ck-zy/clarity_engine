"""
Clarity Engine Agents.

Two approaches for match analysis:
- CodedAgent: Fixed sequence of tool calls → single LLM call
- OpenClawAgent: LLM-driven investigation with tool access
"""

from .base import AnalysisReport, MatchReality
from .coded import CodedAgent
from .openclaw import OpenClawAgent

__all__ = ["AnalysisReport", "MatchReality", "CodedAgent", "OpenClawAgent"]
