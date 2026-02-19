"""
Clarity Engine - Builders
"""

from .robust_builder import RobustBuilder
from .form_interpreter import interpret_form

# Alias para compatibilidade
ContextBuilder = RobustBuilder
MatchContextBuilder = RobustBuilder

__all__ = ["RobustBuilder", "ContextBuilder", "MatchContextBuilder", "interpret_form"]
