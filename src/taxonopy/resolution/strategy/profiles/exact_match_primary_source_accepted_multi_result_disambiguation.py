import logging
from typing import Optional, TYPE_CHECKING, Dict, List

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

STRATEGY_NAME = "ExactMatchPrimarySourceAcceptedMultiResultDisambiguation"

class ExactMatchPrimarySourceAcceptedMultiResultDisambiguationStrategy(ResolutionStrategy):
    """
    Handles cases with >=1 'Exact', 'Accepted' matches from the primary source.
    Filters candidates based on path consistency with input up to the relevant rank,
    then by matching the rank level of the query term, and finally uses parsing
    quality and result order as tie-breakers to select a single best match.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: >=1 Exact, Accepted, Primary Source matches, identical canonicals
        matching query term. Applies filtering and disambiguation to find the best match.
        """
        # Profile condition checks

        # 1. Has response and results?
        if not (attempt.gnverifier_response and attempt.gnverifier_response.results):
            return None # No results to process

        all_results: List[ResultData] = attempt.gnverifier_response.results

        # 2. Overall match type Exact?
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "Exact"):
             return None

        # 3. Filter initial candidates: Must be Accepted, Primary Source, and match query term
        try:
            primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
        except StopIteration:
             logger.error(f"Cannot check primary source for {STRATEGY_NAME}: DATA_SOURCE_PRECEDENCE is empty.")
             return self._create_failed_attempt(attempt, manager, reason="Configuration Error", error_msg="DATA_SOURCE_PRECEDENCE is empty")

        candidates: List[ResultData] = []
        for res in all_results:
            if (res.taxonomic_status == "Accepted" and
                    res.data_source_id == primary_source_id and
                    res.matched_canonical_simple == attempt.query_term):
                candidates.append(res)

        if not candidates:
             logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: No initial candidates found (Accepted, Primary Source, Canonical matches Query).")
             return None # No suitable candidates

        # Contextual filtering
        try:
            expected_classification = self._get_expected_classification(entry_group)
        except Exception as e:
            logger.error(f"Attempt {attempt.key}: Error getting expected classification for {STRATEGY_NAME}: {e}")
            return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg=str(e))

        # 4. Determine the relevant rank from the input for the query term
        input_term_highest_rank = self._get_rank_of_term(attempt.query_term, entry_group)
        if input_term_highest_rank is None:
             logger.debug(f"Profile {STRATEGY_NAME} cannot apply to attempt {attempt.key}: Query term '{attempt.query_term}' not found in input EntryGroupRef ranks.")
             return None

        # 5. Filter by path consistency up to the relevant rank
        path_matching_candidates: List[ResultData] = []
        candidate_classifications: Dict[str, Dict[str, str]] = {} # Cache extracted paths
        for cand in candidates:
             try:
                  cand_class = self._extract_classification(cand)
                  candidate_classifications[cand.record_id] = cand_class # Store for later use
                  if self._compare_paths_up_to_rank(expected_classification, cand_class, input_term_highest_rank):
                       path_matching_candidates.append(cand)
             except Exception as e:
                  logger.error(f"Attempt {attempt.key}, Candidate Record ID {cand.record_id}: Error during path comparison for {STRATEGY_NAME}: {e}")
                  # Skip this candidate if path comparison fails

        if not path_matching_candidates:
             logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: No candidates match input path up to rank '{input_term_highest_rank}'.")
             return None

        # 6. Filter by rank level: Term must be assigned to the correct rank in the result path
        rank_level_candidates: List[ResultData] = []
        for cand in path_matching_candidates:
            cand_class = candidate_classifications.get(cand.record_id) # Get cached path
            if not cand_class:
                continue # Should not happen if cached correctly

            cand_term_highest_rank = self._get_rank_of_term(attempt.query_term, cand_class)
            if cand_term_highest_rank == input_term_highest_rank:
                rank_level_candidates.append(cand)

        if not rank_level_candidates:
             logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: No path-matching candidates assign term '{attempt.query_term}' to rank '{input_term_highest_rank}'.")
             return None

        # Final disambiguation
        winner: Optional[ResultData] = None
        if len(rank_level_candidates) == 1:
            winner = rank_level_candidates[0]
            logger.debug(f"Profile {STRATEGY_NAME} found single rank-level candidate for attempt {attempt.key}: Record ID {winner.record_id}")
        else:
            # Multiple candidates match rank level, use parsing quality as tie-breaker
            logger.debug(f"Profile {STRATEGY_NAME} attempting tie-breaker for attempt {attempt.key} among {len(rank_level_candidates)} candidates.")
            high_quality_candidates = [
                cand for cand in rank_level_candidates
                if cand.score_details and cand.score_details.parsing_quality_score == 1
            ]

            if high_quality_candidates:
                winner = high_quality_candidates[0] # Pick the first high-quality one
                logger.debug(f"Selected winner based on parsing quality score == 1: Record ID {winner.record_id}")
            else:
                winner = rank_level_candidates[0] # Pick the first one if none have perfect parsing score
                logger.debug(f"Selected winner based on first available (no perfect parsing score): Record ID {winner.record_id}")

        # Profile Matched: single winner selected
        winning_classification = candidate_classifications.get(winner.record_id)
        if not winning_classification: # Safety check
             logger.error(f"Failed to retrieve cached classification for winning Record ID {winner.record_id} on attempt {attempt.key}")
             return self._create_failed_attempt(attempt, manager, reason="Internal error retrieving classification")

        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. Winning Record ID: {winner.record_id}")

        # Action: Filter the winning classification up to the relevant input rank
        filtered_resolved_classification = self._filter_classification_by_rank(
            winning_classification, input_term_highest_rank
        )

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_MULTI_RESULT_DISAMBIGUATION,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=filtered_resolved_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={'selected_record_id': winner.record_id, 'candidate_count': len(candidates)}
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}")
        return final_attempt

# Expose for registration
strategy_instance = ExactMatchPrimarySourceAcceptedMultiResultDisambiguationStrategy()
check_and_resolve = strategy_instance.check_and_resolve
