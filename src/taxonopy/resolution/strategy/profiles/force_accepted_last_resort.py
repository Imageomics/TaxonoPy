import logging
from typing import Optional, TYPE_CHECKING, Dict

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.constants import TAXONOMIC_RANKS

from .profile_logging import setup_profile_logging
_PROFILE_DEBUG_OVERRIDE_ = False  # Set to True for debugging
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ForceAcceptedLastResort"

class ForceAcceptedLastResortStrategy(ResolutionStrategy):
    """
    Last resort profile that always matches and simply passes through the 
    original taxonomic data from the input EntryGroupRef.
    
    This profile behaves like the --force-input flag but within the resolution workflow,
    ensuring that no entries fail resolution even if no other profile matches.
    
    This should be the very last profile checked in the CLASSIFICATION_CASES list.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Always accepts the attempt and uses the original input data as the resolution.
        """
        # This profile always matches - it's the last resort
        logger.info(f"Applied {STRATEGY_NAME} to attempt {attempt.key}: No other profiles matched, using input data as resolution.")
        
        # Create a resolution classification using the input EntryGroupRef data
        resolved_classification = {}
        for rank in TAXONOMIC_RANKS:
            value = getattr(entry_group, rank, None)
            if value:  # Only include non-empty values
                resolved_classification[rank] = value

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.FORCE_ACCEPTED,  # Use the FORCE_ACCEPTED status
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=resolved_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={
                'reason': 'last_resort_fallback',
                'note': 'Used original input data without resolution'
            }
        )
        logger.info(f"Created FORCE_ACCEPTED attempt {final_attempt.key} as last resort for {attempt.key}")
        return final_attempt

# Expose for registration
strategy_instance = ForceAcceptedLastResortStrategy()
check_and_resolve = strategy_instance.check_and_resolve
