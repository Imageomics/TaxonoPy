import logging
from typing import Optional, TYPE_CHECKING, Dict

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

STRATEGY_NAME = "ExactMatchPrimarySourceSynonym"

class ExactMatchPrimarySourceSynonymStrategy(ResolutionStrategy):
    """
    Handles cases with a single 'Exact' match from the primary source, where the
    matched name is a 'Synonym'. Resolves to the provided accepted name.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Single Exact, Primary Source match marked as Synonym,
        with accepted name details provided.
        """
        # Profile condition checks

        # 1. Has response and exactly ONE result?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 1):
            logger.debug(f"Attempt {attempt.key} does not have exactly one result. Skipping profile check for {STRATEGY_NAME}.")
            return None

        result: ResultData = attempt.gnverifier_response.results[0]

        # 2. Top-level Match type 'Exact'?
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "Exact"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Top-level matchType is not 'Exact' ({attempt.gnverifier_response.match_type})")
            return None

        # 3. Primary Source?
        try:
            primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
        except StopIteration:
             logger.error(f"Cannot check primary source for {STRATEGY_NAME}: DATA_SOURCE_PRECEDENCE is empty.")
             return self._create_failed_attempt(attempt, manager, reason="Configuration Error", error_msg="DATA_SOURCE_PRECEDENCE is empty")

        if result.data_source_id != primary_source_id:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result data source ID '{result.data_source_id}' does not match primary source ID '{primary_source_id}'.")
            return None

        # 4. Result Status 'Synonym'?
        if result.taxonomic_status != "Synonym":
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result status is not 'Synonym' ({result.taxonomic_status})")
            return None

        # 5. Canonical of SYNONYM matches query term?
        if not (result.matched_canonical_simple and
                result.matched_canonical_simple == attempt.query_term):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Synonym canonical '{result.matched_canonical_simple}' doesn't match query term '{attempt.query_term}'.")
            return None

        # 6. Accepted name details provided? (currentName and classificationPath)
        #    GNVerifier usually provides the accepted name's path in classificationPath
        if not (result.current_name and result.classification_path):
             logger.warning(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Synonym result lacks currentName ('{result.current_name}') or classificationPath ('{result.classification_path}'). Cannot resolve to accepted name.")
             return None

        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}.")

        # Action: Extract the classification path (which belongs to the accepted name)
        try:
            # Use the classification path directly provided in the result for the accepted name
            resolved_classification = self._extract_classification(result)
        except Exception as e:
            logger.error(f"Attempt {attempt.key}: Error extracting classification for {STRATEGY_NAME}: {e}")
            return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg=str(e))

        if not resolved_classification:
             logger.warning(f"Profile {STRATEGY_NAME} applied to attempt {attempt.key}, but failed to extract a valid classification path from the result.")
             # Optionally fail here, or proceed and let output handle empty classification? Let's fail for now.
             return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg="Extracted empty classification for accepted name")


        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.EXACT_MATCH_PRIMARY_SOURCE_SYNONYM,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=resolved_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            # Add metadata about the synonym relationship
            metadata={
                'synonym_matched': result.matched_name,
                'accepted_name': result.current_name,
                'accepted_record_id': result.current_record_id
                }
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}, resolving to accepted name '{result.current_name}'.")
        return final_attempt

    # Helpers inherited from base

# Expose for registration
strategy_instance = ExactMatchPrimarySourceSynonymStrategy()
check_and_resolve = strategy_instance.check_and_resolve
