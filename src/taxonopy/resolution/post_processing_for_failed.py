"""Post-processing operations for taxonomic resolution.

This module contains functions for post-processing resolution results,
such as forcing failed resolutions to use their original input data.
"""

import logging
from typing import Dict, List, Optional, Set

from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionStatus,
    ResolutionAttempt
)

logger = logging.getLogger(__name__)

def force_failed_to_input(
    manager: 'ResolutionAttemptManager',
    entry_group_map: Dict[str, EntryGroupRef]
) -> int:
    """
    Force all failed resolution attempts to use their original input taxonomy.
    
    This function:
    1. Finds all entry groups with failed final resolution attempts
    2. Creates new ResolutionAttempt objects with FAILED_FORCED_INPUT status
    3. Copies the taxonomic hierarchy from the original EntryGroupRef
    
    Args:
        manager: The ResolutionAttemptManager containing the attempts
        entry_group_map: Dictionary mapping entry group keys to EntryGroupRef objects
    
    Returns:
        Number of attempts that were forced to use input data
    """
    logger.info("Starting force-failed-to-input post-processing...")
    
    forced_count = 0
    failure_statuses = {
        ResolutionStatus.FAILED,
        ResolutionStatus.NO_MATCH_RETRIES_EXHAUSTED,
        # additional failure status labels go here
    }
    
    # For each entry group, check if its final attempt is a failure
    for entry_group_key, latest_attempt_key in manager._entry_group_latest_attempt.items():
        latest_attempt = manager.get_attempt(latest_attempt_key)
        
        # Skip if not a failure or entry group not found
        if not latest_attempt or latest_attempt.status not in failure_statuses:
            continue
            
        entry_group = entry_group_map.get(entry_group_key)
        if not entry_group:
            logger.warning(f"Entry group {entry_group_key} not found when forcing failed-to-input.")
            continue
        
        # Create resolved_classification dictionary from the original entry group
        resolved_classification = {}
        for field in ['kingdom', 'phylum', 'class_', 'order', 'family', 'genus', 'species']:
            value = getattr(entry_group, field, None)
            if value:  # Only include non-empty values
                resolved_classification[field] = value
        
        # Create a new attempt with FAILED_FORCED_INPUT status
        forced_attempt = manager.create_attempt(
            entry_group_key=entry_group_key,
            query_term=latest_attempt.query_term,
            query_rank=latest_attempt.query_rank,
            data_source_id=latest_attempt.data_source_id,
            status=ResolutionStatus.FAILED_FORCED_INPUT,
            gnverifier_response=latest_attempt.gnverifier_response,
            resolved_classification=resolved_classification,
            error=latest_attempt.error,
            resolution_strategy_name="ForceFailedToInput",
            failure_reason=latest_attempt.failure_reason,
            metadata={
                'original_status': latest_attempt.status.name,
                'force_failed_to_input': True,
                'original_attempt_key': latest_attempt_key,
                # Preserve existing metadata if any
                **(latest_attempt.metadata or {})
            }
        )
        
        forced_count += 1
        
    logger.info(f"Force-failed-to-input complete: {forced_count} attempts forced to use input data.")
    return forced_count
