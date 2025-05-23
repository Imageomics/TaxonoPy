import logging
from typing import Optional, TYPE_CHECKING, List

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE, TAXONOMIC_RANKS

from .profile_logging import setup_profile_logging
_PROFILE_DEBUG_OVERRIDE_ = False  # Set to True for debugging
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "PartialExactMatchPrimarySourceSimple"
# Use the new status if you added it
SUCCESS_STATUS = getattr(ResolutionStatus, "PARTIAL_EXACT_MATCH_PRIMARY_SOURCE_SIMPLE")

class PartialExactMatchPrimarySourceSimpleStrategy(ResolutionStrategy):
    """
    Handles cases with a single 'PartialExact' match from the primary source.
    Often used when only the genus part of a species name matches.
    Accepts the classification path from the result without additional validation.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager",
        profiles_checked_log: Optional[List[str]] = None
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Single PartialExact match from primary source.
        Takes the classification path as provided.
        """
        # Profile condition checks

        # 1. Has response and exactly one result?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 1):
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Needs exactly one result.")
            return None  # Need exactly one result

        result: ResultData = attempt.gnverifier_response.results[0]

        # 2. Overall Match type 'PartialExact'?
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "PartialExact"):
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Match type is not 'PartialExact'.")
            return None

        # 3. Check if from primary source
        primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
        primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]

        if result.data_source_id != primary_source_id:
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Result not from primary source.")
            return None

        # Profile matched
        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Profile matched. "
                     f"PartialExact match: '{result.matched_name}' for query '{attempt.query_term}'")

        # Extract classification from the result
        try:
            resolved_classification = self._extract_classification(result)
            if not resolved_classification:
                logger.warning(f"[{STRATEGY_NAME}] {attempt.key}: Classification extraction yielded empty result. Failing.")
                return self._create_failed_attempt(
                    attempt, manager, 
                    reason="Classification extraction failed", 
                    error_msg="Extracted empty path from partial match result", 
                    profiles_checked_log=profiles_checked_log
                )
        except Exception as e:
            logger.error(f"[{STRATEGY_NAME}] {attempt.key}: Error extracting classification: {e}", exc_info=True)
            return self._create_failed_attempt(
                attempt, manager, 
                reason="Classification extraction failed", 
                error_msg=str(e), 
                profiles_checked_log=profiles_checked_log
            )

        # Log what was matched
        matched_term = result.matched_canonical_simple
        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Matched on term: '{matched_term}'")
        
        # Find which part of the query was matched
        matched_level = None
        for field in TAXONOMIC_RANKS:
            value = getattr(entry_group, field)
            if value and matched_term in value:
                matched_level = field
                break
                
        # Prepare Metadata
        previous_metadata = attempt.metadata or {}
        profile_specific_metadata = {
            'matched_term': matched_term,
            'matched_level': matched_level,
            'matched_name': result.matched_name,
            'current_name': result.current_name,
            'taxonomic_status': result.taxonomic_status,
            'is_synonym': result.is_synonym
        }

        final_metadata = previous_metadata.copy()
        final_metadata.update(profile_specific_metadata)
        if profiles_checked_log:
            final_metadata['profiles_checked'] = profiles_checked_log

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=SUCCESS_STATUS,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=resolved_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata=final_metadata
        )
        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Applied, created final attempt {final_attempt.key}")
        return final_attempt

# Expose for registration
strategy_instance = PartialExactMatchPrimarySourceSimpleStrategy()
check_and_resolve = strategy_instance.check_and_resolve
