"""Query execution for TaxonoPy.

This module provides functions for executing taxonomic queries against
the GNVerifier service, processing the results, and preparing data for
ResolutionAttempt objects.
"""

import logging
from typing import List, Dict, Optional, Tuple, Iterator
from datetime import datetime

from tqdm import tqdm

from taxonopy.types.data_classes import (
    QueryGroupRef, 
    ResolutionStatus, 
    ResolutionAttempt
)
from taxonopy.types.gnverifier import Name as GNVerifierName
from taxonopy.gnverifier_client import GNVerifierClient
from taxonopy.resolution.attempt_manager import ResolutionAttemptManager


def batch_query_groups(
    query_groups: List[QueryGroupRef], 
    batch_size: int = 10000
) -> Iterator[List[QueryGroupRef]]:
    """Batch query groups for efficient processing.
    
    Args:
        query_groups: List of query groups to batch
        batch_size: Maximum number of query groups per batch
        
    Yields:
        Batches of query groups
    """
    for i in range(0, len(query_groups), batch_size):
        yield query_groups[i:i + batch_size]


def execute_query_batch(
    batch: List[QueryGroupRef],
    client: GNVerifierClient,
    resolution_manager: ResolutionAttemptManager,
    show_progress: bool = True,
    timeout: int = 300
) -> Dict[str, ResolutionAttempt]:
    """Execute a batch of queries and create resolution attempts.
    
    Args:
        batch: Batch of query groups to process
        client: GNVerifier client for executing queries
        resolution_manager: Manager for creating resolution attempts
        show_progress: Whether to show a progress bar
        timeout: Timeout in seconds for query execution
        
    Returns:
        Dictionary mapping query group keys to resolution attempts
    """
    # Extract query terms from query groups
    query_terms = []
    query_group_map = {}  # Maps query term to query group
    
    for query_group in batch:
        query_terms.append(query_group.query_term)
        query_group_map[query_group.query_term] = query_group
    
    # Execute the query batch
    logging.info(f"Executing batch of {len(query_terms)} query terms")
    
    try:
        results = client.execute_query(query_terms)#, timeout=timeout)
    except (RuntimeError, TimeoutError) as e:
        logging.error(f"Failed to execute query batch: {str(e)}")
        # Create failed resolution attempts for all query groups in the batch
        return _create_failed_resolution_attempts(
            batch, 
            resolution_manager, 
            ResolutionStatus.FAILED,
            {"error": str(e)}
        )
    
    # Process results and create resolution attempts
    resolution_attempts = {}
    
    # Create an iterator with or without progress bar
    iter_terms = tqdm(query_terms, desc="Processing results") if show_progress else query_terms
    
    for i, term in enumerate(iter_terms):
        query_group = query_group_map[term]
        # Access the corresponding result by index
        result = results[i] if i < len(results) else None

        if result:
            # Create resolution attempt based on result
            attempt = _create_resolution_attempt_from_result(
                query_group, result, resolution_manager
            )
        else:
            # Create a failed resolution attempt
            attempt = resolution_manager.create_attempt(
                query_group_key=query_group.query_term,
                query_term=query_group.query_term,
                query_rank=query_group.query_rank,
                status=ResolutionStatus.FAILED,
                gnverifier_response=None,
                metadata={"error": "No result received from GNVerifier"}
            )
        
        resolution_attempts[query_group.query_term] = attempt

        print(f"Attempts: {resolution_attempts}")
    
    return resolution_attempts


