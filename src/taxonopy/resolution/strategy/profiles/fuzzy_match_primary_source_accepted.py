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

STRATEGY_NAME = "FuzzyMatchPrimarySourceAccepted"

class FuzzyMatchPrimarySourceAcceptedStrategy(ResolutionStrategy):
    """
    Handles cases with a single 'Fuzzy', 'Accepted' match from the primary source,
    verifying that the classification path matches the input EntryGroupRef up to the
    highest rank specified in the input.
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks profile: Single Fuzzy, Accepted, Primary Source match where result path
        matches input path up to the input's highest specified rank.
        """
        # Profile condition checks

        # 1. Has response and exactly one result?
        if not (attempt.gnverifier_response and
                attempt.gnverifier_response.results and
                len(attempt.gnverifier_response.results) == 1):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Attempt does not have exactly one result.")
            return None

        result: ResultData = attempt.gnverifier_response.results[0]

        # 2. Match type 'Fuzzy'?
        # Use attempt.gnverifier_response.matchType for overall match type
        if not (attempt.gnverifier_response.match_type and
                isinstance(attempt.gnverifier_response.match_type, MatchType) and
                attempt.gnverifier_response.match_type.root == "Fuzzy"):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Top-level matchType is not 'Fuzzy' ({attempt.gnverifier_response.match_type})")
            return None

        # 3. Result Status 'Accepted'?
        if result.taxonomic_status != "Accepted":
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result status is not 'Accepted' ({result.taxonomic_status})")
            return None

        # 4. Primary Source?
        try:
            primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
        except StopIteration:
            logger.error(f"Cannot check primary source for {STRATEGY_NAME}: DATA_SOURCE_PRECEDENCE is empty.")
            return self._create_failed_attempt(attempt, manager, reason="Configuration Error", error_msg="DATA_SOURCE_PRECEDENCE is empty")

        if result.data_source_id != primary_source_id:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result source {result.data_source_id} is not primary.")
            return None

        # 5. StemEditDistance indicates canonical forms likely match? (stemEditDistance == 0)
        #    This implicitly checks if the fuzzy match is plausible at the core name level.
        #    Note: the API specs indidcate this is actually called "editDistanceStem" in the response.
        # if result.edit_distance_stem != 0:
        # currently causing problems, so removing for now
        #      logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: StemEditDistance is not 0 ({result.edit_distance_stem}).")
        #      return None

        # 6. Path consistency check
        try:
            expected_classification = self._get_expected_classification(entry_group)
            result_classification = self._extract_classification(result)
        except Exception as e:
            logger.error(f"Attempt {attempt.key}: Error extracting classification for {STRATEGY_NAME}: {e}")
            return self._create_failed_attempt(attempt, manager, reason="Classification extraction failed", error_msg=str(e))

        parent_rank_field: Optional[str] = None
        query_rank = attempt.query_rank # Rank associated with the term that was queried

        if query_rank:
            try:
                # Map API rank ('class') back to internal field name ('class_') if needed
                query_rank_field = 'class_' if query_rank == 'class' else query_rank
                query_rank_index = TAXONOMIC_RANKS.index(query_rank_field)
                if query_rank_index > 0: # If it's not kingdom
                    parent_rank_field = TAXONOMIC_RANKS[query_rank_index - 1]
                # If query rank is kingdom (index 0), parent_rank_field remains None, comparison check below handles it
            except ValueError:
                logger.warning(f"Query rank '{query_rank}' for attempt {attempt.key} not found in TAXONOMIC_RANKS. Cannot determine parent rank for fuzzy path comparison.")
                return None # Cannot proceed with this profile if query rank is invalid/unknown

        # Perform comparison up to the parent rank (if one exists)
        if not self._compare_paths_up_to_rank(expected_classification, result_classification, parent_rank_field):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Result path does not match input path up to parent rank '{parent_rank_field}' (Query Rank was '{query_rank}').")
            return None

        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}.")

        # Action: Use the full classification from the matched result
        # No filtering needed here as the match was deemed acceptable based on higher ranks

        # Create final attempt
        final_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.FUZZY_MATCH_PRIMARY_SOURCE_ACCEPTED,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=result_classification,
            error=None,
            resolution_strategy_name=STRATEGY_NAME,
            failure_reason=None,
            metadata={'edit_distance': result.edit_distance}
        )
        logger.debug(f"Applied {STRATEGY_NAME}: Created final attempt {final_attempt.key} for original {attempt.key}")
        return final_attempt

# Expose for registration
strategy_instance = FuzzyMatchPrimarySourceAcceptedStrategy()
check_and_resolve = strategy_instance.check_and_resolve
