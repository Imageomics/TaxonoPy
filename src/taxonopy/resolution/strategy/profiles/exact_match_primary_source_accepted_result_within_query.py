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

from .profile_logging import setup_profile_logging
# Set to True to enable debug logging JUST for this profile
_PROFILE_DEBUG_OVERRIDE_ = False
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ExactMatchPrimarySourceAcceptedResultWithinQuery"

class ExactMatchPrimarySourceAcceptedResultWithinQueryStrategy(ResolutionStrategy):
    """
    Handles cases with a single 'Exact', 'Accepted' match from the primary source,
    where the result's classification matches the input up to a parent rank,
    and the result classification terminates at that parent rank.
    (e.g., Input query "Aus bus bus", result matches "Aus bus" at genus level).
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Single Exact, Accepted, Primary Source match where the
        result classification is a valid higher-rank match to the input query.
        """
        # Profile condition checks

        # 1. Has response and exactly one result?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 1):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Does not have exactly one result.")
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

        # 4. Primary Source?
        try:
            primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
        except StopIteration:
             logger.error(f"Cannot check primary source for {STRATEGY_NAME}: DATA_SOURCE_PRECEDENCE is empty.")
             return self._create_failed_attempt(attempt, manager, reason="Config Error", error_msg="No primary source")

        if result.data_source_id != primary_source_id:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Source ID {result.data_source_id} is not primary ({primary_source_id}).")
            return None

        # --- Core Logic ---
        try:
            # 5. Extract classifications
            expected_classification = self._get_expected_classification(entry_group)
            result_classification = self._extract_classification(result)

            # 6. Get terms and ranks
            query_term = attempt.query_term
            matched_term = result.matched_canonical_simple
            if not query_term or not matched_term:
                logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Query term or matched term is missing.")
                return None

            # 7. Does the query term start with the matched term (and they are not identical)?
            #    This identifies cases like query="Aus bus bus", matched="Aus bus"
            if not query_term.startswith(matched_term) or query_term == matched_term:
                logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Query term '{query_term}' does not start with (or is identical to) matched term '{matched_term}'.")
                return None

            # 8. Find the rank of the matched term in the result's classification
            result_match_rank_field = self._get_rank_of_term(matched_term, result_classification)
            if result_match_rank_field is None:
                logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Matched term '{matched_term}' not found in result classification ranks: {result_classification}.")
                return None

            # 9. Check path consistency up to the matched rank
            #    Does the result path match the input path up to the level where the result matched?
            if not self._compare_paths_up_to_rank(expected_classification, result_classification, result_match_rank_field):
                logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result path does not match input path up to rank '{result_match_rank_field}'.")
                return None

            # 10. Does the result classification terminate at the matched rank?
            #     (i.e., no ranks below the matched rank are present in the result)
            highest_rank_in_result = self._get_highest_rank_in_classification(result_classification)
            if highest_rank_in_result != result_match_rank_field:
                logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result classification terminates at '{highest_rank_in_result}', but expected termination at matched rank '{result_match_rank_field}'.")
                return None

        except Exception as e:
             logger.error(f"Attempt {attempt.key}: Error during core logic for {STRATEGY_NAME}: {e}", exc_info=True)
             return self._create_failed_attempt(attempt, manager, reason="Core logic failed", error_msg=str(e))

        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. Result classification accepted.")

        # Action: Use the classification from the result (which is already verified)
        final_classification = result_classification

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_RESULT_WITHIN_QUERY,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=final_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={'matched_term': matched_term, 'matched_rank': result_match_rank_field}
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}")
        return final_attempt

# Expose for registration
strategy_instance = ExactMatchPrimarySourceAcceptedResultWithinQueryStrategy()
check_and_resolve = strategy_instance.check_and_resolve
