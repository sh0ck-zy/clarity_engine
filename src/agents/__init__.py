"""
Clarity Engine Agents.

Two approaches for match analysis:
- CodedAgent: Fixed sequence of tool calls → single LLM call
- OpenClawAgent: LLM-driven investigation with tool access
"""

from .base import AnalysisReport
from .coded import CodedAgent

__all__ = ["AnalysisReport", "CodedAgent"]
