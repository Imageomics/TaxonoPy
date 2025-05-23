"""Query planning for TaxonoPy.

This module provides functions for planning and organizing queries to the
GNVerifier API based on taxonomic data. It transforms EntryGroupRef objects
into QueryParameters objects that can be used for efficient API queries.
"""

import logging
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from taxonopy.types.data_classes import EntryGroupRef, QueryParameters, ResolutionAttempt
from taxonopy.constants import DATA_SOURCE_PRECEDENCE, TAXONOMIC_QUERY_PRECEDENCE, INVALID_VALUES

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager


logger = logging.getLogger(__name__)

def plan_initial_queries(
    entry_group_map: Dict[str, EntryGroupRef]
) -> Dict[str, QueryParameters]:
    """
    Determines the initial QueryParameters for each EntryGroupRef.

    Uses the most specific term/rank from the EntryGroupRef and the
    primary data source ID.

    Args:
        entry_group_map: Dictionary mapping entry group keys to EntryGroupRef objects.

    Returns:
        Dictionary mapping entry group keys to their initial QueryParameters.
    """
    initial_plans: Dict[str, QueryParameters] = {}
    
    # Get the primary data source ID (first one in the precedence list)
    primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
    logger.info(f"Using primary data source ID for initial queries: {primary_source_id}")

    
    processed_count = 0
    for entry_group_key, entry_group in entry_group_map.items():
        query_term = entry_group.most_specific_term
        query_rank = entry_group.most_specific_rank # Maps field name ('class_') to API rank ('class')

        # Handle cases where the entry group might have no usable taxonomy
        if query_term is None:
            query_term = "" # If no term found
            query_rank = None # No specific rank if term is empty
            logger.debug(f"Entry group {entry_group_key} has no valid taxonomy. Planning empty query.")
        
        # Create QueryParameters object
        params = QueryParameters(
            term=query_term,
            rank=query_rank,
            source_id=primary_source_id
        )
        initial_plans[entry_group_key] = params
        processed_count += 1

    logger.info(f"Planned {len(initial_plans)} initial queries.")
    if processed_count != len(entry_group_map):
         logger.warning(f"Processed count ({processed_count}) doesn't match input group count ({len(entry_group_map)}). Check logic.")
         
    return initial_plans


def plan_retry_query(
    attempt: ResolutionAttempt,
    entry_group: EntryGroupRef,
    manager: "ResolutionAttemptManager"
) -> Optional[QueryParameters]:
    """
    Determines the next QueryParameters for a retry attempt based on history
    and precedence rules.

    Args:
        attempt: The latest ResolutionAttempt that indicates a retry is needed.
        entry_group: The corresponding EntryGroupRef object.
        manager: The ResolutionAttemptManager to access attempt history.

    Returns:
        The QueryParameters for the next retry, or None if retries are exhausted.
    """
    logger.debug(f"Planning retry for EntryGroup {entry_group.key}, starting from attempt {attempt.key} (Term: '{attempt.query_term}', Source: {attempt.data_source_id})")

    # 1. Get history and already attempted combinations
    attempt_chain = manager.get_group_attempt_chain(entry_group.key)
    attempted_combinations: Set[Tuple[str, Optional[str], Optional[int]]] = set()
    for prev_attempt in attempt_chain:
        # Ensure we store normalized/consistent values in the set
        term = prev_attempt.query_term or ""
        rank = prev_attempt.query_rank # Keep None as None
        source_id = prev_attempt.data_source_id # Keep None as None
        attempted_combinations.add((term, rank, source_id))
    
    logger.debug(f"Found {len(attempted_combinations)} previously attempted combinations.")

    # 2. Get available terms/ranks from the entry group, respecting precedence
    available_term_rank_pairs = _get_available_term_rank_pairs(entry_group)
    if not available_term_rank_pairs:
        logger.warning(f"Entry group {entry_group.key} has no valid term/rank pairs for retry planning.")
        return None # Exhausted if no terms to query

    # 3. Get ordered list of data source IDs
    available_source_ids = list(DATA_SOURCE_PRECEDENCE.values())
    if not available_source_ids:
         logger.error("DATA_SOURCE_PRECEDENCE is empty. Cannot plan retries.")
         return None # Exhausted (or configuration error)

    # 4. Determine the starting point for searching based on the current attempt
    current_term = attempt.query_term or ""
    current_rank = attempt.query_rank
    current_source_id = attempt.data_source_id

    # Retry logic
    
    # Find the index of the current term/rank pair in the available list
    current_pair_index = -1
    if current_term: # Only search if the current attempt had a term
        for i, (term, rank) in enumerate(available_term_rank_pairs):
            if term == current_term and rank == current_rank:
                current_pair_index = i
                break
    elif not current_term and available_term_rank_pairs: # If current attempt had no term, start from the first available pair
         current_pair_index = 0
    # If current_term exists but wasn't found in available pairs, it's an error
    elif current_term and current_pair_index == -1:
        error_msg = (
            f"Data inconsistency detected for EntryGroup {entry_group.key}: "
            f"Triggering attempt {attempt.key} used term/rank ('{current_term}', {current_rank}) "
            f"which is not found in the available pairs derived from the EntryGroupRef: {available_term_rank_pairs}. "
            "Cannot reliably plan retry."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Iterate through term/rank pairs starting from the current one
    for i in range(current_pair_index, len(available_term_rank_pairs)):
        term_to_try, rank_to_try = available_term_rank_pairs[i]

        # Determine starting source index for this term/rank pair
        start_source_index = 0
        if i == current_pair_index and current_source_id is not None:
            try:
                # Start checking sources after the one that just failed for the current term/rank
                start_source_index = available_source_ids.index(current_source_id) + 1
            except ValueError:
                logger.warning(f"Current attempt's source ID {current_source_id} not found in DATA_SOURCE_PRECEDENCE. Starting source check from index 0.")
                start_source_index = 0
        
        # Iterate through data sources for the current term/rank pair
        for j in range(start_source_index, len(available_source_ids)):
            source_id_to_try = available_source_ids[j]
            
            next_combination = (term_to_try, rank_to_try, source_id_to_try)
            
            if next_combination not in attempted_combinations:
                # logger.info(f"Retry Plan for {entry_group.key}: Next query -> Term='{term_to_try}', Rank={rank_to_try}, SourceID={source_id_to_try}")
                return QueryParameters(term=term_to_try, rank=rank_to_try, source_id=source_id_to_try)

    # If we've exhausted all combinations for all available term/rank pairs
    logger.info(f"Retries exhausted for EntryGroup {entry_group.key}.")
    return None # Exhausted

def _get_available_term_rank_pairs(entry_group: EntryGroupRef) -> List[Tuple[str, Optional[str]]]:
    """
    Gets valid (non-empty/invalid) term/rank pairs from an EntryGroupRef,
    ordered by TAXONOMIC_QUERY_PRECEDENCE (most specific first).
    """
    pairs = []
    # Avoid adding the same term if it appears under multiple fields (e.g., species and scientific_name)
    # Keeps the term/rank pair of the most specific one.
    seen_terms = set() 
    
    for field_name, api_rank in TAXONOMIC_QUERY_PRECEDENCE:
        value = getattr(entry_group, field_name, None)
        if value:
            term = value.strip()
            if term and term.lower() not in INVALID_VALUES and term not in seen_terms:
                pairs.append((term, api_rank))
                seen_terms.add(term)

    return pairs
