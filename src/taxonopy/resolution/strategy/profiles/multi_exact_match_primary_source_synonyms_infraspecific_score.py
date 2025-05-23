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

STRATEGY_NAME = "MultiExactMatchPrimarySourceSynonymsInfraspecificScore"
# Use the new status if added, otherwise fall back
SUCCESS_STATUS = getattr(ResolutionStatus, "MULTI_EXACT_MATCH_PRIMARY_SOURCE_SYNONYMS_INFRASPECIFIC_SCORE")

class MultiExactMatchPrimarySourceSynonymsInfraspecificScoreStrategy(ResolutionStrategy):
    """
    Handles cases with multiple 'Exact', 'Synonym' matches from the primary source,
    where results have the same canonical name but different infraspecific ranks.
    Selects the result with the highest infraSpecificRankScore.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager",
        profiles_checked_log: Optional[List[str]] = None
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Multiple Exact, Primary Source, Synonym matches.
        Selects the one with highest infraSpecificRankScore.
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

        # 3. Filter results to Primary Source
        primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
        primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]

        primary_results: List[ResultData] = []
        for res in all_results:
            if res.data_source_id == primary_source_id:
                primary_results.append(res)

        if len(primary_results) < 2:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Less than 2 primary source results.")
            return None

        # 4. Check if all are marked as Synonym
        if not all(res.taxonomic_status == "Synonym" for res in primary_results):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Not all results are Synonyms.")
            return None

        # 5. Check if all point to the same accepted name
        if len(set(res.current_name for res in primary_results)) != 1:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Results point to different accepted names.")
            return None

        # 6. Find the result with highest infraSpecificRankScore
        best_result = None
        highest_score = -1

        for res in primary_results:
            # Check if scoreDetails exists and has infraSpecificRankScore
            if (res.score_details and 
                hasattr(res.score_details, 'infra_specific_rank_score') and
                res.score_details.infra_specific_rank_score is not None):
                
                score = res.score_details.infra_specific_rank_score
                if score > highest_score:
                    highest_score = score
                    best_result = res
            else:
                logger.debug(f"Result {res.record_id} missing infraSpecificRankScore, skipping.")
        
        if not best_result:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: "
                         f"Could not find result with valid infraSpecificRankScore.")
            return None

        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. "
                     f"Selected result: {best_result.matched_name} with "
                     f"infraSpecificRankScore: {highest_score}")

        # 7. Extract classification from the selected result
        try:
            resolved_classification = self._extract_classification(best_result)
            if not resolved_classification:
                logger.warning(f"[{STRATEGY_NAME}] {attempt.key}: Classification extraction yielded empty result. Failing.")
                return self._create_failed_attempt(
                    attempt, manager, 
                    reason="Classification extraction failed", 
                    error_msg="Extracted empty path from best result", 
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
            'selected_synonym': best_result.matched_name,
            'accepted_name': best_result.current_name,
            'accepted_record_id': best_result.current_record_id,
            'infra_specific_rank_score': highest_score
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
strategy_instance = MultiExactMatchPrimarySourceSynonymsInfraspecificScoreStrategy()
check_and_resolve = strategy_instance.check_and_resolve
