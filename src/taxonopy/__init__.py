"""TaxonoPy: A Python package for resolving taxonomic hierarchies.

TaxonoPy uses the Global Names Verifier (GNVerifier) API to create an internally
consistent taxonomic hierarchy from a variety of inputs, primarily designed for
the TreeOfLife (TOL) dataset.
"""

__version__ = "0.1.0"

from taxonopy.types.data_classes import (
    ResolutionStatus,
    TaxonomicEntry,
    EntryGroupRef,
    QueryGroupRef,
    ResolutionAttempt,
)

__all__ = [
    "ResolutionStatus",
    "TaxonomicEntry",
    "EntryGroupRef",
    "QueryGroupRef",
    "ResolutionAttempt",
    "ResolutionAttemptManager",
]
