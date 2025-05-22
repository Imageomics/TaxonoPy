import logging
from typing import Optional, TYPE_CHECKING, List, Dict

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE, KINGDOM_SYNONYMS

from .profile_logging import setup_profile_logging
_PROFILE_DEBUG_OVERRIDE_ = False  # Set to True for debugging
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "MultiExactMatchPrimarySourceAcceptedHomonym"
# Use the new status if you added it
SUCCESS_STATUS = getattr(ResolutionStatus, "MULTI_EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_HOMONYM")

class MultiExactMatchPrimarySourceAcceptedHomonymStrategy(ResolutionStrategy):
    """
    Handles cases with multiple 'Exact', 'Accepted' matches from the primary source
    that represent homonyms (same name in different taxonomic groups).
    Disambiguates by matching the kingdom from the input to the results.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager",
        profiles_checked_log: Optional[List[str]] = None
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Multiple Exact, Accepted matches from primary source,
        disambiguating based on kingdom match with input.
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
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Match type is not 'Exact'.")
            return None

        # 3. Filter results to primary source with Accepted status
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

        # 5. Check for different kingdoms (confirms these are homonyms)
        kingdoms_found = set()
        for res in primary_accepted_results:
            if res.classification_path and "|" in res.classification_path:
                kingdom = res.classification_path.split("|")[0]
                kingdoms_found.add(kingdom)
        
        if len(kingdoms_found) < 2:
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: All results are from the same kingdom ({kingdoms_found}). Not a homonym case.")
            return None

        # 6. Kingdom match disambiguation
        input_kingdom = entry_group.kingdom
        if not input_kingdom:
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Input kingdom is empty, cannot disambiguate homonyms.")
            return None

        # Get canonical form of input kingdom (handles synonyms)
        canonical_input_kingdom = self.get_canonical_kingdom(input_kingdom)
        if not canonical_input_kingdom:
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Input kingdom '{input_kingdom}' not recognized as valid kingdom or synonym.")
            return None

        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Input kingdom '{input_kingdom}' mapped to canonical '{canonical_input_kingdom}'")
        
        # Find matching result
        matching_result = None
        for res in primary_accepted_results:
            if res.classification_path and "|" in res.classification_path:
                result_kingdom = res.classification_path.split("|")[0]
                canonical_result_kingdom = self.get_canonical_kingdom(result_kingdom)
                
                logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Result kingdom '{result_kingdom}' mapped to canonical '{canonical_result_kingdom}'")
                
                if canonical_result_kingdom and canonical_result_kingdom == canonical_input_kingdom:
                    matching_result = res
                    break
        
        if not matching_result:
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: No result found with kingdom matching input canonical kingdom '{canonical_input_kingdom}'")
            return None

        # Profile matched - kingdom matched successfully
        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Profile matched. Selected homonym in kingdom '{canonical_input_kingdom}'")

        # Extract classification from the matching result
        try:
            resolved_classification = self._extract_classification(matching_result)
            if not resolved_classification:
                logger.warning(f"[{STRATEGY_NAME}] {attempt.key}: Classification extraction yielded empty result. Failing.")
                return self._create_failed_attempt(
                    attempt, manager, 
                    reason="Classification extraction failed", 
                    error_msg="Extracted empty path from matching result", 
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
            'selected_result_id': matching_result.record_id,
            'selected_result_name': matching_result.matched_name,
            'matched_kingdom': canonical_input_kingdom,
            'homonym_kingdoms': list(kingdoms_found)
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
strategy_instance = MultiExactMatchPrimarySourceAcceptedHomonymStrategy()
check_and_resolve = strategy_instance.check_and_resolve
