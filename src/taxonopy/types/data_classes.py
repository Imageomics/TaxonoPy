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
from typing import Dict, List, Optional, Set, Union, Tuple, Callable, FrozenSet
from uuid import UUID
import hashlib
import json

from taxonopy.types.gnverifier import Name as GNVerifierName
from taxonopy.constants import (
    TAXONOMIC_QUERY_PRECEDENCE,
    TAXONOMIC_RANKS,
    INVALID_VALUES
)


class ResolutionStatus(Enum):
    """The possible resolution statuses of a taxonomic entry."""
    def __init__(self, groups: Tuple[str, ...]):
        self.groups: Set[str] = set(groups)
    
    # Terminal success status group
    SINGULAR_EXACT_MATCH = (("terminal", "success"),)
    FORCE_ACCEPTED = (("terminal", "success"),)

    # Terminal failure status group
    EMPTY_INPUT_TAXONOMY = (("terminal", "failure"),)

    # Retry status group
    NO_MATCH_NONEMPTY_QUERY = (("non-terminal", "retry",),)

    # Non-terminal status group
    PROCESSING = (("non-terminal", "processing"),)
    MULTIPLE_EXACT_MATCHES = (("non-terminal", "processing"),)
    
    # Temporary deprecated status group for forcing
    # TODO: Remove this once the deprecated status is no longer needed
    EXACT_MATCH = (("terminal", "deprecated"),)
    FUZZY_MATCH = (("terminal", "deprecated"),)
    PARTIAL_MATCH = (("terminal", "deprecated"),)

    @property
    def is_terminal(self) -> bool:
        """Return whether the status is terminal (success or failure)."""
        return "terminal" in self.groups

    @property
    def is_successful(self) -> bool:
        """Return whether the status indicates a successful resolution."""
        return "success" in self.groups
    
    @property
    def needs_retry(self) -> bool:
        """Return whether the status indicates a need for retry."""
        return "retry" in self.groups


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
        for rank in TAXONOMIC_RANKS:
            value = getattr(self, rank)
            if value and value.lower() not in INVALID_VALUES:
                return True
        return False
    
    @property
    def most_specific_rank(self) -> Optional[str]:
        """Return the most specific taxonomic rank that has valid data."""
        for field, rank in TAXONOMIC_QUERY_PRECEDENCE:
            value = getattr(self, field)
            if value and value.strip().lower() not in INVALID_VALUES:
                return rank
        return None
    
    @property
    def most_specific_term(self) -> Optional[str]:
        """Return the term corresponding to the most specific rank."""
        for field, rank in TAXONOMIC_QUERY_PRECEDENCE:
            value = getattr(self, field)
            if value and value.strip().lower() not in INVALID_VALUES:
                return value.strip()
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
            'has_taxonomic_data': self.has_taxonomic_data,
            'most_specific_rank': self.most_specific_rank,
            'most_specific_term': self.most_specific_term,
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

    # Set of common names across all entries in this group
    common_names: Optional[Set[str]] = field(default_factory=frozenset)
    
    @property
    def group_count(self) -> int:
        """Return the number of entries in this group."""
        return len(self.entry_uuids)
    
    @property
    def most_specific_rank(self) -> Optional[str]:
        """Return the most specific taxonomic rank that has valid data."""
        for field, rank in TAXONOMIC_QUERY_PRECEDENCE:
            value = getattr(self, field)
            if value and value.strip().lower() not in INVALID_VALUES:
                return rank
        return None

    @property
    def most_specific_term(self) -> Optional[str]:
        """
        Return the term (value) corresponding to the most specific rank available,
        based on the precedence order.
        """
        for field_name, rank in TAXONOMIC_QUERY_PRECEDENCE:
            value = getattr(self, field_name, None)
            if value and value.strip().lower() not in INVALID_VALUES:
                return value.strip()
        return None

    @property
    def key(self) -> str:
        """Unique, deterministic key based on hash of entry IDs + shared taxonomic data."""
        entry_id_str = "|".join(sorted(self.entry_uuids))
        terms = []
        for field, _ in TAXONOMIC_QUERY_PRECEDENCE:
            term = getattr(self, field, "") or ""
            terms.append(term.strip().lower())
        taxa_data = "|".join(terms)
        full_str = f"{entry_id_str}|{taxa_data}"

        return hashlib.sha256(full_str.encode("utf-8")).hexdigest()


    def resolve_taxonomic_entries(self, resolver: Callable[[str], Optional[TaxonomicEntry]]) -> List[TaxonomicEntry]:
        """
        Retrieve full TaxonomicEntry objects corresponding to the stored entry UUIDs.
        
        Args:
            resolver: A function mapping an entry UUID (str) to a TaxonomicEntry.
        
        Returns:
            A list of TaxonomicEntry objects sorted by their UUIDs. 

        Usage example:
            resolved_entries = entry_group.resolve_taxonomic_entries(entry_index.get)
        """
        # Sort UUIDs for consistent ordering
        return [resolver(uuid) for uuid in sorted(self.entry_uuids) if resolver(uuid) is not None]

