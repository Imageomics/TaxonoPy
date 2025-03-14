"""Taxonomic resolution system.

This package provides a flexible framework for implementing and applying
taxonomic resolution strategies.
"""

from taxonopy.resolution.attempt_manager import ResolutionAttemptManager
from taxonopy.resolution.config import ResolutionStrategyConfig
from taxonopy.resolution.strategy_base import ResolutionStrategy
from taxonopy.resolution.strategy_registry import StrategyRegistry
from taxonopy.resolution.strategy_manager import ResolutionStrategyManager

# Import strategies
# from taxonopy.resolution.strategies import (
#     ExactMatchStrategy,
#     # Add other strategies as they are implemented
# )

__all__ = [
    # Core components
    "ResolutionAttemptManager",
    "ResolutionStrategyConfig",
    "ResolutionStrategy",
    "StrategyRegistry",
    "ResolutionStrategyManager",
    
    # Strategies
    "ExactMatchStrategy",
]