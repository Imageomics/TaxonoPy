import logging
from typing import Optional, TYPE_CHECKING, List, Dict, Set

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

STRATEGY_NAME = "ExactMatchPrimarySourceMultiAccepted"

SUCCESS_STATUS = getattr(ResolutionStatus, "EXACT_MATCH_PRIMARY_SOURCE_MULT_ACCEPTED")

class ExactMatchPrimarySourceMultiAcceptedStrategy(ResolutionStrategy):
    """
    Handles cases with multiple 'Exact' matches from the primary source where
    multiple results have 'Accepted' status with the same canonical name.
    
    Selection criteria (in order):
    1. If one accepted result has currentName matching query term exactly, select it
    2. If all accepted results have identical classification paths, select first one
    3. Otherwise, fail with ambiguity
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager",
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Multiple primary source results with multiple 'Accepted' status
        and same canonical name. Uses enhanced selection strategy.
        """
        # Profile condition checks

        # 1. Has response and multiple results?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) >= 2):
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Needs at least 2 results.")
            return None  # Need multiple results

        all_results: List[ResultData] = attempt.gnverifier_response.results

        # 2. Overall Match type 'Exact'?
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "Exact"):
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Overall match type is not 'Exact'.")
            return None

        # 3. Filter to primary source results
        primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
        primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]

        primary_accepted_results: List[ResultData] = []
        
        for res in all_results:
            if res.data_source_id == primary_source_id and res.taxonomic_status == "Accepted":
                primary_accepted_results.append(res)

        # 4. Need at least 2 accepted results from primary source
        if len(primary_accepted_results) < 2:
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Need at least 2 accepted results from primary source, found {len(primary_accepted_results)}.")
            return None

        # 5. Verify they have the same canonical name
        first_canonical = primary_accepted_results[0].matched_canonical_simple
        all_same_canonical = all(
            res.matched_canonical_simple == first_canonical 
            for res in primary_accepted_results
        )

        if not all_same_canonical:
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Not all accepted results have the same canonical name.")
            return None

        # 6. Enhanced Selection Logic
        selected_result = None
        selection_reason = ""
        
        # 6a. First priority: Check if any result's currentName exactly matches query term
        query_term = attempt.query_term.strip()
        for res in primary_accepted_results:
            current_name = res.current_name.strip() if res.current_name else ""
            if current_name == query_term:
                selected_result = res
                selection_reason = "exact_match_to_query_term"
                logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Found result with currentName exactly matching query term: {current_name}")
                break
        
        # 6b. Second priority: Check if all classification paths are identical
        if not selected_result:
            # Get all unique classification paths from accepted results
            classification_paths: Set[str] = set()
            for res in primary_accepted_results:
                if res.classification_path:
                    classification_paths.add(res.classification_path)
            
            if len(classification_paths) == 1:
                # All paths are identical, take the first result
                selected_result = primary_accepted_results[0]
                selection_reason = "identical_classifications"
                logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: All accepted results have identical classification paths. Selecting first result.")
            else:
                # Classification paths differ, ambiguous situation
                logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Classification paths differ between accepted results. Ambiguous.")
                return self._create_failed_attempt(
                    attempt, manager,
                    reason="Multiple accepted results with different classifications",
                    error_msg="Cannot disambiguate between accepted results with different classification paths",
                )

        # Profile matched - a result has been selected
        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Profile matched. Selected result: {selected_result.matched_name}, "
                     f"Reason: {selection_reason}")

        # Extract classification from the selected result
        try:
            resolved_classification = self._extract_classification(selected_result)
            if not resolved_classification:
                logger.warning(f"[{STRATEGY_NAME}] {attempt.key}: Classification extraction yielded empty result. Failing.")
                return self._create_failed_attempt(
                    attempt, manager, 
                    reason="Classification extraction failed", 
                    error_msg="Extracted empty path from selected result", 
                )
        except Exception as e:
            logger.error(f"[{STRATEGY_NAME}] {attempt.key}: Error extracting classification: {e}", exc_info=True)
            return self._create_failed_attempt(
                attempt, manager, 
                reason="Classification extraction failed", 
                error_msg=str(e), 
            )

        # Prepare Metadata
        previous_metadata = attempt.metadata or {}
        profile_specific_metadata = {
            'selected_result_id': selected_result.record_id,
            'selected_result_name': selected_result.matched_name,
            'selection_reason': selection_reason,
            'other_accepted_count': len(primary_accepted_results) - 1,
            'canonical_name': first_canonical
        }

        final_metadata = previous_metadata.copy()
        final_metadata.update(profile_specific_metadata)
        # if profiles_checked_log:
        #     final_metadata['profiles_checked'] = profiles_checked_log

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
strategy_instance = ExactMatchPrimarySourceMultiAcceptedStrategy()
check_and_resolve = strategy_instance.check_and_resolve
