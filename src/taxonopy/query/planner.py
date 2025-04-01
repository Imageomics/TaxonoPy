"""Query planning for TaxonoPy.

This module provides functions for planning and organizing queries to the
GNVerifier API based on taxonomic data. It transforms EntryGroupRef objects
into QueryGroupRef objects that can be used for efficient API queries.
"""

import hashlib
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple, Iterator, Mapping
from dataclasses import dataclass

from tqdm import tqdm
import logging

from taxonopy.types.data_classes import (
    EntryGroupRef, 
    QueryGroupRef
)
from taxonopy.cache_manager import cached
from taxonopy.entry_grouper import create_entry_groups
from taxonopy.config import config
from taxonopy.constants import DATA_SOURCE_PRECEDENCE


logger = logging.getLogger(__name__)

# def get_query_term_and_rank(entry_group: EntryGroupRef) -> Tuple[str, str]:
#     """Determine the optimal query term and its rank for an entry group.
    
#     This function examines the taxonomic data of the entry group and chooses 
#     the most specific non-null field to use as the query term. The precedence order is:
#     1. species (often contains a genus species binomial)
#     2. scientific_name
#     3. genus
#     4. family
#     5. order
#     6. class_
#     7. phylum
#     8. kingdom
    
#     Args:
#         entry_group: The entry group to plan a query for
        
#     Returns:
#         A tuple of (query_term, rank)
        
#     Raises:
#         ValueError: If no valid query term can be determined
#     """
#     # Check fields in order of precedence
#     precedence = [
#         ("species", "species"),
#         ("scientific_name", "scientific_name"),
#         ("genus", "genus"),
#         ("family", "family"),
#         ("order", "order"),
#         ("class_", "class"),
#         ("phylum", "phylum"),
#         ("kingdom", "kingdom")
#     ]
    
#     for field, rank in precedence:
#         value = getattr(entry_group, field)
#         if value and value.strip().lower() not in ['unknown', 'null', 'none', '', 'n/a']:
#             # Clean and normalize the query term
#             query_term = value.strip()
#             return query_term, rank
    
#     # If we get here, there's no valid query term
#     msg = f"""
#     No valid query term found for entry group {entry_group.key}.
#     Count: {entry_group.group_count} 
#     Taxonomic data: {entry_group.kingdom} {entry_group.phylum} {entry_group.class_} {entry_group.order} {entry_group.family} {entry_group.genus} {entry_group.scientific_name} 
# {entry_group.species}
#     """
#     raise ValueError(msg)


# def generate_query_key(query_term: str, query_rank: str) -> str:
#     """Generate a unique key for a query based on term and rank.
    
#     Args:
#         query_term: The term to be queried
#         query_rank: The rank of the term
        
#     Returns:
#         A hash string that uniquely identifies the query
#     """
#     # Concatenate term and rank in a consistent format
#     query_data = f"{query_term.lower().strip()}|{query_rank.lower().strip()}"
    
#     # Generate a SHA-256 hash
#     return hashlib.sha256(query_data.encode()).hexdigest()


# def create_query_groups(
#     entry_groups: List[EntryGroupRef],
#     progress_bar: bool = True
# ) -> Dict[str, QueryGroupRef]:
#     """Create query groups from entry groups based on query terms.
    
#     This function examines each entry group, determines the optimal query term,
#     and groups entry groups that will use the same query term to optimize API calls.
    
#     Args:
#         entry_groups: List of entry groups to organize into query groups
#         progress_bar: Whether to show a progress bar
        
#     Returns:
#         A dictionary mapping query keys to QueryGroupRef objects
#     """
#     # Initialize query groups
#     query_groups: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: {"group_keys": set(), "representative": ""})
#     query_terms: Dict[str, Tuple[str, str]] = {}  # Maps query_key -> (query_term, query_rank)
    
#     # Create an iterator with or without progress bar
#     iter_groups = tqdm(entry_groups, desc="Planning queries") if progress_bar else entry_groups
    
