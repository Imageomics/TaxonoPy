import logging
from typing import Optional, TYPE_CHECKING, List

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

STRATEGY_NAME = "ExactMatchPrimarySourceAcceptedAuthorDisambiguation"
# Use the new status if you added it
SUCCESS_STATUS = getattr(ResolutionStatus, "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_AUTHOR_DISAMBIGUATION")

class ExactMatchPrimarySourceAcceptedAuthorDisambiguationStrategy(ResolutionStrategy):
    """
    Handles cases with multiple 'Exact', 'Accepted' matches from the primary source
    that have identical canonical names but different authors.
    Selects the result whose full name (with author) exactly matches the query term.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager",
        profiles_checked_log: Optional[List[str]] = None
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Multiple Exact, Accepted, Primary Source matches with identical
        canonical names but different authors. Selects result with matching full name.
        """
        # Profile condition checks

        # 1. Has response and at least 2 results?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) >= 2):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Does not have at least 2 results.")
            return None

        all_results: List[ResultData] = attempt.gnverifier_response.results

        # 2. Overall Match type 'Exact'?
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "Exact"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Match type is not 'Exact'.")
            return None

        # 3. Filter results to Primary Source with 'Accepted' status
        primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
        primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]

        accepted_primary_results: List[ResultData] = []
        for res in all_results:
            # Check for primary source results with Accepted status
            if (res.data_source_id == primary_source_id and 
                res.taxonomic_status == "Accepted"):
                accepted_primary_results.append(res)

        # Need at least 2 accepted results from primary source
        if len(accepted_primary_results) < 2:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: "
                         f"Fewer than 2 accepted primary source results ({len(accepted_primary_results)}).")
            return None

        # 4. Check if they all have identical canonicals
        canonical_name = accepted_primary_results[0].matched_canonical_simple
        if not all(res.matched_canonical_simple == canonical_name for res in accepted_primary_results):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: "
                         f"Not all results have the same canonical name.")
            return None

        # 5. Find the result whose full matched name matches the query term
        matching_result = None
        for res in accepted_primary_results:
            # Compare the full name with author
            if res.matched_name == attempt.query_term:
                matching_result = res
                break

        if not matching_result:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: "
                         f"No result with full name matching query term '{attempt.query_term}'.")
            return None

        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. "
                     f"Selected result with matching author: {matching_result.matched_name}")

        # Action: Extract classification from the matching result
        try:
            resolved_classification = self._extract_classification(matching_result)
            if not resolved_classification:
                logger.warning(f"[{STRATEGY_NAME}] {attempt.key}: Classification extraction yielded empty result. Failing.")
                return self._create_failed_attempt(
                    attempt, manager, 
                    reason="Classification extraction failed", 
                    error_msg="Extracted empty path from matching result", 
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
            'matched_result_id': matching_result.record_id,
            'matched_full_name': matching_result.matched_name,
            'author_disambiguation': 'true'
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
strategy_instance = ExactMatchPrimarySourceAcceptedAuthorDisambiguationStrategy()
check_and_resolve = strategy_instance.check_and_resolve