@dataclass(frozen=True)
class QueryGroupRef:
    """A reference to a group of entry groups with the same query term.
    
    This represents the second transformation - the query planning stage.
    Entry groups that will use the same query term are grouped to optimize 
    API calls.
    """
    
    # The taxonomic rank of the query term
    query_rank: str

    # The term that will be used for the query
    query_term: str
    
    # The GNVerifier data source ID for this query group
    data_source_id: int
    
    # The keys of all entry groups in this query group
    entry_group_keys: FrozenSet[str] = field(default_factory=frozenset)
    
    @property
    def group_count(self) -> int:
        """Return the number of entry groups in this query group."""
        return len(self.entry_group_keys)

    @property
    def key(self) -> str:
        """Generate a deterministic key for this query group.
        
        The key is based on the combination of entry_group_keys, query_rank, 
        query_term, 
        and data_source_id.
        """
        # Create a string combining all relevant attributes
        key_parts = [
            "|".join(sorted(self.entry_group_keys)),
            self.query_rank or "",
            self.query_term or "",
            str(self.data_source_id)
        ]
        
        key_str = "|".join(key_parts)
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    def resolve_entry_groups(self, resolver: Callable[[str], Optional[EntryGroupRef]]) -> List[EntryGroupRef]:
        """
        Retrieve the full EntryGroupRef objects corresponding to the stored keys.

        Args:
            resolver: A function that takes an entry group key (str) and returns
                      the corresponding EntryGroupRef (or None if not found).

        Returns:
            A list of EntryGroupRef objects corresponding to this query group,
            sorted by their keys.

        Usage example:
            resolved_groups = query_group.resolve_entry_groups(entry_group_index.get)
        """
        # Sort the keys for consistent ordering
        return [resolver(key) for key in sorted(self.entry_group_keys) if resolver(key) is not None]


@dataclass(frozen=True)
class ResolutionAttempt:
    """Records the result of a GNVerifier query and its interpretation.
    
    This represents the final transformation - the resolution outcome.
    It contains both the query information and the result, as well as
    metadata about the resolution attempt.
    """

    # The query group this attempt is for
    query_group_key: str
    
    # The taxonomic rank of the query term
    query_rank: str

    # The term that was used in the query
    query_term: str
    
    # The status of the resolution
    status: ResolutionStatus
    
    # The raw response from GNVerifier, if applicable
    gnverifier_response: Optional[GNVerifierName] = None
    
    # The resolved classification, if successful
    resolved_classification: Optional[Dict[str, str]] = None
    
    # Additional metadata about the resolution
    metadata: Dict[str, Union[str, int, float, bool]] = field(default_factory=dict)
    
    # Reference to the previous attempt in the chain, if any
    previous_key: Optional[str] = None

    @property
    def is_retry(self) -> bool:
        """Check if this attempt is a retry (has a previous attempt)."""
        return self.previous_key is not None
    
    @property
    def is_successful(self) -> bool:
        """Return whether the attempt was successful."""
        return self.status.is_successful
    
    @property
    def needs_retry(self) -> bool:
        """Return whether the attempt needs to be retried."""
        return self.status.needs_retry

    @property
    def key(self) -> str:
        """
        Compute a unique key for this resolution attempt based on its
        QueryGroupRef linkage and GNVerifier response.
        """
        # Convert the GNVerifier response to a JSON string for deterministic hashing.
        # If there's no response, use an empty string.
        response_str = (
            json.dumps(self.gnverifier_response, sort_keys=True)
            if self.gnverifier_response is not None else ""
        )
        # Combine with the query group key, query term, and query rank.
        combined = f"{self.query_group_key}|{self.query_term}|{self.query_rank}|{response_str}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()
