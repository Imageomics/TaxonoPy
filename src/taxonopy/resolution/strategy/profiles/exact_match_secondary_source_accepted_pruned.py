import logging
from typing import Optional, TYPE_CHECKING, Dict, Set

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE, TAXONOMIC_RANKS

from .profile_logging import setup_profile_logging
# Set to True in the specific file(s) you want to debug
_PROFILE_DEBUG_OVERRIDE_ = True
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ExactMatchSecondarySourceAcceptedPruned"

class ExactMatchSecondarySourceAcceptedPrunedStrategy(ResolutionStrategy):
    """
    Handles successful 'Exact', 'Accepted' matches resulting from a RETRY query
    to a SECONDARY data source. It prunes the result classification to standard ranks
    and validates the path against the input EntryGroupRef up to the relevant rank.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Single Exact, Accepted match from a known secondary source
        (on a retry attempt), where the pruned result path matches input context.
        """
        # Profile condition checks

        # 0. Is this a retry attempt? Important for context.
        if not attempt.is_retry:
            # This profile only handles results from retries.
            logger.debug(f"Profile {STRATEGY_NAME} cannot apply to attempt {attempt.key}: Not a retry attempt.")
            return None

        # 1. Has response and exactly one result?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 1):
            # Log carefully, avoiding len() on None
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: "
                            f"Response exists: {bool(attempt.gnverifier_response)}, "    
                            f"Results list exists: {attempt.gnverifier_response.results is not None}, "
                            f"Result count: {len(attempt.gnverifier_response.results) if attempt.gnverifier_response.results else 'N/A (None)'}")
            return None

        result: ResultData = attempt.gnverifier_response.results[0]

        # 2. Top-level Match type 'Exact'?
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "Exact"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Match type is not 'Exact'.")
            return None

        # 3. Result Status 'Accepted'?
        if result.taxonomic_status != "Accepted":
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result status is not 'Accepted'.")
            return None

        # 4. Is it from the secondary source?
        try:
            secondary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[1]
            secondary_source_id = DATA_SOURCE_PRECEDENCE[secondary_source_key]
            if result.data_source_id != secondary_source_id:
                logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Source ID {result.data_source_id} is not secondary ({secondary_source_id}).")
                return None # Must be secondary source
        except IndexError: # out of range?
            logger.error(f"Cannot check source for {STRATEGY_NAME}: DATA_SOURCE_PRECEDENCE is empty.")
            return self._create_failed_attempt(attempt, manager, reason="Config Error", error_msg="DATA_SOURCE_PRECEDENCE empty")        

        # 5. Canonical matches query term used in this attempt?
        if not (result.matched_canonical_simple and
                result.matched_canonical_simple == attempt.query_term):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Canonical match '{result.matched_canonical_simple}' does not match query term '{attempt.query_term}'.")
            return None

        # 6. Path consistency check (using pruned result path)
        try:
            expected_classification = self._get_expected_classification(entry_group)
            # Extract classification (implicitly pruned to standard ranks by base helper)
            result_classification_pruned = self._extract_classification(result)
        except Exception as e:
            logger.error(f"Attempt {attempt.key}: Error extracting classification for {STRATEGY_NAME}: {e}")
            return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg=str(e))

        if not result_classification_pruned:
            logger.warning(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Could not extract standard ranks from result {result.record_id}.")
            return None

        # Find the highest rank in the input where the query term appears
        # This rank determines how far up the hierarchy we need to check for consistency
        input_term_highest_rank = self._get_rank_of_term(attempt.query_term, entry_group)
        if input_term_highest_rank is None:
            logger.warning(f"Profile {STRATEGY_NAME} cannot apply to attempt {attempt.key}: Query term '{attempt.query_term}' not found in input ranks.")
            return None

        # Compare pruned result path with input path up to the relevant rank
        paths_match = self._compare_paths_up_to_rank(expected_classification, result_classification_pruned, input_term_highest_rank)

        if not paths_match:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Path comparison failed.")
            logger.debug(f"--- Input Path (up to {input_term_highest_rank}): { {k: v for k, v in expected_classification.items() if k in TAXONOMIC_RANKS[:TAXONOMIC_RANKS.index(input_term_highest_rank)+1]} }")
            logger.debug(f"--- Pruned Result Path: {result_classification_pruned}")
            return None

        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. Source: {result.data_source_id}, Term: '{attempt.query_term}'")

        # Action: Use the pruned classification extracted earlier.

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id, # Source ID from this attempt (secondary source)
            status=ResolutionStatus.EXACT_MATCH_SECONDARY_SOURCE_ACCEPTED_PRUNED,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=result_classification_pruned,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={'secondary_source_id': result.data_source_id,
                      'secondary_source_title': result.data_source_title_short}
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key} (Retry)")
        return final_attempt

# Expose for registration
strategy_instance = ExactMatchSecondarySourceAcceptedPrunedStrategy()
check_and_resolve = strategy_instance.check_and_resolve
