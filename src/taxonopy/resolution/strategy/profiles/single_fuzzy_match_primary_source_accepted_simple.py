import logging
from typing import Optional, TYPE_CHECKING, List, Dict

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE

from .profile_logging import setup_profile_logging
_PROFILE_DEBUG_OVERRIDE_ = False  # Set to True for debugging
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "SingleFuzzyMatchPrimarySourceAcceptedSimple"
# Use the new status if you added it
SUCCESS_STATUS = getattr(ResolutionStatus, "SINGLE_FUZZY_MATCH_PRIMARY_SOURCE_ACCEPTED_SIMPLE")

class SingleFuzzyMatchPrimarySourceAcceptedSimpleStrategy(ResolutionStrategy):
    """
    Handles cases with a single 'Fuzzy' match from the primary source with 'Accepted' status.
    This covers common cases like spelling variations or gender agreement differences
    where stemEditDistance is 0 (core word matches) but edit distance > 0.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager",
        profiles_checked_log: Optional[List[str]] = None
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Single Fuzzy, Primary Source, Accepted match
        with stemEditDistance of 0.
        """
        # Profile condition checks

        # 1. Has response and exactly one result?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 1):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Does not have exactly one result.")
            return None

        result: ResultData = attempt.gnverifier_response.results[0]

        # 2. Top-level Match type 'Fuzzy'?
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "Fuzzy"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Match type is not 'Fuzzy'.")
            return None

        # 3. Check if result is from primary source
        primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
        primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]

        if result.data_source_id != primary_source_id:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: "
                         f"Result not from primary source ({result.data_source_id} ≠ {primary_source_id}).")
            return None

        # 4. Check if result has 'Accepted' status
        if result.taxonomic_status != "Accepted":
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: "
                         f"Result status is not 'Accepted' ({result.taxonomic_status}).")
            return None

        # 5. Preferably stemEditDistance should be 0 (core word matches)
        # But not enforcing this check strictly to handle more cases
        if hasattr(result, 'stem_edit_distance') and result.stem_edit_distance > 0:
            logger.debug(f"Profile {STRATEGY_NAME} note on attempt {attempt.key}: "
                         f"stemEditDistance > 0 ({result.stem_edit_distance}), but proceeding anyway.")

        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. "
                     f"Fuzzy match: '{attempt.query_term}' → '{result.matched_name}'")

        # Action: Extract classification from the result
        try:
            resolved_classification = self._extract_classification(result)
            if not resolved_classification:
                logger.warning(f"[{STRATEGY_NAME}] {attempt.key}: Classification extraction yielded empty result. Failing.")
                return self._create_failed_attempt(
                    attempt, manager, 
                    reason="Classification extraction failed", 
                    error_msg="Extracted empty path from fuzzy match result", 
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

        # Prepare Metadata
        previous_metadata = attempt.metadata or {}
        profile_specific_metadata = {
            'fuzzy_matched_name': result.matched_name,
            'edit_distance': result.edit_distance,
            'stem_edit_distance': getattr(result, 'stem_edit_distance', None)
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
strategy_instance = SingleFuzzyMatchPrimarySourceAcceptedSimpleStrategy()
check_and_resolve = strategy_instance.check_and_resolve
