"""
Clarity Agents Module - Anti-Hallucination Data Extraction

This module provides AI-powered data enrichment with strict validation
to ensure no hallucinated data enters the analysis pipeline.

Key components:
- ExtractionAgent: Extracts structured data from web search
- ExtractionValidator: Validates extracted data against schemas
- EnrichedContextBuilder: Merges agent data with deterministic DB data

Design principle: Agents EXTRACT, they don't INVENT.

Usage:
    # Basic validation (no DB dependencies)
    from src.agents.extraction_schemas import InjuryExtraction
    from src.agents.extraction_validator import validate_extraction

    # Full agent (requires DB and LLM)
    from src.agents.extraction_agent import ExtractionAgent
    from src.agents.enriched_context import EnrichedContextBuilder
"""

# Lightweight imports (no external dependencies)
from .extraction_schemas import (
    InjuryExtraction,
    FormExtraction,
    TablePositionExtraction,
    HeadToHeadExtraction,
    TeamEnrichment,
    MatchEnrichment,
    EXTRACTION_SCHEMAS
)
from .extraction_validator import (
    ExtractionValidator,
    ValidationResult,
    validate_extraction
)

# Lazy imports for heavy modules
def get_extraction_agent():
    """Get ExtractionAgent class (lazy import)."""
    from .extraction_agent import ExtractionAgent
    return ExtractionAgent

def get_enriched_context_builder():
    """Get EnrichedContextBuilder class (lazy import)."""
    from .enriched_context import EnrichedContextBuilder
    return EnrichedContextBuilder

__all__ = [
    # Schemas
    'InjuryExtraction',
    'FormExtraction',
    'TablePositionExtraction',
    'HeadToHeadExtraction',
    'TeamEnrichment',
    'MatchEnrichment',
    'EXTRACTION_SCHEMAS',
    # Validator
    'ExtractionValidator',
    'ValidationResult',
    'validate_extraction',
    # Lazy loaders
    'get_extraction_agent',
    'get_enriched_context_builder',
]
