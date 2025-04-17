import logging
from typing import Optional, TYPE_CHECKING, List, Dict, Tuple

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE, TAXONOMIC_RANKS

from .profile_logging import setup_profile_logging
_PROFILE_DEBUG_OVERRIDE_ = False  # Set to True for debugging
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ExactMatchPrimarySourceMultiAcceptedTaxonomicMatch"

# Make sure to add these to ResolutionStatus enum
SUCCESS_STATUS = getattr(ResolutionStatus, "EXACT_MATCH_PRIMARY_SOURCE_MULTI_ACCEPTED_TAXONOMIC_MATCH", None)
TIE_STATUS = getattr(ResolutionStatus, "EXACT_MATCH_PRIMARY_SOURCE_MULTI_ACCEPTED_TAXONOMIC_TIE", None)

# Fallback for now
if TIE_STATUS is None:
    TIE_STATUS = ResolutionStatus.FAILED

class ExactMatchPrimarySourceMultiAcceptedTaxonomicMatchStrategy(ResolutionStrategy):
    """
    Handles cases with multiple 'Exact', 'Accepted' matches from the primary source
    where we need to disambiguate based on which result's classification path
    best matches the input taxonomic hierarchy.
    
    Handles kingdom synonyms based on the KINGDOM_SYNONYMS constant.
    If multiple results tie for highest match count, it fails with metadata.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager",
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Multiple Exact, Accepted, Primary Source matches.
        Selects the result with the most taxonomic rank matches with input data.
        """
        # Profile condition checks

        # 1. Has response and multiple results?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) >= 2):
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Needs at least 2 results.")
            return None  # Need multiple results

        # 2. Overall Match type 'Exact'?
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "Exact"):
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Match type is not 'Exact'.")
            return None

        # 3. Filter to primary source accepted results
        primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
        primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]

        primary_accepted_results: List[ResultData] = []
        for res in attempt.gnverifier_response.results:
            if res.data_source_id == primary_source_id and res.taxonomic_status == "Accepted":
                primary_accepted_results.append(res)

        # 4. Need at least 2 accepted results from primary source
        if len(primary_accepted_results) < 2:
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Fewer than 2 primary source accepted results found.")
            return None

        # Extract input taxonomy for comparison
        input_classification = self._get_expected_classification(entry_group)
        if not input_classification:
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: No valid input taxonomy to compare against.")
            return None

        # 5. Compare each result's taxonomy against input
        result_scores: List[Tuple[ResultData, int, Dict[str, str]]] = []
        
        for result in primary_accepted_results:
            try:
                # Extract result's classification
                result_classification = self._extract_classification(result)
                
                # Count how many ranks match between input and result
                match_count = 0
                matches = []
                
                for rank in TAXONOMIC_RANKS:
                    input_val = input_classification.get(rank)
                    result_val = result_classification.get(rank)
                    
                    if not input_val or not result_val:
                        continue
                    
                    # Special handling for kingdom to allow synonyms
                    if rank == 'kingdom':
                        input_canonical = self.get_canonical_kingdom(input_val)
                        result_canonical = self.get_canonical_kingdom(result_val)
                        
                        if input_canonical and result_canonical and input_canonical == result_canonical:
                            match_count += 1
                            matches.append(rank)
                    # Direct comparison for other ranks
                    elif input_val.lower() == result_val.lower():
                        match_count += 1
                        matches.append(rank)
                
                logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Result {result.record_id} has {match_count} matching ranks: {matches}")
                result_scores.append((result, match_count, result_classification))
                
            except Exception as e:
                logger.error(f"[{STRATEGY_NAME}] {attempt.key}: Error processing result {result.record_id}: {e}", exc_info=True)
                continue
        
        if not result_scores:
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: No valid results to compare.")
            return None
        
        # 6. Find the result(s) with highest number of matches
        max_match_count = max(score for _, score, _ in result_scores)
        best_results = [(result, classification) for result, score, classification in result_scores if score == max_match_count]
        
        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Found {len(best_results)} results with {max_match_count} matching ranks.")
        
        # 7. If there's just one winner, use it. Otherwise, it's a tie.
        if len(best_results) == 1:
            # Clear winner based on taxonomic matches
            winning_result, winning_classification = best_results[0]
            
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Selected winner: Record ID {winning_result.record_id}")
            
            # Create metadata with match details
            metadata = {
                'match_count': max_match_count,
                'total_results': len(primary_accepted_results),
                'selection_method': 'taxonomic_hierarchy_match',
                'selected_record_id': winning_result.record_id
            }
            
            # Create successful resolution attempt
            final_attempt = manager.create_attempt(
                entry_group_key=attempt.entry_group_key,
                query_term=attempt.query_term,
                query_rank=attempt.query_rank,
                data_source_id=attempt.data_source_id,
                status=SUCCESS_STATUS,
                gnverifier_response=attempt.gnverifier_response,
                resolved_classification=winning_classification,
                error=None,
                resolution_strategy_name=STRATEGY_NAME,
                failure_reason=None,
                metadata=metadata
            )
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Applied, created successful attempt {final_attempt.key}")
            return final_attempt
            
        else:
            # We have a tie - multiple results with same match count
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Tie between {len(best_results)} results with {max_match_count} matches.")
            
            # Create metadata with tie details
            metadata = {
                'match_count': max_match_count,
                'total_results': len(primary_accepted_results),
                'tied_results_count': len(best_results),
                'tied_record_ids': [result.record_id for result, _ in best_results],
                'selection_method': 'taxonomic_hierarchy_match_tie'
            }
            
            # Create failed attempt due to tie
            failed_attempt = manager.create_attempt(
                entry_group_key=attempt.entry_group_key,
                query_term=attempt.query_term,
                query_rank=attempt.query_rank,
                data_source_id=attempt.data_source_id,
                status=TIE_STATUS,
                gnverifier_response=attempt.gnverifier_response,
                resolved_classification=None,
                error=None,
                resolution_strategy_name=STRATEGY_NAME,
                failure_reason="Tie between multiple results with equal taxonomic matches",
                metadata=metadata
            )
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Applied, created tie attempt {failed_attempt.key}")
            return failed_attempt

# Expose for registration
strategy_instance = ExactMatchPrimarySourceMultiAcceptedTaxonomicMatchStrategy()
check_and_resolve = strategy_instance.check_and_resolve