#     # Process each entry group
#     for entry_group in iter_groups:
#         try:
#             # Determine query term and rank directly from the entry group's taxonomic data
#             query_term, query_rank = get_query_term_and_rank(entry_group)
            
#             # Generate a key for this query
#             query_key = generate_query_key(query_term, query_rank)
            
#             # Store the query term and rank for later use
#             query_terms[query_key] = (query_term, query_rank)
            
#             # Add this entry group to the query group
#             if not query_groups[query_key]["representative"]:
#                 query_groups[query_key]["representative"] = entry_group.key
                
#             query_groups[query_key]["group_keys"].add(entry_group.key)
            
#         except ValueError as e:
#             # Log error and skip this entry group
#             logger.warning(f"Warning: {str(e)}")
#             continue
    
#     # Convert to QueryGroupRef objects
#     return {
#         key: QueryGroupRef(
#             query_term=query_terms[key][0],
#             query_rank=query_terms[key][1],
#             entry_group_keys=frozenset(data["group_keys"]),
#             data_source_id=11 # Default to GBIF for now
#         )
#         for key, data in query_groups.items()
#     }

# @cached(
#     prefix="query_plans",
#     key_args=["input_path"]
# )
# def create_query_plans(input_path: str) -> List[QueryGroupRef]:
#     """Create query plans from entry groups.
    
#     This is the main entry point for the module.
    
#     Args:
#         input_path: Path to input directory or file
        
#     Returns:
#         List of QueryGroupRef objects
#     """
#     # Get entry groups for this input path
#     entry_groups = create_entry_groups(input_path)
    
#     # Create query groups directly from entry groups
#     query_groups = create_query_groups(entry_groups)
    
#     # Return as list
#     return list(query_groups.values())

@cached(
    prefix="query_plans",
    key_args=["entry_groups", "data_source_id"],
    max_age=config.cache_max_age
)
def create_initial_query_plans(
    entry_groups: List[EntryGroupRef],
    data_source_id: int = DATA_SOURCE_PRECEDENCE['GBIF'],  # Default to GBIF
    progress_bar: bool = True
) -> List[QueryGroupRef]:
    """
    Create initial query plans from entry groups.
    
    This groups entry groups by their most specific term and rank,
    creating QueryGroupRef objects for efficient API queries.
    
    Args:
        entry_groups: List of entry groups to organize
        data_source_id: The initial data source ID to query (default: GBIF)
        progress_bar: Whether to show a progress bar
        
    Returns:
        List of QueryGroupRef objects
    """
    from collections import defaultdict
    from tqdm import tqdm
    
    # Create a dictionary to group entry groups by query term and rank
    query_groups = defaultdict(list)

    print(f"Raw entry groups!!!!!!!!: {entry_groups}")
    # print(f"Entry Group keys: {[eg.key for eg in entry_groups]}")
    
    # Create an iterator with or without progress bar
    iter_groups = tqdm(entry_groups, desc="Planning queries") if progress_bar else entry_groups
   
    # Group entry groups by most specific term and rank
    for entry_group in iter_groups:
        query_rank = entry_group.most_specific_rank
        query_term = entry_group.most_specific_term
        
        if not query_rank or not query_term:
            logger.warning(f"Skipping entry group with no valid query term: {entry_group.key}")
            continue
        
        # Create a grouping key for the dictionary
        group_key = f"{query_rank}|{query_term}"
        query_groups[group_key].append(entry_group)
    
    # Create QueryGroupRef objects for each group
    result = []
    for group_key, group_entry_groups in query_groups.items():
        query_rank, query_term = group_key.split("|", 1)
        
        # Collect entry group keys
        entry_group_keys = frozenset(eg.key for eg in group_entry_groups)
        
        # Create QueryGroupRef
        query_group = QueryGroupRef(
            query_rank=query_rank,
            query_term=query_term,
            data_source_id=data_source_id,
            entry_group_keys=entry_group_keys
        )
        
        result.append(query_group)
    
    logger.info(f"Created {len(result)} query plans from {len(entry_groups)} entry groups")
    return result
