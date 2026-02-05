"""TaxonoPy: A Python package for resolving taxonomic hierarchies.

TaxonoPy uses the Global Names Verifier (GNVerifier) API to create an internally
consistent taxonomic hierarchy from a variety of inputs, primarily designed for
the TreeOfLife (TOL) dataset.
"""

__version__ = "0.1.1b0"

from taxonopy.types.data_classes import (
    ResolutionStatus,
    TaxonomicEntry,
    EntryGroupRef,
    QueryParameters,
    ResolutionAttempt,
)

from taxonopy.resolution import (
    ResolutionAttemptManager,
    ResolutionStrategyConfig,
    ResolutionStrategyManager,
    ResolutionStrategy,
)

__all__ = [
    # Data classes
    "ResolutionStatus",
    "TaxonomicEntry",
    "EntryGroupRef",
    "QueryParameters",
    "ResolutionAttempt",
    
    # Resolution components
    "ResolutionAttemptManager",
    "ResolutionStrategyConfig",
    "ResolutionStrategyManager",
    "ResolutionStrategy",
]