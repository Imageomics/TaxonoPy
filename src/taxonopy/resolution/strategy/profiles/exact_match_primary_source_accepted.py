import logging
from typing import Optional, TYPE_CHECKING

from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE
from taxonopy.resolution.strategy.base import ResolutionStrategy

from .profile_logging import setup_profile_logging
# Set to True in the specific file(s) you want to debug
_PROFILE_DEBUG_OVERRIDE_ = False
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ExactMatchPrimarySourceAccepted"

class ExactMatchPrimarySourceAcceptedStrategy(ResolutionStrategy):
    """
    Applies the ExactMatchPrimarySourceAccepted profile.
    Inherits _extract_classification and _get_expected_classification from ResolutionStrategy.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks for the specific profile: Single, Exact, Accepted, primary source match
        where classification and query term align with input group.
        If matched, creates and returns the final EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED attempt.
        Returns None otherwise.
        """
        # Profile condition checks
        # 1. Has response and exactly one result?
        if not (
            attempt.gnverifier_response and
            attempt.gnverifier_response.results is not None and
            len(attempt.gnverifier_response.results) == 1
        ):
            results_list = attempt.gnverifier_response.results if attempt.gnverifier_response else None
            result_count = len(results_list) if results_list is not None else "N/A (None)"
            # Log carefully, avoiding len() on None
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: "
                         f"Response exists: {bool(attempt.gnverifier_response)}, "
                         f"Results list exists: {results_list is not None}, "
                         f"Result count: {result_count}")
            return None # Profile mismatch

        result: ResultData = attempt.gnverifier_response.results[0]

        # 2. Match type 'Exact'?
        if not (result.match_type and
                isinstance(result.match_type, MatchType) and
                result.match_type.root == "Exact"):
            logger.debug(f"Checking if attempt {attempt.key} is 'Exact'")
            logger.debug(f"Attempt {attempt.key} match type: {result.match_type}")
            return None # Profile mismatch

        # 3. Status 'Accepted'?
        if result.taxonomic_status != "Accepted":
            logger.debug(f"Checking if attempt {attempt.key} is 'Accepted'")
            logger.debug(f"Attempt {attempt.key} taxonomic status: {result.taxonomic_status}")
            return None # Profile mismatch

        # 4. Uses data from the primary data source?
        primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
        primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]
        if result.data_source_id != primary_source_id:
            logger.debug(f"Checking if attempt {attempt.key} uses primary data source ({primary_source_key}, {primary_source_id})")
            logger.debug(f"Attempt {attempt.key} data source ID: {result.data_source_id}")
            return None # Profile mismatch

        # 5. Classification matches input?
        expected_classification = self._get_expected_classification(entry_group)

        try:
            result_classification = self._extract_classification(result)
        except Exception as e:
            logger.error(f"Attempt {attempt.key}: Error extracting classification for {STRATEGY_NAME}: {e}")
            # Fail the attempt if extraction error occurs within the profile logic
            return manager.create_failed_attempt(
                attempt,
                manager,
                reason="Classification extraction failed", error_msg=str(e))
        match = True
        for rank_field, expected_value in expected_classification.items():
            result_value = result_classification.get(rank_field)

            if rank_field == 'kingdom':
                logger.debug(f"  Comparing Kingdom: Input='{expected_value}' vs Result='{result_value}'")

                # Direct Exact Match Check:
                if expected_value == result_value:
                    logger.debug("    Kingdoms match directly. PASS.")
                    continue # Move to next rank

                # If direct match failed, check synonyms only if input is a known synonym
                canonical_input_kingdom = ResolutionStrategy.get_canonical_kingdom(expected_value)
                canonical_result_kingdom = ResolutionStrategy.get_canonical_kingdom(result_value) # Still useful for logging/potential future checks

                # Check if the original input value was found as a synonym key and if the canonical input matches the canonical result
                is_input_a_synonym = False
                if expected_value and canonical_input_kingdom != expected_value.strip(): # Check if canonicalization actually changed the input
                     # This implies the original input value was found in a synonym set
                     is_input_a_synonym = True

                if is_input_a_synonym and canonical_input_kingdom == canonical_result_kingdom:
                     # Input was a known synonym, and its canonical form matches the result's canonical form (or direct result value if result isn't in synonyms)
                     logger.debug(f"    Input kingdom ('{expected_value}') is synonym for '{canonical_input_kingdom}', which matches result kingdom ('{result_value}' -> '{canonical_result_kingdom}'). PASS.")
                     continue # Treat as a match

                # 3. If none of the above passed, it's a mismatch for this profile
                logger.debug(f"    Kingdom Mismatch: Direct match failed, and input ('{expected_value}') is not a recognized synonym matching the result ('{result_value}').")
                match = False
                break
            else:
                # Direct comparison for other ranks (same as before)
                logger.debug(f"  Comparing Rank '{rank_field}': Input='{expected_value}' vs Result='{result_value}'")
                if result_value != expected_value:
                    logger.debug("  Rank Mismatch: Values differ.")
                    match = False
                    break

        if not match:
             logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Classification mismatch detected.")
             return None # Profile mismatch
        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Passed classification comparison.")

        # Compare classifications (only ranks present in input)
        match = True
        for rank_field, expected_value in expected_classification.items():
            if result_classification.get(rank_field) != expected_value:
                logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Classification mismatch on rank '{rank_field}'. Expected '{expected_value}', Got '{result_classification.get(rank_field)}'.")
                match = False
                break
        if not match:
             return None # Profile mismatch

        # 6. Query term matches most specific input term?
        if attempt.query_term != entry_group.most_specific_term:
            logger.debug(f"Checking if attempt {attempt.key} query term matches input term")
            logger.debug(f"Attempt {attempt.key} query term: {attempt.query_term}, input term: {entry_group.most_specific_term}")
            return None # Profile mismatch
            
        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}.")

        # Action

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=result_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={}
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}")
        return final_attempt

# Expose for registration
strategy_instance = ExactMatchPrimarySourceAcceptedStrategy()
check_and_resolve = strategy_instance.check_and_resolve
