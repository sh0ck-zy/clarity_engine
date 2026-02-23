"""
Clarity Engine Agents.

Three approaches for match analysis:
- CodedAgent: Fixed sequence of tool calls → single LLM call
- OpenClawAgent: LLM-driven investigation with tool access
- SkilledAgent: LLM-driven with SKILL.md guidance (v2)
"""

from .base import AnalysisReport, MatchReality
from .coded import CodedAgent
from .openclaw import OpenClawAgent
from .skilled import SkilledAgent

__all__ = ["AnalysisReport", "MatchReality", "CodedAgent", "OpenClawAgent", "SkilledAgent"]
