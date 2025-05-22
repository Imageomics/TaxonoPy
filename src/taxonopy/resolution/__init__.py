"""Taxonomic resolution system.

This package provides a flexible framework for implementing and applying
taxonomic resolution strategies.
"""

from taxonopy.resolution.attempt_manager import ResolutionAttemptManager
from taxonopy.resolution.config import ResolutionStrategyConfig
from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.resolution.strategy.manager import ResolutionStrategyManager

# Import strategy profiles
from taxonopy.resolution.strategy.profiles.exact_match_primary_source_accepted import ExactMatchPrimarySourceAcceptedStrategy

__all__ = [
    # Core components
    "ResolutionAttemptManager",
    "ResolutionStrategyConfig",
    "ResolutionStrategy",
    "ResolutionStrategyManager",
    
    # Strategies
    "ExactMatchStrategy",
    "ExactMatchPrimarySourceAcceptedStrategy",
]
