"""Taxonomic resolution strategies.

This package contains concrete strategy implementations for
resolving taxonomic names.
"""

from taxonopy.resolution.strategies.exact_match import ExactMatchStrategy
# from taxonopy.resolution.strategies.fuzzy_match import FuzzyMatchStrategy
# from taxonopy.resolution.strategies.synonym import SynonymResolutionStrategy

from taxonopy.resolution.strategy_registry import StrategyRegistry

# Register all strategies
StrategyRegistry.register("exact_match", ExactMatchStrategy)
# Register other strategies as they are implemented
# StrategyRegistry.register("fuzzy_match", FuzzyMatchStrategy)
# StrategyRegistry.register("synonym", SynonymResolutionStrategy)

__all__ = [
    "ExactMatchStrategy",
    # Add other strategies as they are implemented
    # "FuzzyMatchStrategy",
    # "SynonymResolutionStrategy",
]
