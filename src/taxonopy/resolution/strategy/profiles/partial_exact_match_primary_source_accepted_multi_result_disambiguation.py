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

STRATEGY_NAME = "PartialExactMatchPrimarySourceAcceptedMultiResultDisambiguation"

class PartialExactMatchPrimarySourceAcceptedMultiResultDisambiguationStrategy(ResolutionStrategy):
    """
    Handles cases with >=1 'PartialExact', 'Accepted' matches from the primary source.
    Filters candidates based on whether the matched canonical name starts the query term,
    then by path consistency with input up to the relevant rank, then by matching
    the rank level of the matched canonical term, and finally uses parsing
    quality and result order as tie-breakers to select a single best match.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: >=1 PartialExact, Accepted, Primary Source matches.
        Filters & disambiguates to find the best match consistent with input context.
        """
        # Profile condition checks

        # 1. Match Type 'PartialExact'?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "PartialExact"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Match type is not 'PartialExact'.")
            return None

        # 2. Has results?
        if not attempt.gnverifier_response.results:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: No results found.")
            return None

        all_results: List[ResultData] = attempt.gnverifier_response.results

        # 3. Filter initial candidates: Accepted, Primary Source
        try:
            primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
        except StopIteration:
             logger.error(f"Cannot check primary source for {STRATEGY_NAME}: DATA_SOURCE_PRECEDENCE is empty.")
             return self._create_failed_attempt(attempt, manager, reason="Configuration Error", error_msg="DATA_SOURCE_PRECEDENCE is empty")

        candidates: List[ResultData] = []
        for res in all_results:
            if (res.taxonomic_status == "Accepted" and
                    res.data_source_id == primary_source_id and
                    res.matched_canonical_simple): # Ensure matched term exists
                candidates.append(res)
        if not candidates:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: No Accepted/PrimarySource candidates found.")
            return None


        # 4. Contextual and rank-level matching
        try:
            expected_classification = self._get_expected_classification(entry_group)
        except Exception as e:
             logger.error(f"Attempt {attempt.key}: Error getting expected classification for {STRATEGY_NAME}: {e}")
             return self._create_failed_attempt(attempt, manager, reason="Getting expected classification failed", error_msg=str(e))


        valid_candidates: List[ResultData] = []
        candidate_classifications: Dict[str, Dict[str, str]] = {}
        candidate_match_ranks: Dict[str, Optional[str]] = {} # Rank where match was confirmed

        for cand in candidates:
             # Ensure matched_canonical_simple exists (already checked, but belts and suspenders)
             matched_term = cand.matched_canonical_simple
             if not matched_term:
                continue

             try:
                  cand_class = self._extract_classification(cand)
                  candidate_classifications[cand.record_id] = cand_class

                  # Find highest rank of the matched term in the RESULT's path
                  result_term_highest_rank = self._get_rank_of_term(matched_term, cand_class)
                  if result_term_highest_rank is None:
                       logger.debug(f"Candidate {cand.record_id}: Matched term '{matched_term}' not found in result path ranks.")
                       continue

                  # Get the corresponding term from the INPUT at that same rank
                  input_term_at_result_rank = getattr(entry_group, result_term_highest_rank, None)

                  # Check 1: Input term starts with matched term
                  # Allow for exact match as well (startswith includes equality)
                  if not (input_term_at_result_rank and
                          input_term_at_result_rank.strip().startswith(matched_term)):
                        logger.debug(f"Candidate {cand.record_id}: Input term '{input_term_at_result_rank}' at rank '{result_term_highest_rank}' does not start with matched term '{matched_term}'.")
                        continue

                  # Check 2: Higher classification path matches
                  parent_rank = self._get_parent_rank(result_term_highest_rank)
                  # Note: _compare_paths_up_to_rank handles parent_rank being None (if rank is kingdom)
                  if not self._compare_paths_up_to_rank(expected_classification, cand_class, parent_rank):
                       logger.debug(f"Candidate {cand.record_id}: Higher path does not match input up to parent rank '{parent_rank}'.")
                       continue

                  # If both checks pass, it's a valid candidate
                  valid_candidates.append(cand)
                  candidate_match_ranks[cand.record_id] = result_term_highest_rank # Store the rank

             except Exception as e:
                  logger.error(f"Attempt {attempt.key}, Candidate Record ID {cand.record_id}: Error processing candidate for {STRATEGY_NAME}: {e}", exc_info=True)
                  # Skip this candidate on error

        if not valid_candidates:
             logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: No candidates passed semantic rank and path consistency checks.")
             return None

        # 5. Final sisambiguation (if len(valid_candidates) > 1)
        winner: Optional[ResultData] = None
        if len(valid_candidates) == 1:
             winner = valid_candidates[0]
             logger.debug(f"Profile {STRATEGY_NAME} selected single valid candidate for attempt {attempt.key}: Record ID {winner.record_id}")
        else:
            # tie-breaker logic
            logger.debug(f"Profile {STRATEGY_NAME} attempting tie-breaker for attempt {attempt.key} among {len(valid_candidates)} candidates.")
            high_quality_candidates = [
                cand for cand in valid_candidates
                if cand.score_details and cand.score_details.parsing_quality_score == 1
            ]

            if high_quality_candidates:
                winner = high_quality_candidates[0] # Pick the first high-quality one
                logger.debug(f"Selected winner based on parsing quality score == 1: Record ID {winner.record_id}")
            else:
                winner = valid_candidates[0] # Pick the first one if none have perfect parsing score
                logger.debug(f"Selected winner based on first available (no perfect parsing score): Record ID {winner.record_id}")

        # Profile Matched: A single winner selected
        winning_classification = candidate_classifications.get(winner.record_id)
        # Get the rank used for filtering for this specific winner
        rank_for_filtering = candidate_match_ranks.get(winner.record_id)

        # Check if we successfully got the needed info for the winner
        if not winning_classification or rank_for_filtering is None:
             logger.error(f"Failed to retrieve cached classification or match rank for winning Record ID {winner.record_id} on attempt {attempt.key}")
             return self._create_failed_attempt(attempt, manager, reason="Internal error retrieving winning classification/rank")

        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. Winning Record ID: {winner.record_id}, Matched Rank: {rank_for_filtering}")

        # Action
        # Filter the winning classification up to the relevant rank
        filtered_resolved_classification = self._filter_classification_by_rank(
            winning_classification, rank_for_filtering
        )

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.PARTIAL_EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_DISAMBIGUATED,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=filtered_resolved_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={'selected_record_id': winner.record_id, 'matched_canonical': winner.matched_canonical_simple}
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}")
        return final_attempt

# Expose for registration
strategy_instance = PartialExactMatchPrimarySourceAcceptedMultiResultDisambiguationStrategy()
check_and_resolve = strategy_instance.check_and_resolve
