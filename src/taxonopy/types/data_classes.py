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
    """The possible resolution statuses of a taxonomic entry defining the resolution profile."""
    def __init__(self, status_name: str, groups: Tuple[str, ...]):
        self._value_ = (status_name, groups)
        self.groups: Set[str] = set(groups)

    # Terminal success status group
    EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED = (
        "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED", 
        ("terminal", "success")
    )
    EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_SIMPLE = (
        "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_SIMPLE",
        ("terminal", "success")
    )
    EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_AMONG_SYNONYMS_SIMPLE = (
        "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_AMONG_SYNONYMS_SIMPLE",
        ("terminal", "success")
    )
    EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_AUTHOR_DISAMBIGUATION = (
        "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_AUTHOR_DISAMBIGUATION",
        ("terminal", "success")
    )
    EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_RETRY = (
        "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_RETRY", 
        ("terminal", "success")
    )
    EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_INNER_RANK_DISAMBIGUATION = ( 
        "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_INNER_RANK_DISAMBIGUATION",
        ("terminal", "success")
    )
    EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_RANK_LEVEL_DISAMBIGUATION = (
        "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_RANK_LEVEL_DISAMBIGUATION",
        ("terminal", "success")
    )
    EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_SYNONYM_DISAMBIGUATION = (
        "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_SYNONYM_DISAMBIGUATION",
        ("terminal", "success")
    )
    EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_MULTI_RESULT_DISAMBIGUATION = (
        "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_MULTI_RESULT_DISAMBIGUATION",
        ("terminal", "success")
    )
    EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_RESULT_WITHIN_QUERY = (
        "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_RESULT_WITHIN_QUERY",
        ("terminal", "success")
    )
    FUZZY_MATCH_PRIMARY_SOURCE_ACCEPTED = (
        "FUZZY_MATCH_PRIMARY_SOURCE_ACCEPTED",
        ("terminal", "success")
    )
    SINGLE_FUZZY_MATCH_PRIMARY_SOURCE_ACCEPTED_SIMPLE = (
        "SINGLE_FUZZY_MATCH_PRIMARY_SOURCE_ACCEPTED_SIMPLE",
        ("terminal", "success")
    )
    EXACT_MATCH_PRIMARY_SOURCE_SYNONYM = (
        "EXACT_MATCH_PRIMARY_SOURCE_SYNONYM",
        ("terminal", "success")
    )
    PARTIAL_EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_DISAMBIGUATED = (
        "PARTIAL_EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_DISAMBIGUATED",
        ("terminal", "success")
    )
    EXACT_MATCH_SECONDARY_SOURCE_ACCEPTED_PRUNED = (
        "EXACT_MATCH_SECONDARY_SOURCE_ACCEPTED_PRUNED",
        ("terminal", "success")
    )
    
    # Forced acceptance status
    FORCE_ACCEPTED = (
        "FORCE_ACCEPTED",
        ("terminal", "success")
    )

    # Terminal failure status group
    EMPTY_INPUT_TAXONOMY = (
        "EMPTY_INPUT_TAXONOMY",
        ("terminal", "failure")
    )
    FAILED = (
        "FAILED",
        ("terminal", "failure")
    )
    NO_MATCH_RETRIES_EXHAUSTED = (
        "NO_MATCH_RETRIES_EXHAUSTED",
        ("terminal", "failure")
    )

    # Retry status group
    NO_MATCH_NONEMPTY_QUERY = (
        "NO_MATCH_NONEMPTY_QUERY",
        ("non-terminal", "retry")
    )

    # Non-terminal status group
    PROCESSING = (
        "PROCESSING",
        ("non-terminal", "processing")
    )
    MULTIPLE_EXACT_MATCHES = (
        "MULTIPLE_EXACT_MATCHES",
        ("non-terminal", "processing")
    )
    RETRY_SCHEDULED = (
        "RETRY_SCHEDULED",
        ("non-terminal", "processing")
    ) 

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
        # Check scientific_name separately if all ranks are empty/invalid
        value = self.scientific_name
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
        """
        Return the most specific taxonomic rank that has valid data. 
        If taxonomic data is empty, return None.
        """
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
        If taxonomic data is empty, return None.
        """
        for field_name, rank in TAXONOMIC_QUERY_PRECEDENCE:
            value = getattr(self, field_name, None)
            if value and value.strip().lower() not in INVALID_VALUES:
                return value.strip()
        return None

    @property
    def key(self) -> str:
        """Unique, deterministic key based on hash of shared taxonomic data."""
        terms = []
        for field, _ in TAXONOMIC_QUERY_PRECEDENCE:
            term = getattr(self, field, "") or ""
            terms.append(term.strip().lower())
        taxa_data = "|".join(terms)

        return hashlib.sha256(taxa_data.encode("utf-8")).hexdigest()

    def resolve_taxonomic_entries(self, resolver: Callable[[str], Optional[TaxonomicEntry]]) -> List[TaxonomicEntry]:
        """
        Retrieve full TaxonomicEntry objects corresponding to the stored entry UUIDs.
        
        Args:
            resolver: A function mapping an entry UUID (str) to a TaxonomicEntry.
        
        Returns:
            A list of TaxonomicEntry objects sorted by their UUIDs. 

        Usage example:
            # Assuming entry_index is a Dict[str, TaxonomicEntry]
            resolved_entries = entry_group.resolve_taxonomic_entries(entry_index.get)
        """
        # Sort UUIDs for consistent ordering
        return [resolver(uuid) for uuid in sorted(self.entry_uuids) if resolver(uuid) is not None]

@dataclass(frozen=True)
class QueryParameters:
    """Represents the parameters for a unique GNVerifier query."""
    term: str
    rank: str
    source_id: int

@dataclass(frozen=True)
class ResolutionAttempt:
    """Records the result of a GNVerifier query and its interpretation."""

    # Core linking and query info
    entry_group_key: str
    query_rank: str
    query_term: str
    data_source_id: int # The GNVerifier data source ID used for this attempt's query

    # Resolution outcome, assigned after query result obtained
    status: ResolutionStatus
    resolved_classification: Optional[Dict[str, str]] = None # If successful

    # Provenance and diagnostics
    gnverifier_response: Optional[GNVerifierName] = None # Raw Pydantic model from API response
    previous_key: Optional[str] = None # Key of the attempt before this one (if retry)
    error: Optional[str] = None # Records errors during execution or classification
    resolution_strategy_name: Optional[str] = None # Which strategy assigned the status
    failure_reason: Optional[str] = None # Specific reason if status is FAILED/error
    scheduled_query_params: Optional[QueryParameters] = None 

    # Flexible metadata
    # For extra, non-essential info specific to a strategy or temporary state
    metadata: Dict[str, Union[str, int, float, bool]] = field(default_factory=dict) 

    @property
    def is_retry(self) -> bool:
        return self.previous_key is not None
    
    @property
    def is_successful(self) -> bool:
        return self.status.is_successful

    @property
    def key(self) -> str:
        """
        Compute a unique key that deterministically identifies this resolution attempt.
        
        Includes the core components that define the attempt's identity:
        - entry_group_key: The group being resolved
        - query information: rank, term, and data source ID
        - gnverifier_response: The API response (or empty string if none)
        """
        response_str = ""
        if self.gnverifier_response is not None:
            try:
                # Step 1: Dump Pydantic model to dict
                response_dict = self.gnverifier_response.model_dump(mode='json')
                # Step 2: Dump dict to sorted JSON string
                response_str = json.dumps(response_dict, sort_keys=True)
            except AttributeError: # Fallback for older Pydantic or different environments
                 try:
                      response_dict = self.gnverifier_response.dict()
                      response_str = json.dumps(response_dict, sort_keys=True)
                 except Exception as e:
                      # Log differently here if needed, maybe just print for dataclass context
                      print(f"Warning: Could not serialize self.gnverifier_response for key property: {e}")
                      response_str = ""
            except Exception as e:
                 print(f"Warning: Could not serialize self.gnverifier_response for key property: {e}")
                 response_str = ""

        key_components = [
            self.entry_group_key or "",
            self.query_term or "",
            self.query_rank or "",
            str(self.data_source_id) if self.data_source_id is not None else "",
            response_str # Add the serialized response
        ]

        combined = "|".join(key_components)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()
