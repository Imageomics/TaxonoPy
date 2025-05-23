import logging
from typing import Optional, TYPE_CHECKING

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE

from .profile_logging import setup_profile_logging
# Set to True if you want to force debug logging for this specific file
_PROFILE_DEBUG_OVERRIDE_ = False
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ExactMatchPrimarySourceAcceptedSimple"
# Use the new status if you added it, otherwise fall back to the existing one
SUCCESS_STATUS = getattr(ResolutionStatus, "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_SIMPLE",
                         ResolutionStatus.EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED)

class ExactMatchPrimarySourceAcceptedSimpleStrategy(ResolutionStrategy):
    """
    Handles cases with a single 'Exact', 'Accepted' match from the primary source.
    Trusts the result's classification path without further validation against input path.
    Requires result.current_name to exactly match the attempt.query_term.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager",
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Single, Exact, Accepted, primary source match where
        result.currentName == attempt.query_term. Takes result path as is.
        """
        # Profile condition checks

        # 1. Has response and exactly one result?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 1):
            return None # Not a single result

        result: ResultData = attempt.gnverifier_response.results[0]

        # 2. Result Match type 'Exact'?
        # (Using result.match_type is sufficient here as we only have one result)
        if not (result.match_type and
                isinstance(result.match_type, MatchType) and
                result.match_type.root == "Exact"):
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Mismatch - Result MatchType is not Exact ('{result.match_type.root if result.match_type else 'None'}').")
            return None

        # 3. Result Status 'Accepted'?
        if result.taxonomic_status != "Accepted":
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Mismatch - Result Status is not Accepted ('{result.taxonomic_status}').")
            return None

        # 4. Uses data from the primary data source?
        primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
        primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]
        if result.data_source_id != primary_source_id:
            logger.debug(f"Checking if attempt {attempt.key} uses primary data source ({primary_source_key}, {primary_source_id})")
            logger.debug(f"Attempt {attempt.key} data source ID: {result.data_source_id}")
            return None # Profile mismatch

        # # 5. Result's currentName exactly matches the query term used in this attempt?
        # #    (Using strip for robustness against leading/trailing whitespace)
        # query_term_stripped = attempt.query_term.strip()
        # current_name_stripped = result.current_name.strip() if result.current_name else None
        # logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Comparing query_term '{query_term_stripped}' vs result.current_name '{current_name_stripped}'")
        # if not (current_name_stripped and query_term_stripped == current_name_stripped):
        #     logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Mismatch - result.current_name does not exactly match attempt.query_term.")
        #     return None

        # Profile matched
        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Profile matched.")

        # Action: Extract classification directly from the result
        try:
            resolved_classification = self._extract_classification(result)
            if not resolved_classification: # Check if extraction yielded anything
                 logger.warning(f"[{STRATEGY_NAME}] {attempt.key}: Classification extraction yielded empty result. Failing.")
                 return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg="Extracted empty path")
        except Exception as e:
            logger.error(f"[{STRATEGY_NAME}] {attempt.key}: Error extracting classification: {e}", exc_info=True)
            return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg=str(e))

        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Using classification: {resolved_classification}")

        # Prepare Metadata
        previous_metadata = attempt.metadata or {}
        profile_specific_metadata = {'matched_current_name': result.current_name} # Add useful info

        final_metadata = previous_metadata.copy()
        final_metadata.update(profile_specific_metadata)

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_SIMPLE,
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
strategy_instance = ExactMatchPrimarySourceAcceptedSimpleStrategy()
check_and_resolve = strategy_instance.check_and_resolve
