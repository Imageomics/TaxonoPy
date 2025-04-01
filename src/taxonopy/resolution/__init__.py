"""Taxonomic resolution system.

This package provides a flexible framework for implementing and applying
taxonomic resolution strategies.
"""

from taxonopy.resolution.attempt_manager import ResolutionAttemptManager
from taxonopy.resolution.config import ResolutionStrategyConfig
from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.resolution.strategy.registry import StrategyRegistry
from taxonopy.resolution.strategy.manager import ResolutionStrategyManager

# Import strategy modes
from taxonopy.resolution.strategy.modes.exact_match import ExactMatchStrategy
from taxonopy.resolution.strategy.modes.singular_exact_match import SingularExactMatchStrategy

__all__ = [
    # Core components
    "ResolutionAttemptManager",
    "ResolutionStrategyConfig",
    "ResolutionStrategy",
    "StrategyRegistry",
    "ResolutionStrategyManager",
    
    # Strategies
    "ExactMatchStrategy",
    "SingularExactMatchStrategy",
]