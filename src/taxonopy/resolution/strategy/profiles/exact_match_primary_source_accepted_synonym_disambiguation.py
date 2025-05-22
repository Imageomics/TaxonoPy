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
# Set to True in the specific file(s) you want to debug
_PROFILE_DEBUG_OVERRIDE_ = False
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ExactMatchPrimarySourceAcceptedSynonymDisambiguation"

class ExactMatchPrimarySourceAcceptedSynonymDisambiguationStrategy(ResolutionStrategy):
    """
    Handles cases with exactly two 'Exact', 'Accepted' matches from the primary source,
    one being Accepted and the other a Synonym. Selects the Accepted match if its path
    is consistent with the input EntryGroupRef up to the relevant rank.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Two Exact, Primary Source matches (one Accepted, one Synonym),
        identical canonicals matching query term. Selects Accepted if path matches input.
        """
        # Profile condition checks

        # 1. Has response and exactly two results?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 2):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Attempt does not have exactly two results.")
            return None

        result0: ResultData = attempt.gnverifier_response.results[0]
        result1: ResultData = attempt.gnverifier_response.results[1]

        # 2. Both match types 'Exact'?
        if not (result0.match_type and isinstance(result0.match_type, MatchType) and result0.match_type.root == "Exact" and
                result1.match_type and isinstance(result1.match_type, MatchType) and result1.match_type.root == "Exact"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: One or both results do not have match type 'Exact'.")
            return None

        # 3. Both use data from the primary data source?
        try:
            primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
        except StopIteration:
            logger.error(f"Cannot check primary source for {STRATEGY_NAME}: DATA_SOURCE_PRECEDENCE is empty.")
            return self._create_failed_attempt(attempt, manager, reason="Configuration Error", error_msg="DATA_SOURCE_PRECEDENCE is empty")

        if not (result0.data_source_id == primary_source_id and result1.data_source_id == primary_source_id):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: One or both results do not use the primary data source.")
            return None

        # 4. Canonical forms match each other and the query term?
        if not (result0.matched_canonical_simple and
                result0.matched_canonical_simple == result1.matched_canonical_simple and
                result0.matched_canonical_simple == attempt.query_term):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Canonical forms do not match each other or the query term.")
            return None

        # 5. Exactly one Accepted and one Synonym? Identify which is which.
        accepted_result: Optional[ResultData] = None
        synonym_result: Optional[ResultData] = None

        if result0.taxonomic_status == "Accepted" and result1.taxonomic_status == "Synonym":
            accepted_result = result0
            synonym_result = result1
        elif result1.taxonomic_status == "Accepted" and result0.taxonomic_status == "Synonym":
            accepted_result = result1
            synonym_result = result0
        else:
            # Does not match the one-accepted, one-synonym pattern
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Does not match the one-accepted, one-synonym pattern.")
            return None

        # Disambiguation Logic based on Accepted result's path
        try:
            expected_classification = self._get_expected_classification(entry_group)
            accepted_classification = self._extract_classification(accepted_result)
        except Exception as e:
            logger.error(f"Attempt {attempt.key}: Error extracting classification for {STRATEGY_NAME}: {e}")
            return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg=str(e))

        # 6. Determine the highest rank of the query term in the input
        input_term_highest_rank = self._get_rank_of_term(attempt.query_term, entry_group)
        if input_term_highest_rank is None:
             # This case is unlikely if the query term came from the entry group, but handle defensively
             logger.warning(f"Profile {STRATEGY_NAME} cannot apply to attempt {attempt.key}: Query term '{attempt.query_term}' not found in input EntryGroupRef ranks.")
             return None

        # 7. Check if the Accepted result's path matches input up to the relevant rank
        if not self._compare_paths_up_to_rank(expected_classification, accepted_classification, input_term_highest_rank):
             logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Accepted result path does not match input up to rank '{input_term_highest_rank}'.")
             return None # The accepted match isn't consistent with input context

        # Profile Matched: Accepted result verified against input context
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}.")

        # Action: Filter the Accepted classification up to the relevant rank
        filtered_resolved_classification = self._filter_classification_by_rank(
            accepted_classification, input_term_highest_rank
        )

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_SYNONYM_DISAMBIGUATION,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=filtered_resolved_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={'accepted_record_id': accepted_result.record_id, 'synonym_record_id': synonym_result.record_id}
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}")
        return final_attempt

# Expose for registration
strategy_instance = ExactMatchPrimarySourceAcceptedSynonymDisambiguationStrategy()
check_and_resolve = strategy_instance.check_and_resolve
