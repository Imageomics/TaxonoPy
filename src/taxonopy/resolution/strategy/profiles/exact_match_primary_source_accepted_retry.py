import logging
from typing import Optional, TYPE_CHECKING, Dict

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE, TAXONOMIC_RANKS

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ExactMatchPrimarySourceAcceptedRetry"

class ExactMatchPrimarySourceAcceptedRetryStrategy(ResolutionStrategy):
    """
    Handles cases where a RETRY query (using a less specific term than the
    original EntryGroupRef) results in a single, exact, accepted match from
    the primary source, and the result path matches the input path UP TO
    the rank of the query term used.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks for the specific profile conditions for a successful retry match.
        """
        # Profile condition checks

        # 0. Is this actually a retry attempt?
        #    ResolutionAttemptManager ely on the order in CLASSIFICATION_CASES, but explicit check adds safety.
        if not attempt.is_retry:
            logger.debug(f"Attempt {attempt.key} is not a retry attempt. Skipping profile check for {STRATEGY_NAME}.")
            return None # This profile only handles results from retries

        # 1. Has response and exactly one result?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 1):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Attempt does not have exactly one result.")
            return None

        result: ResultData = attempt.gnverifier_response.results[0]

        # 2. Match type 'Exact'?
        if not (result.match_type and isinstance(result.match_type, MatchType) and result.match_type.root == "Exact"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result is not an 'Exact' match.")
            return None

        # 3. Status 'Accepted'?
        if result.taxonomic_status != "Accepted":
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result is not 'Accepted' status.")
            return None

        # 4. Uses data from the primary data source?
        try:
            primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
        except StopIteration:
            logger.error(f"Cannot check primary source for {STRATEGY_NAME}: DATA_SOURCE_PRECEDENCE is empty.")
             # Fail the attempt directly here if config is bad
            return self._create_failed_attempt(attempt, manager, reason="Configuration Error", error_msg="DATA_SOURCE_PRECEDENCE is empty")

        if result.data_source_id != primary_source_id:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result does not use the primary data source.")
            return None

        # 5. Canonical form matches the specific query term used in THIS attempt?
        #    Unlike the initial profile,  don't compare to entry_group.most_specific_term
        if not (result.matched_canonical_simple and
                result.matched_canonical_simple == attempt.query_term):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result canonical '{result.matched_canonical_simple}' doesn't match query term '{attempt.query_term}'.")
            return None

        # 6. Result classification path matches input path up to the query rank?
        try:
            expected_classification = self._get_expected_classification(entry_group)
            result_classification = self._extract_classification(result)
        except Exception as e:
            logger.error(f"Attempt {attempt.key}: Error extracting classification for {STRATEGY_NAME}: {e}")
            return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg=str(e))

        # 7. Partial path comparison
        if not self._compare_partial_paths(expected_classification, result_classification, attempt.query_rank):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result classification does not match input path up to query rank.")
            return None

        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}.")

        # Action: Filter the classification based on the attempt's query rank
        filtered_resolved_classification = self._filter_classification_by_rank(
            result_classification, attempt.query_rank
        )
        logger.debug(f"Filtered classification for attempt {attempt.key} (up to rank {attempt.query_rank}): {filtered_resolved_classification}")


        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_RETRY,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=filtered_resolved_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={}
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}")
        return final_attempt

    def _compare_partial_paths(self, expected_path: Dict[str, str], result_path: Dict[str, str], max_rank: Optional[str]) -> bool:
        """
        Checks if the result_path matches the expected_path up to the specified max_rank.
        Uses TAXONOMIC_RANKS to determine the order for comparison.
        """
        if not expected_path or max_rank is None:
             # If no expected path or no rank to compare up to, consider it not a match for this profile's intent
             return False

        try:
            # Find the index of the rank we need to compare up to
            cutoff_rank_index = TAXONOMIC_RANKS.index(max_rank if max_rank != 'class' else 'class_')
        except ValueError:
            logger.warning(f"Rank '{max_rank}' used in query attempt not found in standard TAXONOMIC_RANKS. Cannot perform partial path comparison.")
            return False # Cannot compare if rank is unknown

        # Iterate through ranks from kingdom up to max_rank
        for i in range(cutoff_rank_index + 1):
            current_rank_field = TAXONOMIC_RANKS[i]
            expected_term = expected_path.get(current_rank_field)
            result_term = result_path.get(current_rank_field)

            # If the expected path has a term for this rank, it MUST match in the result path
            if expected_term is not None and expected_term != result_term:
                return False # Mismatch found

        return True # All ranks up to cutoff_rank matched


# Expose for registration
strategy_instance = ExactMatchPrimarySourceAcceptedRetryStrategy()
check_and_resolve = strategy_instance.check_and_resolve
