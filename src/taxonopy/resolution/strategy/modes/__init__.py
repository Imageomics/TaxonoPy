"""Taxonomic resolution strategy implementations.

This package contains concrete strategy implementations for
resolving taxonomic names.
"""

from taxonopy.resolution.strategy.modes.exact_match import ExactMatchStrategy
from taxonopy.resolution.strategy.modes.singular_exact_match import SingularExactMatchStrategy
# Add other strategies as they are implemented
# from taxonopy.resolution.strategy.modes.synonym import SynonymResolutionStrategy

from taxonopy.resolution.strategy.registry import StrategyRegistry

# Register all strategies
StrategyRegistry.register("exact_match", ExactMatchStrategy)
StrategyRegistry.register("singular_exact_match", SingularExactMatchStrategy)
# Register other strategies as they are implemented
# StrategyRegistry.register("synonym", SynonymResolutionStrategy)

__all__ = [
    "ExactMatchStrategy",
    "SingularExactMatchStrategy",
    # Add other strategies as they are implemented
    # "SynonymResolutionStrategy",
]