def _create_resolution_attempt_from_result(
    query_group: QueryGroupRef,
    result: dict,  # note that result is now a dict
    resolution_manager: ResolutionAttemptManager) -> ResolutionAttempt:
    # Convert the dictionary to a GNVerifierName object
    try:
        result_obj = GNVerifierName.parse_obj(result)
    except Exception as e:
        resolution_manager.logger.error(f"Error parsing GNVerifier result: {e}")
        result_obj = None

    # If conversion failed, treat it as no match
    if result_obj is None:
        return resolution_manager.create_attempt(
            query_group_key=query_group.query_term,
            query_term=query_group.query_term,
            query_rank=query_group.query_rank,
            status=ResolutionStatus.FAILED,
            gnverifier_response=None,
            metadata={"error": "Failed to parse GNVerifier result"}
        )
    
    match_type = result_obj.match_type.root if result_obj.match_type else "NoMatch"
    
    if match_type == "NoMatch":
        status = ResolutionStatus.NO_MATCH
    elif match_type == "Exact":
        status = ResolutionStatus.EXACT_MATCH
    elif match_type in ["Fuzzy", "FuzzyRelaxed"]:
        status = ResolutionStatus.FUZZY_MATCH
    elif match_type in ["Partial", "PartialFuzzy", "PartialFuzzyRelaxed", "Virus", "FacetedSearch"]:
        status = ResolutionStatus.PARTIAL_MATCH
    else:
        status = ResolutionStatus.AMBIGUOUS_MATCH
    
    # Extract classification if available
    resolved_classification = None
    if status in [ResolutionStatus.EXACT_MATCH, ResolutionStatus.FUZZY_MATCH, ResolutionStatus.PARTIAL_MATCH]:
        if result_obj.best_result and result_obj.best_result.classification_path and result_obj.best_result.classification_ranks:
            resolved_classification = _extract_classification(
                result_obj.best_result.classification_path,
                result_obj.best_result.classification_ranks
            )
    
    # Create metadata for the resolution attempt
    metadata = {
        "data_sources_num": result_obj.data_sources_num,
        "curation": result_obj.curation,
        "match_type": match_type,
        "timestamp": datetime.now().isoformat()
    }
    
    if result_obj.error:
        metadata["error"] = result_obj.error
    
    return resolution_manager.create_attempt(
        query_group_key=query_group.query_term,
        query_term=query_group.query_term,
        query_rank=query_group.query_rank,
        status=status,
        gnverifier_response=result_obj,
        resolved_classification=resolved_classification,
        metadata=metadata
    )


def _extract_classification(
    classification_path: str, 
    classification_ranks: str
) -> Dict[str, str]:
    """Extract classification from GNVerifier result paths.
    
    Args:
        classification_path: Pipe-separated path of taxon names
        classification_ranks: Pipe-separated path of ranks
        
    Returns:
        Dictionary mapping ranks to taxon names
    """
    classification = {}
    
    # Split the paths into lists
    taxa = classification_path.split('|')
    ranks = classification_ranks.split('|')
    
    # Map ranks to taxa
    for i, rank in enumerate(ranks):
        if i < len(taxa):
            # Convert 'class' to 'class_' to match TaxonomicEntry fields
            if rank == "class":
                rank = "class_"
            classification[rank] = taxa[i]
    
    return classification


def _create_failed_resolution_attempts(
    batch: List[QueryGroupRef],
    resolution_manager: ResolutionAttemptManager,
    status: ResolutionStatus,
    metadata: Dict
) -> Dict[str, ResolutionAttempt]:
    """Create failed resolution attempts for all query groups in a batch.
    
    Args:
        batch: Batch of query groups
        resolution_manager: Manager for creating resolution attempts
        status: Resolution status to set
        metadata: Metadata to include in the attempts
        
    Returns:
        Dictionary mapping query group keys to resolution attempts
    """
    attempts = {}
    
    for query_group in batch:
        attempt = resolution_manager.create_attempt(
            query_group_key=query_group.query_term,
            query_term=query_group.query_term,
            query_rank=query_group.query_rank,
            status=status,
            gnverifier_response=None,
            metadata=metadata
        )
        attempts[query_group.query_term] = attempt
    
    return attempts


def execute_all_queries(
    query_groups: List[QueryGroupRef],
    client: GNVerifierClient,
    resolution_manager: ResolutionAttemptManager,
    batch_size: int = 10000,
    show_progress: bool = True
) -> Dict[str, ResolutionAttempt]:
    """Execute all queries for taxonomic resolution.
    
    This is the main entry point for the module.
    
    Args:
        query_groups: List of query groups to process
        client: GNVerifier client for executing queries
        resolution_manager: Manager for creating resolution attempts
        batch_size: Maximum number of query groups per batch
        show_progress: Whether to show a progress bar
        
    Returns:
        Dictionary mapping query group keys to resolution attempts
    """
    all_attempts = {}
    
    # Batch the query groups
    batches = list(batch_query_groups(query_groups, batch_size))
    
    logging.info(f"Processing {len(query_groups)} query groups in {len(batches)} batches")
    
    # Process each batch
    for i, batch in enumerate(batches):
        logging.info(f"Processing batch {i+1}/{len(batches)} with {len(batch)} query groups")
        
        batch_attempts = execute_query_batch(
            batch, 
            client, 
            resolution_manager,
            show_progress=show_progress
        )
        
        # Add batch results to overall results
        all_attempts.update(batch_attempts)
    
    logging.info(f"Completed processing {len(query_groups)} query groups")
    
    return all_attempts
