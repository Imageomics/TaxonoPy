import logging
from typing import Optional, TYPE_CHECKING
from taxonopy.constants import INVALID_VALUES, TAXONOMIC_RANKS

from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "EmptyInputTaxonomy"

def check_and_resolve(attempt: ResolutionAttempt,
                      entry_group: EntryGroupRef,
                      manager: "ResolutionAttemptManager"
                      ) -> Optional[ResolutionAttempt]:
    """
    Checks for the profile: Taxonomic data for input group is empty.
    If matched, creates and returns the final EMPTY_INPUT_TAXONOMY attempt.
    Returns None otherwise.
    """
    # Profile condition check
    any_taxonomic_data = False
    for rank in TAXONOMIC_RANKS:
        value = getattr(entry_group, rank)
        if value not in INVALID_VALUES:
            any_taxonomic_data = True
            logger.debug(f"Entry group {entry_group.key} has taxonomic data for rank {rank}: {value}")
            break

    # Also check 'scientific_name' and 'query_term'
    if entry_group.scientific_name not in INVALID_VALUES:
        any_taxonomic_data = True
        logger.debug(f"Entry group {entry_group.key} has taxonomic data for scientific_name: {entry_group.scientific_name}")

    if any_taxonomic_data:
        return None # Profile mismatch, queryable taxonomic data found

    # Profile matched
    logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}.")
    
    # Action: none needed, just assign status.

    # Create final attempt
    final_attempt = manager.create_attempt(
        entry_group_key=attempt.entry_group_key,
        query_term=attempt.query_term,
        query_rank=attempt.query_rank,
        data_source_id=attempt.data_source_id,
        status=ResolutionStatus.EMPTY_INPUT_TAXONOMY,
        gnverifier_response=attempt.gnverifier_response,
        resolved_classification=None,
        error=None,
        resolution_strategy_name=STRATEGY_NAME,
        failure_reason="Query originated from input group with no usable taxonomic data.",
        metadata={}
    )
    logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}")
    return final_attempt
