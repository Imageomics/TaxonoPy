import logging
from typing import Optional, TYPE_CHECKING, List, Dict

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData, MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE

from .profile_logging import setup_profile_logging
_PROFILE_DEBUG_OVERRIDE_ = False
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "ExactMatchPrimarySourceAcceptedAmongSynonymsSimple"
SUCCESS_STATUS = getattr(ResolutionStatus, "EXACT_MATCH_PRIMARY_SOURCE_ACCEPTED_AMONG_SYNONYMS_SIMPLE")

class ExactMatchPrimarySourceAcceptedAmongSynonymsSimpleStrategy(ResolutionStrategy):
    """
    Handles cases with multiple 'Exact' matches from the primary source where
    exactly one is 'Accepted' and all others are 'Synonym'. Trusts the
    classification path from the 'Accepted' result.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager",
        profiles_checked_log: Optional[List[str]] = None
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: >=2 Exact, Primary Source matches; 1 Accepted, rest Synonym.
        Selects Accepted result and takes its path as is.
        """
        # Profile condition checks

        # 1. Has response and > 1 result?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) > 1):
            return None # Need multiple results

        all_results: List[ResultData] = attempt.gnverifier_response.results

        # 2. Overall Match type 'Exact'?
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "Exact"):
            return None

        # 3. Filter results to Primary Source and find Accepted/Synonyms
        primary_source_key = list(DATA_SOURCE_PRECEDENCE.keys())[0]
        primary_source_id = DATA_SOURCE_PRECEDENCE[primary_source_key]

        primary_results: List[ResultData] = []
        accepted_result: Optional[ResultData] = None
        synonym_results: List[ResultData] = []
        accepted_count = 0

        for res in all_results:
            # Must be from primary source
            if res.data_source_id == primary_source_id and \
               res.match_type and isinstance(res.match_type, MatchType):
                primary_results.append(res) # Keep track of all relevant primary results
                if res.taxonomic_status == "Accepted":
                    # If multiple are found, the counts check below will fail (on purpose)
                    if accepted_count == 0:
                        accepted_result = res
                    accepted_count += 1

                # Ignore results with other statuses from primary source for this profile

        # 4. Check counts: Exactly 1 Accepted, and all other primary results are Synonyms
        total_primary_results = len(primary_results)

        # Make the check more permissive - only require exactly one accepted result
        if not (total_primary_results > 1 and accepted_count == 1):
            logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Mismatch on result requirements. "
                        f"Need >1 primary results with exactly 1 accepted. Got: Primary={total_primary_results}, Accepted={accepted_count}.")
            return None

        # 5. Check if the accepted result exists (should always be true if accepted_count == 1)
        if not accepted_result:
            logger.error(f"[{STRATEGY_NAME}] {attempt.key}: Internal logic error - accepted_count is 1 but accepted_result is None. Failing.")
            return self._create_failed_attempt(attempt, manager, reason="Internal Logic Error", error_msg="Accepted result not found despite count=1", profiles_checked_log=profiles_checked_log)

        # Profile matched
        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Profile matched. Selecting accepted result Record ID {accepted_result.record_id}")

        # Action: Extract classification from the Accepted result
        try:
            resolved_classification = self._extract_classification(accepted_result)
            if not resolved_classification:
                 logger.warning(f"[{STRATEGY_NAME}] {attempt.key}: Classification extraction from accepted result yielded empty result. Failing.")
                 return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg="Extracted empty path from accepted result", profiles_checked_log=profiles_checked_log)
        except Exception as e:
            logger.error(f"[{STRATEGY_NAME}] {attempt.key}: Error extracting classification from accepted result: {e}", exc_info=True)
            return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg=str(e), profiles_checked_log=profiles_checked_log)

        logger.debug(f"[{STRATEGY_NAME}] {attempt.key}: Using classification from accepted result: {resolved_classification}")

        # Prepare Metadata
        previous_metadata = attempt.metadata or {}
        profile_specific_metadata = {
            'accepted_record_id': accepted_result.record_id,
            'synonym_record_ids': [s.record_id for s in synonym_results]
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
strategy_instance = ExactMatchPrimarySourceAcceptedAmongSynonymsSimpleStrategy()
check_and_resolve = strategy_instance.check_and_resolve
