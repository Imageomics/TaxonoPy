from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import List, Dict, Optional

from .gnverifier import ResultData as GNVerifierResponse

class ResolutionStatus(Enum):
    """Status of a resolution attempt"""
    RESOLVED = auto()         # Successfully resolved
    NEEDS_RETRY = auto()      # Failed but has higher ranks to try
    LINKED = auto()           # Links to another successful resolution
    UNRESOLVABLE = auto()     # Failed with no more ranks to try

@dataclass(frozen=True)
class TaxonomicEntry:
    """Single entry from input data"""
    uuid: str
    scientific_name: Optional[str]
    kingdom: str
    phylum: str
    class_: str
    order: str
    family: str
    genus: str
    species: str
    common_name: Optional[str]

@dataclass(frozen=True)
class EntryGroupRef:
    """Group of entries sharing same taxonomic data"""
    key: str  # The taxonomic combination key
    entry_ids: List[str]  # UUIDs of TaxonomicEntries

@dataclass(frozen=True)
class QueryGroupRef:
    """Group of entries sharing same query term"""
    term: str  # Term to query
    rank: str  # Rank of the term
    group_keys: List[str]  # Keys to EntryGroupRefs

@dataclass(frozen=True)
class ResolutionAttempt:
    """Result of attempting to resolve a query term"""
    term: str  # Query term attempted
    rank: str  # Rank of query term
    status: ResolutionStatus
    gnverifier_response: Optional[GNVerifierResponse] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)