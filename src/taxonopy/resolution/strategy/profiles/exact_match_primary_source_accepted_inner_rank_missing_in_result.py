import logging
from typing import Optional, TYPE_CHECKING, Dict, Set

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    QueryParameters,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE, TAXONOMIC_RANKS
from taxonopy.query.planner import plan_retry_query

from .profile_logging import setup_profile_logging
# Set to True in the specific file(s) you want to debug
_PROFILE_DEBUG_OVERRIDE_ = True
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ExactMatchPrimarySourceAcceptedInnerRankMissingInResult"

class ExactMatchPrimarySourceAcceptedInnerRankMissingInResultStrategy(ResolutionStrategy):
    """
    Handles cases with a single 'Exact', 'Accepted' match from the PRIMARY source,
    where the result's classification path is missing one or more expected ranks
    compared to the input EntryGroupRef hierarchy up to the level of the matched term.
    Triggers a retry.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Single Exact, Accepted, PRIMARY Source match where result path
        is missing expected rank(s) compared to input path up to query rank. Triggers retry.
        """

        # Profile condition checks

        # 1. Single Result?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 1):
            # Log carefully, avoiding len() on None
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: "
                            f"Response exists: {bool(attempt.gnverifier_response)}, "
                            f"Results list exists: {attempt.gnverifier_response.results is not None}, "
                            f"Result count: {len(attempt.gnverifier_response.results) if attempt.gnverifier_response.results else 'N/A (None)'}")   
            return None

        # Match type 'Exact'?
        result: ResultData = attempt.gnverifier_response.results[0]
        # Check top-level match type first
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "Exact"): 
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Match type is not 'Exact'.")
            return None

        # Result Status 'Accepted'?
        if result.taxonomic_status != "Accepted": 
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result status is not 'Accepted'.")
            return None

        # 2. Primary source only?
        try:
            primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
            primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]
        except (IndexError, KeyError):
            logger.critical(f"PROFILE {STRATEGY_NAME} ERROR on attempt {attempt.key}: Could not determine primary_source_id from DATA_SOURCE_PRECEDENCE.")
            return self._create_failed_attempt(attempt, manager, reason="Config Error", error_msg="Cannot determine primary source ID")


        if result.data_source_id != primary_source_id:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result source ID '{result.data_source_id}' does not match required primary source ID '{primary_source_id}'.")
            return None

        # 3. Canonical Match query term?
        if not (result.matched_canonical_simple and
                result.matched_canonical_simple == attempt.query_term):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Canonical match query term '{result.matched_canonical_simple}' does not match input '{attempt.query_term}'.")
            return None

        # 4. Extract Classifications & Determine Query Rank in Input
        try:
            expected_classification = self._get_expected_classification(entry_group)
            result_classification = self._extract_classification(result)
            # Determine the highest rank of the query term *in the input*
            input_term_highest_rank = self._get_rank_of_term(attempt.query_term, entry_group)
        except Exception as e:
            logger.error(f"Attempt {attempt.key}: Error during classification/rank extraction for {STRATEGY_NAME}: {e}")
            return self._create_failed_attempt(attempt, manager, reason="Classification/Rank extraction failed", error_msg=str(e))

        if input_term_highest_rank is None:
            logger.warning(f"Profile {STRATEGY_NAME} cannot apply to attempt {attempt.key}: Query term '{attempt.query_term}' not found in input EntryGroupRef ranks.")
            return None

        # 5. Missing Rank Check (Relative to Input up to Query Rank)
        missing_rank_found = False
        try:
            term_rank_index = TAXONOMIC_RANKS.index(input_term_highest_rank)

            # Check ranks from kingdom up to the term's rank
            for i in range(term_rank_index + 1):
                rank_field = TAXONOMIC_RANKS[i]
                # If the input expected a rank here, but the result doesn't have it...
                if rank_field in expected_classification and rank_field not in result_classification:
                    logger.debug(f"Profile {STRATEGY_NAME} match on attempt {attempt.key}: Input expected rank '{rank_field}', but result classification missing it.")
                    missing_rank_found = True
                    break # Found a missing rank, no need to check further
        except ValueError:
             logger.warning(f"Rank '{input_term_highest_rank}' not found in TAXONOMIC_RANKS during missing rank check for attempt {attempt.key}.")
             return None # Cannot proceed if rank invalid
        except Exception as e:
            logger.error(f"Unexpected error during missing rank check for attempt {attempt.key}: {e}", exc_info=True)
            return self._create_failed_attempt(attempt, manager, reason="Missing rank check failed", error_msg=str(e))


        if not missing_rank_found:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: No expected ranks were found missing in the result classification up to rank '{input_term_highest_rank}'.")
            return None # Profile doesn't match if no expected ranks are missing

        # Profile Matched: Inconsistency detected (missing rank), trigger retry
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. Missing inner rank detected in primary source result, planning retry...")

        # Action: Plan the next retry
        next_query_params: Optional[QueryParameters] = None
        try:
            next_query_params = plan_retry_query(attempt, entry_group, manager)
        except ValueError as e: # Catch specific data inconsistency error from planner
            logger.error(f"Error planning retry for attempt {attempt.key} (triggered by {STRATEGY_NAME}): {e}. Failing this attempt.")
            return self._create_failed_attempt(attempt, manager, reason="Retry planning failed (data inconsistency)", error_msg=str(e))
        except Exception as e: # Catch other planner errors
            logger.error(f"Unexpected error during retry planning for attempt {attempt.key} (triggered by {STRATEGY_NAME}): {e}", exc_info=True)
            return self._create_failed_attempt(attempt, manager, reason="Retry planner exception", error_msg=str(e))

        # Create the next attempt based on retry plan
        if next_query_params:
            retry_scheduled_attempt = manager.create_attempt(
                entry_group_key=attempt.entry_group_key,
                query_term=attempt.query_term, # Keep original query info for context
                query_rank=attempt.query_rank,
                data_source_id=attempt.data_source_id,
                status=ResolutionStatus.RETRY_SCHEDULED,
                gnverifier_response=None,
                resolution_strategy_name=STRATEGY_NAME,
                scheduled_query_params=next_query_params,
                metadata={'reason_for_retry': 'Missing inner rank in primary source result'}
            )
            logger.debug(f"Applied {STRATEGY_NAME}: Created RETRY_SCHEDULED attempt {retry_scheduled_attempt.key} for original {attempt.key}. Next query: {next_query_params}")
            logger.debug(f"DEBUGG {STRATEGY_NAME} next attempt: {retry_scheduled_attempt}")
            return retry_scheduled_attempt
        else:
            # Retries exhausted
            exhausted_attempt = manager.create_attempt(
                entry_group_key=attempt.entry_group_key,
                query_term=attempt.query_term, query_rank=attempt.query_rank, data_source_id=attempt.data_source_id,
                status=ResolutionStatus.NO_MATCH_RETRIES_EXHAUSTED, # Or a more specific FAILED status?
                gnverifier_response=attempt.gnverifier_response,
                resolution_strategy_name=STRATEGY_NAME,
                failure_reason="Retries exhausted after detecting primary source inconsistency (missing rank).",
                metadata={'reason_for_retry': 'Missing inner rank in primary source result'}
            )
            logger.debug(f"Applied {STRATEGY_NAME}: Created NO_MATCH_RETRIES_EXHAUSTED attempt {exhausted_attempt.key} for original {attempt.key}.")
            return exhausted_attempt


# Expose for registration
strategy_instance = ExactMatchPrimarySourceAcceptedInnerRankMissingInResultStrategy()
check_and_resolve = strategy_instance.check_and_resolve
