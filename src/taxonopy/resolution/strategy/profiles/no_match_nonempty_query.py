import sys

import logging
from typing import Optional, TYPE_CHECKING

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    QueryParameters,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import MatchType
from taxonopy.query.planner import plan_retry_query

from .profile_logging import setup_profile_logging
# Set to True in the specific file(s) you want to debug
_PROFILE_DEBUG_OVERRIDE_ = False
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "NoMatchNonEmptyQuery"

class NoMatchNonEmptyQueryStrategy(ResolutionStrategy):
    """
    Handles attempts where the query was non-empty but yielded no match or failed.
    Initiates retry planning.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks for the profile: Non-empty query resulted in NoMatch or failure.
        If matched, plans a retry. Creates RETRY_SCHEDULED attempt if a plan exists,
        or NO_MATCH_RETRIES_EXHAUSTED if retries are exhausted. Handles planner errors.
        Returns the newly created attempt, or None if this profile doesn't apply.
        """
        # Profile condition checks
        # -- targeted for debugging --
        if attempt.query_term and (attempt.query_term == "Diapriinae" or attempt.query_term == "Diapriidae"):
            print(f"Query term: {attempt.query_term}")
            print(f"Query rank: {attempt.query_rank}")
            print(f"Data source ID: {attempt.data_source_id}")
            print(f"GNVerifier response: {attempt.gnverifier_response}")

        # 1. Was the query term non-empty?
        if not attempt.query_term or attempt.query_term.strip() == "":
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Query term is empty.")
            # -- targeted for debugging --
            if attempt.query_term and (attempt.query_term == "Diapriinae" or attempt.query_term == "Diapriidae"):
                print(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key} (query term: {attempt.query_term}): Query term is empty.")
            return None # Handled by empty_input profile

        # 2. Did the response indicate NoMatch or Failure?
        is_no_match_or_failure = False
        if not attempt.gnverifier_response:
            # Case A: Query execution failed (no response object)
            logger.debug(f"Profile {STRATEGY_NAME} matching attempt {attempt.key} (query term: {attempt.query_term}): No GNVerifier response (likely execution error).")
            is_no_match_or_failure = True
            # -- targeted for debugging --
            if attempt.query_term and (attempt.query_term == "Diapriinae" or attempt.query_term == "Diapriidae"):
                 print(f"Profile {STRATEGY_NAME} matching attempt {attempt.key} (query term: {attempt.query_term}): No GNVerifier response (likely execution error).")
        elif attempt.gnverifier_response.match_type and isinstance(attempt.gnverifier_response.match_type, MatchType) and attempt.gnverifier_response.match_type.root == "NoMatch":
            # Case B: Explicit "NoMatch" type
            # -- targeted for debugging --
            if attempt.query_term and (attempt.query_term == "Diapriinae" or attempt.query_term == "Diapriidae"):
                print(f"Profile {STRATEGY_NAME} matching attempt {attempt.key} (query term: {attempt.query_term}): Explicit 'NoMatch' type found.")
            logger.debug(f"Profile {STRATEGY_NAME} matching attempt {attempt.key}: Explicit 'NoMatch' type found.")
            is_no_match_or_failure = True
        elif not attempt.gnverifier_response.results:
            # Case C: Response exists but no results list (implicit no match)
            # -- targeted for debugging --
            if attempt.query_term and (attempt.query_term == "Diapriinae" or attempt.query_term == "Diapriidae"):
                print(f"Profile {STRATEGY_NAME} matching attempt {attempt.key} (query term: {attempt.query_term}): GNVerifier response has no results list.")
            logger.debug(f"Profile {STRATEGY_NAME} matching attempt {attempt.key}: GNVerifier response has no results list.")
            is_no_match_or_failure = True

        # If none of the no-match/failure conditions are met, this profile doesn't apply
        if not is_no_match_or_failure:
            # -- targeted for debugging --
            if attempt.query_term and (attempt.query_term == "Diapriinae" or attempt.query_term == "Diapriidae"):
                print(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key} (query term: {attempt.query_term}): No match or failure found.")
            # This attempt might have results that just didn't match other success profiles.
            # It will eventually be marked FAILED by the manager if no other profile handles it.
            return None
            
        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. Planning retry...")
        # -- targeted for debugging --
        if attempt.query_term and (attempt.query_term == "Diapriinae" or attempt.query_term == "Diapriidae"):
            print(f"Attempt {attempt.key} (query term: {attempt.query_term}) matched profile for {STRATEGY_NAME}. Planning retry...")

        # Action: Plan the next retry
        next_query_params: Optional[QueryParameters] = None
        try:
            # Call the planner function
            next_query_params = plan_retry_query(attempt, entry_group, manager)
        except ValueError as e:
            # Handle data inconsistency error from planner
            logger.error(f"Error planning retry for attempt {attempt.key}: {e}. Failing this attempt.")
            failed_attempt = self._create_failed_attempt(attempt, manager, reason="Retry planning failed (data inconsistency)", error_msg=str(e))
            return failed_attempt # Return the FAILED attempt
        except Exception as e:
            # Handle unexpected errors during planning
            logger.error(f"Unexpected error during retry planning for attempt {attempt.key}: {e}", exc_info=True)
            failed_attempt = self._create_failed_attempt(attempt, manager, reason="Retry planner exception", error_msg=str(e))
            return failed_attempt
        # print(f"Next query params: {next_query_params}")
        # Create the next attempt based on retry plan
        if next_query_params:
            retry_scheduled_attempt = manager.create_attempt(
                entry_group_key=attempt.entry_group_key,
                query_term=attempt.query_term,
                query_rank=attempt.query_rank,
                data_source_id=attempt.data_source_id,
                status=ResolutionStatus.RETRY_SCHEDULED,
                gnverifier_response=attempt.gnverifier_response,
                resolved_classification=None,
                error=attempt.error,
                resolution_strategy_name=STRATEGY_NAME,
                failure_reason=None,
                scheduled_query_params=next_query_params,
                metadata={}
            )
            logger.debug(f"Applied {STRATEGY_NAME}: Created RETRY_SCHEDULED attempt {retry_scheduled_attempt.key} for original {attempt.key}. Next query: {next_query_params}")
            return retry_scheduled_attempt
        else:
            # Retries exhausted, create NO_MATCH_RETRIES_EXHAUSTED attempt
            exhausted_attempt = manager.create_attempt(
                entry_group_key=attempt.entry_group_key,
                query_term=attempt.query_term,
                query_rank=attempt.query_rank,
                data_source_id=attempt.data_source_id,
                status=ResolutionStatus.NO_MATCH_RETRIES_EXHAUSTED,
                gnverifier_response=attempt.gnverifier_response, # Preserve last response
                resolved_classification=None,
                error=attempt.error, # Preserve original error if any
                resolution_strategy_name=STRATEGY_NAME, # Strategy that determined exhaustion
                failure_reason="No match found after exhausting all retry combinations.",
                metadata={}
            )
            logger.debug(f"Applied {STRATEGY_NAME}: Created NO_MATCH_RETRIES_EXHAUSTED attempt {exhausted_attempt.key} for original {attempt.key}.")
            return exhausted_attempt

# Expose for registration
strategy_instance = NoMatchNonEmptyQueryStrategy()
check_and_resolve = strategy_instance.check_and_resolve
