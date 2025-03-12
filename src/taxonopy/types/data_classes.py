"""Core data classes for TaxonoPy.

This module defines the immutable data classes that form the core of the
TaxonoPy resolution workflow. Each class represents a specific stage in the
taxonomic resolution process.

Design Principles:
- Immutability: All classes are frozen to prevent modification after creation
- Clear Data Flow: Classes represent transformations of data through the workflow
- Separation of Concerns: Each class has a single, well-defined purpose
- Reference-based Relationships: Objects refer to each other by ID rather than embedding
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Union
from uuid import UUID

from taxonopy.types.gnverifier import Name as GNVerifierName


class ResolutionStatus(Enum):
    """The possible resolution statuses of a taxonomic entry."""
    
    # Initial status
    UNPROCESSED = auto()
    
    # Processing statuses
    QUEUED = auto()
    PROCESSING = auto()
    
    # Success statuses
    EXACT_MATCH = auto()
    FUZZY_MATCH = auto()
    PARTIAL_MATCH = auto()
    
    # Failure statuses
    NO_MATCH = auto()
    AMBIGUOUS_MATCH = auto()
    INVALID_INPUT = auto()
    FAILED = auto()
    
    # Final status
    FORCE_ACCEPTED = auto()


@dataclass(frozen=True)
class TaxonomicEntry:
    """A single taxonomic entry from the input data.
    
    This is the starting point of the resolution workflow, representing the
    raw input data before any processing or resolution.
    """
    
    # Core identification fields
    uuid: str
    scientific_name: Optional[str] = None
    common_name: Optional[str] = None
    
    # The seven standard Linnaean ranks
    kingdom: Optional[str] = None
    phylum: Optional[str] = None
    class_: Optional[str] = None  # Using class_ to avoid conflict with Python keyword
    order: Optional[str] = None
    family: Optional[str] = None
    genus: Optional[str] = None
    species: Optional[str] = None
    
    # Additional metadata
    source_dataset: Optional[str] = None
    source_id: Optional[str] = None
    
    @property
    def has_taxonomic_data(self) -> bool:
        """Check if the entry has any non-empty taxonomic data."""
        for rank in ['kingdom', 'phylum', 'class_', 'order', 'family', 'genus', 'species']:
            value = getattr(self, rank)
            if value and value.lower() not in ['unknown', 'null', 'none', '']:
                return True
        return False
    
    @property
    def most_specific_rank(self) -> Optional[str]:
        """Return the most specific taxonomic rank that is not empty."""
        for rank in ['species', 'genus', 'family', 'order', 'class_', 'phylum', 'kingdom']:
            value = getattr(self, rank)
            if value and value.lower() not in ['unknown', 'null', 'none', '']:
                return rank
        return None
    
    @property
    def most_specific_term(self) -> Optional[str]:
        """Return the value of the most specific taxonomic rank that is not empty."""
        rank = self.most_specific_rank
        if rank:
            return getattr(self, rank)
        return None
    
    def to_dict(self) -> Dict[str, Optional[str]]:
        """Convert the entry to a dictionary."""
        result = {
            'uuid': self.uuid,
            'scientific_name': self.scientific_name,
            'common_name': self.common_name,
            'kingdom': self.kingdom,
            'phylum': self.phylum,
            'class': self.class_,  # Convert class_ back to class
            'order': self.order,
            'family': self.family,
            'genus': self.genus, 
            'species': self.species,
            'source_dataset': self.source_dataset,
            'source_id': self.source_id,
        }
        return result


@dataclass(frozen=True)
class EntryGroupRef:
    """A reference to a group of taxonomic entries with identical taxonomy.
    
    This represents the first transformation of the data - the grouping stage.
    Entries with identical taxonomic data are grouped to minimize API calls.
    The group stores the actual taxonomic data fields directly to eliminate
    the need for separate lookups.
    """
    
    # Unique key for this group, typically based on the taxonomic data
    key: str
    
    # The UUIDs of all entries in this group
    entry_uuids: Set[str] = field(default_factory=frozenset)
    
    # The actual taxonomic data that defines this group
    kingdom: Optional[str] = None
    phylum: Optional[str] = None
    class_: Optional[str] = None  # Using class_ to avoid conflict with Python keyword
    order: Optional[str] = None
    family: Optional[str] = None
    genus: Optional[str] = None
    species: Optional[str] = None
    scientific_name: Optional[str] = None
    
    @property
    def group_count(self) -> int:
        """Return the number of entries in this group."""
        return len(self.entry_uuids)
    
    @property
    def most_specific_rank(self) -> Optional[str]:
        """Return the most specific taxonomic rank that is not empty."""
        for rank in ['species', 'genus', 'family', 'order', 'class_', 'phylum', 'kingdom']:
            value = getattr(self, rank)
            if value and value.strip().lower() not in ['unknown', 'null', 'none', '', 'n/a']:
                return rank
        return None
    
    @property
    def most_specific_term(self) -> Optional[str]:
        """Return the value of the most specific taxonomic rank that is not empty."""
        rank = self.most_specific_rank
        if rank:
            return getattr(self, rank)
        return None

@dataclass(frozen=True)
class QueryGroupRef:
    """A reference to a group of entry groups with the same query term.
    
    This represents the second transformation - the query planning stage.
    Entry groups that will use the same query term are grouped to optimize 
    API calls.
    """
    
    # The term that will be used for the query
    query_term: str
    
    # The taxonomic rank of the query term
    query_rank: str
    
    # The keys of all entry groups in this query group
    entry_group_keys: Set[str] = field(default_factory=frozenset)
    
    # The key of a representative entry group
    representative_group_key: str = field(default="")
    
    @property
    def group_count(self) -> int:
        """Return the number of entry groups in this query group."""
        return len(self.entry_group_keys)


@dataclass(frozen=True)
class ResolutionAttempt:
    """Records the result of a GNVerifier query and its interpretation.
    
    This represents the final transformation - the resolution outcome.
    It contains both the query information and the result, as well as
    metadata about the resolution attempt.
    """
    # Unique identifier for this attempt
    attempt_id: str

    # The query group this attempt is for
    query_group_key: str
    
    # The term that was used in the query
    query_term: str
    
    # The taxonomic rank of the query term
    query_rank: str
    
    # The status of the resolution
    status: ResolutionStatus
    
    # The raw response from GNVerifier, if applicable
    gnverifier_response: Optional[GNVerifierName] = None
    
    # The resolved classification, if successful
    resolved_classification: Optional[Dict[str, str]] = None
    
    # Additional metadata about the resolution
    metadata: Dict[str, Union[str, int, float, bool]] = field(default_factory=dict)
    
    # Reference to the previous attempt in the chain, if any
    previous_attempt_id: Optional[str] = None
    
    @property
    def is_retry(self) -> bool:
        """Check if this attempt is a retry (has a previous attempt)."""
        return self.previous_attempt_id is not None
