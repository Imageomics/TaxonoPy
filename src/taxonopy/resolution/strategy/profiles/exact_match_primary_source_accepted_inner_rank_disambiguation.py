import logging
from typing import Optional, TYPE_CHECKING, Dict, Tuple

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE

from .profile_logging import setup_profile_logging
# Set to True in the specific file(s) you want to debug
_PROFILE_DEBUG_OVERRIDE_ = False
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ExactMatchPrimarySourceAcceptedInnerRankDisambiguation"

class ExactMatchPrimarySourceAcceptedInnerRankDisambiguationStrategy(ResolutionStrategy):
    """
    Handles cases with exactly two 'Exact', 'Accepted' matches from the primary source,
    disambiguating based on which result's classification path matches the input EntryGroupRef.
    Inherits helper methods from ResolutionStrategy.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks for the profile: Two Exact, Accepted, Primary Source matches with identical
        canonical simple names matching the query term. Disambiguates using the input hierarchy.
        """
        # Profile condition checks
        
        # 1. Has response and exactly two results?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 2):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Attempt does not have exactly two results.")
            return None # Profile mismatch

        result0: ResultData = attempt.gnverifier_response.results[0]
        result1: ResultData = attempt.gnverifier_response.results[1]

        try:
            expected_classification = self._get_expected_classification(entry_group)
            result0_classification = self._extract_classification(result0)
            result1_classification = self._extract_classification(result1)
        except Exception as e:
            logger.error(f"Attempt {attempt.key}: Error extracting classification for {STRATEGY_NAME}: {e}")
            return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg=str(e))

        # 2. Both match types 'Exact'?
        if not (result0.match_type and isinstance(result0.match_type, MatchType) and result0.match_type.root == "Exact" and
                result1.match_type and isinstance(result1.match_type, MatchType) and result1.match_type.root == "Exact"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Not both results are Exact matches.")
            return None # Profile mismatch

        # 3. Both statuses 'Accepted'?
        if not (result0.taxonomic_status == "Accepted" and result1.taxonomic_status == "Accepted"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Not both results are Accepted.")
            return None # Profile mismatch

        # 4. Both use data from the primary data source?
        primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
        primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]

        if not (result0.data_source_id == primary_source_id and result1.data_source_id == primary_source_id):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Not both results used primary data source {primary_source_key} ({primary_source_id}). "
                         f"Result0 Source: {result0.data_source_id}, Result1 Source: {result1.data_source_id}")
            return None # Profile mismatch

        if not (result0.data_source_id == primary_source_id and result1.data_source_id == primary_source_id):
            return None # Profile mismatch

        # 5. Canonical forms match each other and the query term?
        if not (result0.matched_canonical_simple and
                result0.matched_canonical_simple == result1.matched_canonical_simple and
                result0.matched_canonical_simple == attempt.query_term):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Canonical forms do not match each other or the query term.")
            logger.debug(f"Result0 Canonical: {result0.matched_canonical_simple}, Result1 Canonical: {result1.matched_canonical_simple}, Query Term: {attempt.query_term}")
            return None # Profile mismatch

        # 6. Kingdoms match?
        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Performing kingdom consistency check (robust)...")
        try:
            canonical_input_kingdom = ResolutionStrategy.get_canonical_kingdom(expected_classification.get('kingdom'))
            logger.debug(f"  Input Kingdom: '{expected_classification.get('kingdom')}' -> Canonical: '{canonical_input_kingdom}'")

            # 1. Input kingdom MUST be valid for this profile to apply contextually
            if not canonical_input_kingdom:
                logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Mismatch - Input EntryGroupRef has no valid canonical kingdom. Returning None.")
                return None

            canonical_result0_kingdom = ResolutionStrategy.get_canonical_kingdom(result0_classification.get('kingdom'))
            canonical_result1_kingdom = ResolutionStrategy.get_canonical_kingdom(result1_classification.get('kingdom'))
            logger.debug(f"  Result 0 Kingdom: '{result0_classification.get('kingdom')}' -> Canonical: '{canonical_result0_kingdom}'")
            logger.debug(f"  Result 1 Kingdom: '{result1_classification.get('kingdom')}' -> Canonical: '{canonical_result1_kingdom}'")

            # 2. Check if at least one result matches the valid input kingdom
            #    (Handles cases where one result might lack a kingdom)
            result0_matches = (canonical_result0_kingdom == canonical_input_kingdom)
            result1_matches = (canonical_result1_kingdom == canonical_input_kingdom)

            if not (result0_matches or result1_matches):
                # Neither result's kingdom matches the input kingdom, OR both results lack a valid kingdom.
                logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Mismatch - Neither valid result kingdom ('{canonical_result0_kingdom}', '{canonical_result1_kingdom}') matches the input canonical kingdom ('{canonical_input_kingdom}'). Returning None.")
                return None

            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Passed robust kingdom consistency check.")

        except Exception as e:
            logger.error(f"[{STRATEGY_NAME}] {attempt.key}: ERROR during robust kingdom check: {e}", exc_info=True)
            return self._create_failed_attempt(attempt, manager, reason="Kingdom check failed", error_msg=str(e))

        # Disambiguation logic

        # Compare paths - check if result path contains all expected ranks/terms from input
        match0 = self._compare_paths(expected_classification, result0_classification)
        match1 = self._compare_paths(expected_classification, result1_classification)

        winning_result: Optional[ResultData] = None
        final_classification: Optional[Dict[str, str]] = None

        if match0 and not match1:
            winning_result = result0
            final_classification = result0_classification
            logger.debug(f"Disambiguation for attempt {attempt.key}: Result 0 path matched input.")
        elif not match0 and match1:
            winning_result = result1
            final_classification = result1_classification
            logger.debug(f"Disambiguation for attempt {attempt.key}: Result 1 path matched input.")
        elif match0 and match1:
            # Both matched? This implies ambiguity remains or input was too sparse.
            logger.warning(f"Profile {STRATEGY_NAME} ambiguity for attempt {attempt.key}: Both result paths matched input. Cannot resolve.")
            # TODO: create FAILED or specific AMBIGUOUS status here? For now, return None.
            # return self._create_failed_attempt(attempt, manager, reason="Ambiguous match", error_msg="Both result paths matched input group")
            return None # Profile doesn't apply if ambiguous
        else:
             # Neither matched
             logger.debug(f"Profile {STRATEGY_NAME} mismatch for attempt {attempt.key}: Neither result path matched input.")
             return None # Profile mismatch


        # Profile matched with a single winner
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}.")

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_INNER_RANK_DISAMBIGUATION,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=final_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={'disambiguated_record_id': winning_result.record_id}
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}")
        return final_attempt

# Expose for registration
strategy_instance = ExactMatchPrimarySourceAcceptedInnerRankDisambiguationStrategy()
check_and_resolve = strategy_instance.check_and_resolve
