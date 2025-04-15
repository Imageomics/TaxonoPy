import logging
from typing import Optional, TYPE_CHECKING, Dict, List

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

STRATEGY_NAME = "ExactMatchPrimarySourceAcceptedRankLevelDisambiguation"

class ExactMatchPrimarySourceAcceptedRankLevelDisambiguationStrategy(ResolutionStrategy):
    """
    Handles cases with exactly two 'Exact', 'Accepted' matches from the primary source,
    where both match the input path up to the query rank. Disambiguates by selecting
    the result whose path terminates exactly at the query rank level.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Two Exact, Accepted, Primary Source matches, identical canonicals
        matching query term. Selects the result ending at query rank.
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
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: One or both results are not 'Exact' matches.")
            return None

        # 3. Both statuses 'Accepted'?
        if not (result0.taxonomic_status == "Accepted" and result1.taxonomic_status == "Accepted"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: One or both results are not 'Accepted' statuses.")
            return None

        # 4. Both use data from the primary data source?
        try:
            primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
        except StopIteration:
             logger.error(f"Cannot check primary source for {STRATEGY_NAME}: DATA_SOURCE_PRECEDENCE is empty.")
             return self._create_failed_attempt(attempt, manager, reason="Configuration Error", error_msg="DATA_SOURCE_PRECEDENCE is empty")

        if not (result0.data_source_id == primary_source_id and result1.data_source_id == primary_source_id):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: One or both results do not use the primary data source.")
            return None

        # 5. Canonical forms match each other and the query term?
        if not (result0.matched_canonical_simple and
                result0.matched_canonical_simple == result1.matched_canonical_simple and
                result0.matched_canonical_simple == attempt.query_term):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Canonical forms do not match each other or the query term.")
            return None
        # Ensure these checks pass before proceeding
        if not (attempt.gnverifier_response and attempt.gnverifier_response.results and len(attempt.gnverifier_response.results) == 2): return None
        result0, result1 = attempt.gnverifier_response.results[0], attempt.gnverifier_response.results[1]
        if not (result0.match_type and isinstance(result0.match_type, MatchType) and result0.match_type.root == "Exact" and result1.match_type and isinstance(result1.match_type, MatchType) and result1.match_type.root == "Exact"): return None
        if not (result0.taxonomic_status == "Accepted" and result1.taxonomic_status == "Accepted"): return None
        try: primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
        except StopIteration: return self._create_failed_attempt(attempt, manager, reason="Config Error", error_msg="No primary source")
        if not (result0.data_source_id == primary_source_id and result1.data_source_id == primary_source_id): return None
        if not (result0.matched_canonical_simple and result0.matched_canonical_simple == result1.matched_canonical_simple and result0.matched_canonical_simple == attempt.query_term): return None

        # Disambiguation logic
        try:
            expected_classification = self._get_expected_classification(entry_group)
            result0_classification = self._extract_classification(result0)
            result1_classification = self._extract_classification(result1)
        except Exception as e:
            logger.error(f"Attempt {attempt.key}: Error extracting classification for {STRATEGY_NAME}: {e}")
            return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg=str(e))

        # 6. Find the highest rank where the query term appears in the input
        input_term_highest_rank = self._get_rank_of_term(attempt.query_term, entry_group)
        if input_term_highest_rank is None:
             logger.debug(f"Profile {STRATEGY_NAME} cannot apply to attempt {attempt.key}: Query term '{attempt.query_term}' not found in input EntryGroupRef ranks.")
             return None # Query term itself isn't meaningfully in the input hierarchy

        # 7. Check if both result paths match input up to the input_term_highest_rank
        match0_up_to_input_rank = self._compare_paths_up_to_rank(expected_classification, result0_classification, input_term_highest_rank)
        match1_up_to_input_rank = self._compare_paths_up_to_rank(expected_classification, result1_classification, input_term_highest_rank)

        if not (match0_up_to_input_rank and match1_up_to_input_rank):
            # If one or both results diverge from the input *before* the relevant rank, this profile doesn't apply
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: One or both result paths diverge from input before rank '{input_term_highest_rank}'.")
            return None

        # 8. Find the highest rank where the query term appears in each result
        result0_term_highest_rank = self._get_rank_of_term(attempt.query_term, result0_classification)
        result1_term_highest_rank = self._get_rank_of_term(attempt.query_term, result1_classification)

        # 9. Disambiguate: Find the result where the term's highest rank matches the input's highest rank for that term
        winner_index: Optional[int] = None
        if result0_term_highest_rank == input_term_highest_rank and result1_term_highest_rank != input_term_highest_rank:
            winner_index = 0
        elif result1_term_highest_rank == input_term_highest_rank and result0_term_highest_rank != input_term_highest_rank:
            winner_index = 1
        else:
            # Ambiguous: either both results assign the term to the same rank as input,
            # or neither does, or one/both don't contain the term at all in their path.
            logger.debug(f"Profile {STRATEGY_NAME} ambiguity/mismatch for attempt {attempt.key}: Cannot uniquely identify result where term '{attempt.query_term}' has rank '{input_term_highest_rank}'. R0='{result0_term_highest_rank}', R1='{result1_term_highest_rank}'")
            return None

        # Profile Matched with a single winner based on rank level of the term
        winning_result = attempt.gnverifier_response.results[winner_index]
        winning_classification = result0_classification if winner_index == 0 else result1_classification
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. Winning result index: {winner_index}")

        # 10. Action: Filter the winning classification up to the input_term_highest_rank
        filtered_resolved_classification = self._filter_classification_by_rank(
            winning_classification, input_term_highest_rank
        )

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_RANK_LEVEL_DISAMBIGUATION,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=filtered_resolved_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={'disambiguated_record_id': winning_result.record_id}
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}")
        return final_attempt

# Expose for registration
strategy_instance = ExactMatchPrimarySourceAcceptedRankLevelDisambiguationStrategy()
check_and_resolve = strategy_instance.check_and_resolve
